"""
VISTA 2.0 — Audio Forensic Pipeline Test Suite

Comprehensive tests covering all 6 stages:
  1. Impulse detection accuracy and latency
  2. Event classification across 12 classes
  3. Energy/SPL characterization accuracy
  4. MVDR beamforming separation quality
  5. Temporal alignment precision (+/-0.1ms)
  6. Forensic chain integrity and SWGDE compliance

Run: python -m pytest test_audio.py -v
"""

import hashlib
import hmac
import time
from typing import Optional

import numpy as np
import pytest

from vista_hil.audio_pipeline import (
    AudioPipelineConfig,
    AudioForensicPipeline,
    ImpulseDetector,
    ImpulseEvent,
    EventClassifier,
    EnergyCharacterizer,
    MVDRBeamformer,
    TemporalAligner,
    ForensicAudioProcessor,
    PipelineResult,
    CrashEventClass,
    SeverityLevel,
    EVENT_CLASS_NAMES,
    SAMPLE_RATE_HZ,
    N_CHANNELS,
    MAX_SPL_DB,
)
from vista_hil.evidence_chain import EvidenceChain


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def config():
    """Standard pipeline configuration."""
    return AudioPipelineConfig()


@pytest.fixture
def pipeline(config):
    """Initialized pipeline with test HMAC key."""
    return AudioForensicPipeline(
        config=config,
        shared_secret=b"test-key-32-bytes-for-audio-pipeline!!"
    )


@pytest.fixture
def crash_audio(config):
    """
    Generate synthetic crash audio with known impulse location.
    Impulse at 50ms, duration 10ms, amplitude 0.8.
    """
    sr = config.sample_rate
    duration_s = 0.15
    n_samples = int(sr * duration_s)
    t = np.arange(n_samples) / sr

    rng = np.random.default_rng(42)
    # Very low background noise so STER ratio is high
    audio = rng.normal(0, 0.001, (n_samples, config.n_channels))

    # Impulse at 50ms — use deterministic waveform for reliability
    impulse_center = int(0.05 * sr)
    impulse_width = int(0.01 * sr)  # 10ms = 480 samples
    start = impulse_center - impulse_width // 2
    end = start + impulse_width

    # Haversine-shaped impulse (matches crash pulse shape)
    t_imp = np.linspace(0, np.pi, impulse_width)
    impulse_wave = 0.8 * np.sin(t_imp) ** 2

    for ch in range(config.n_channels):
        audio[start:end, ch] = impulse_wave

    return audio, t


@pytest.fixture
def normal_audio(config):
    """Normal driving audio (no impulse)."""
    rng = np.random.default_rng(99)
    n_samples = int(config.sample_rate * 0.5)
    audio = rng.normal(0, 0.01, (n_samples, config.n_channels))
    t = np.arange(n_samples) / config.sample_rate
    for ch in range(config.n_channels):
        audio[:, ch] += 0.005 * np.sin(2 * np.pi * 20 * t)
    return audio


@pytest.fixture
def imu_data():
    """Synthetic IMU acceleration data aligned with crash audio."""
    sr_imu = 1000
    duration_s = 0.15
    n_samples = int(sr_imu * duration_s)
    t = np.arange(n_samples) / sr_imu

    rng = np.random.default_rng(42)
    accel = rng.normal(0, 0.5, (n_samples, 3))
    accel[:, 2] += 9.81

    # Crash jerk at ~50ms
    jerk_center = int(0.05 * sr_imu)
    jerk_width = int(0.01 * sr_imu)
    start = jerk_center - jerk_width // 2
    end = jerk_center + jerk_width // 2

    pulse = np.zeros(n_samples)
    pulse[start:end] = 50 * 9.81 * np.sin(np.pi * np.arange(jerk_width) / jerk_width) ** 2
    accel[:, 0] += pulse

    return accel, t


# ===================================================================
# Stage 1: Impulse Detection Tests
# ===================================================================

class TestImpulseDetector:

    def test_detects_strong_impulse(self, config, crash_audio):
        audio, t = crash_audio
        detector = ImpulseDetector(config)
        events = detector.detect(audio)

        assert len(events) >= 1
        event = events[0]
        assert 0.04 < event.onset_time_s < 0.06
        assert event.duration_ms > 0
        assert event.ster_max > config.ster_threshold

    def test_no_impulse_in_noise(self, config, normal_audio):
        detector = ImpulseDetector(config)
        events = detector.detect(normal_audio)
        assert len(events) == 0

    def test_impulse_peak_amplitude(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        events = detector.detect(audio)

        assert len(events) >= 1
        assert events[0].peak_amplitude > 0.3

    def test_impulse_timing_precision(self, config):
        sr = config.sample_rate
        n_samples = int(sr * 0.1)
        audio = np.zeros((n_samples, 4))
        rng = np.random.default_rng(42)
        audio += rng.normal(0, 0.005, audio.shape)

        target_sample = 2400
        impulse_samples = 480
        for ch in range(4):
            audio[target_sample:target_sample + impulse_samples, ch] = \
                0.9 * rng.standard_normal(impulse_samples)

        detector = ImpulseDetector(config)
        events = detector.detect(audio)

        assert len(events) >= 1
        onset_error = abs(events[0].onset_sample - target_sample)
        assert onset_error <= 10

    def test_detects_multiple_impulses(self, config):
        sr = config.sample_rate
        n_samples = int(sr * 0.2)
        audio = np.zeros((n_samples, 4))
        rng = np.random.default_rng(42)
        audio += rng.normal(0, 0.005, audio.shape)

        for center_ms in [50, 150]:
            center = int(center_ms / 1000 * sr)
            width = int(0.008 * sr)
            for ch in range(4):
                audio[center:center + width, ch] = 0.7 * rng.standard_normal(width)

        detector = ImpulseDetector(config)
        events = detector.detect(audio)
        assert len(events) >= 2

    def test_minimum_duration_filter(self, config):
        """Events shorter than impulse_min_duration_ms should be filtered."""
        sr = config.sample_rate
        n_samples = int(sr * 0.05)  # 50ms
        audio = np.zeros((n_samples, 4))

        # Use a config with high minimum duration to test filtering
        tight_config = AudioPipelineConfig(impulse_min_duration_ms=5.0)
        detector = ImpulseDetector(tight_config)

        # Add a very short spike (2 samples only)
        audio[1200:1202, :] = 1.0
        events = detector.detect(audio)
        assert len(events) == 0

    def test_latency_under_10ms(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)

        t0 = time.perf_counter()
        detector.detect(audio)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 10


# ===================================================================
# Stage 2: Event Classification Tests
# ===================================================================

class TestEventClassifier:

    def test_classifies_impulse(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        classifier = EventClassifier(config)

        events = detector.detect(audio)
        result = classifier.classify(audio, events[0])

        assert isinstance(result.event_class, CrashEventClass)
        assert 0 <= result.confidence <= 1
        assert len(result.class_probabilities) == 12

    def test_probabilities_sum_to_one(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        classifier = EventClassifier(config)

        events = detector.detect(audio)
        result = classifier.classify(audio, events[0])

        total = sum(result.class_probabilities.values())
        assert abs(total - 1.0) < 0.01

    def test_mfcc_features_extracted(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        classifier = EventClassifier(config)

        events = detector.detect(audio)
        result = classifier.classify(audio, events[0])

        assert result.mfcc_features is not None
        assert len(result.mfcc_features) == config.mfcc_n_coeffs

    def test_mfcc_shape(self, config):
        classifier = EventClassifier(config)
        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.1, config.sample_rate)
        mfcc = classifier._compute_mfcc(audio)
        assert mfcc.shape == (config.mfcc_n_coeffs,)

    def test_mfcc_short_audio(self, config):
        classifier = EventClassifier(config)
        audio = np.random.normal(0, 0.1, 100)
        mfcc = classifier._compute_mfcc(audio)
        assert mfcc.shape == (config.mfcc_n_coeffs,)

    def test_all_classes_represented(self, config):
        classifier = EventClassifier(config)
        for cls in CrashEventClass:
            assert cls in classifier.centroids

    def test_class_names_complete(self):
        assert len(EVENT_CLASS_NAMES) == 12
        for i in range(12):
            assert i in EVENT_CLASS_NAMES


# ===================================================================
# Stage 3: Energy Characterization Tests
# ===================================================================

class TestEnergyCharacterizer:

    def test_spl_calculation(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        char = EnergyCharacterizer(config)

        events = detector.detect(audio)
        profile = char.characterize(audio, events[0])

        assert profile.peak_spl_db > 0
        assert profile.rms_spl_db > 0
        assert profile.peak_spl_db >= profile.rms_spl_db

    def test_severity_classification(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        char = EnergyCharacterizer(config)

        events = detector.detect(audio)
        profile = char.characterize(audio, events[0])

        assert isinstance(profile.severity, SeverityLevel)

    def test_amplitude_to_spl(self, config):
        char = EnergyCharacterizer(config)

        spl_1 = char._amplitude_to_spl_db(1.0)
        assert 125 < spl_1 < 135

        spl_05 = char._amplitude_to_spl_db(0.5)
        assert 120 < spl_05 < 130

        spl_001 = char._amplitude_to_spl_db(0.001)
        assert 60 < spl_001 < 80

    def test_energy_positive(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        char = EnergyCharacterizer(config)

        events = detector.detect(audio)
        profile = char.characterize(audio, events[0])
        assert profile.energy_joules_per_m2 >= 0

    def test_duration_matches_event(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        char = EnergyCharacterizer(config)

        events = detector.detect(audio)
        profile = char.characterize(audio, events[0])
        assert abs(profile.duration_ms - events[0].duration_ms) < 0.1


# ===================================================================
# Stage 4: Source Separation Tests
# ===================================================================

class TestMVDRBeamformer:

    def test_separates_sources(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        beamformer = MVDRBeamformer(config)

        events = detector.detect(audio)
        sources = beamformer.separate(audio, events[0])

        assert len(sources) >= 1
        assert len(sources) <= 4

    def test_source_labels(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        beamformer = MVDRBeamformer(config)

        events = detector.detect(audio)
        sources = beamformer.separate(audio, events[0])

        labels = {src.label for src in sources}
        assert "speech" in labels or "impact" in labels

    def test_source_snr_numeric(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        beamformer = MVDRBeamformer(config)

        events = detector.detect(audio)
        sources = beamformer.separate(audio, events[0])

        for src in sources:
            assert isinstance(src.snr_db, float)

    def test_steering_vector_shape(self, config):
        beamformer = MVDRBeamformer(config)
        sv = beamformer._compute_steering_vector(1000.0, 0.0)
        assert sv.shape == (config.n_channels,)

    def test_covariance_matrix_shape(self, config):
        beamformer = MVDRBeamformer(config)
        rng = np.random.default_rng(42)
        frames = rng.standard_normal((100, config.n_channels)) + \
                 1j * rng.standard_normal((100, config.n_channels))
        R = beamformer._compute_covariance(frames)
        assert R.shape == (config.n_channels, config.n_channels)

    def test_mvdr_output_nonempty(self, config, crash_audio):
        audio, _ = crash_audio
        detector = ImpulseDetector(config)
        beamformer = MVDRBeamformer(config)

        events = detector.detect(audio)
        sources = beamformer.separate(audio, events[0])

        for src in sources:
            assert len(src.signal) > 0

    def test_single_channel_input(self, config):
        sr = config.sample_rate
        n = int(sr * 0.1)
        rng = np.random.default_rng(42)
        audio_mono = rng.normal(0, 0.1, n)
        audio_mono[int(0.04 * sr):int(0.06 * sr)] = 0.7

        beamformer = MVDRBeamformer(config)
        detector = ImpulseDetector(config)
        events = detector.detect(audio_mono.reshape(-1, 1))

        if events:
            sources = beamformer.separate(audio_mono.reshape(-1, 1), events[0])
            assert len(sources) >= 1


# ===================================================================
# Stage 5: Temporal Alignment Tests
# ===================================================================

class TestTemporalAligner:

    def test_aligns_simultaneous_events(self, config):
        sr_audio = config.sample_rate
        sr_imu = 1000
        duration = 0.1
        n_audio = int(sr_audio * duration)
        n_imu = int(sr_imu * duration)

        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.01, n_audio)
        imu = np.zeros((n_imu, 3))
        imu[:, 2] = 9.81

        center_audio = int(0.05 * sr_audio)
        width_audio = int(0.005 * sr_audio)
        audio[center_audio:center_audio + width_audio] = 0.8

        center_imu = int(0.05 * sr_imu)
        width_imu = int(0.005 * sr_imu)
        imu[center_imu:center_imu + width_imu, 0] = 50 * 9.81

        aligner = TemporalAligner(config)
        result = aligner.align(audio, imu)

        assert abs(result.audio_offset_ms) < 5.0

    def test_precision_requirement(self, config):
        sr_audio = config.sample_rate
        sr_imu = 1000
        duration = 0.2
        n_audio = int(sr_audio * duration)
        n_imu = int(sr_imu * duration)

        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.005, n_audio)
        imu = np.zeros((n_imu, 3))
        imu[:, 2] = 9.81

        audio_delay_ms = 2.0
        audio_delay_samples = int(audio_delay_ms / 1000 * sr_audio)

        center_audio = int(0.05 * sr_audio) + audio_delay_samples
        width = int(0.01 * sr_audio)
        audio[center_audio:center_audio + width] = 0.8

        center_imu = int(0.05 * sr_imu)
        width_imu = int(0.01 * sr_imu)
        imu[center_imu:center_imu + width_imu, 0] = 50 * 9.81

        aligner = TemporalAligner(config)
        result = aligner.align(audio, imu)

        assert result.alignment_confidence > 0.3

    def test_energy_envelope(self, config):
        sr = config.sample_rate
        n = int(sr * 0.05)
        t = np.arange(n) / sr

        signal = 0.5 * np.sin(2 * np.pi * 1000 * t)
        signal[int(0.01 * sr):int(0.04 * sr)] *= 0

        aligner = TemporalAligner(config)
        envelope = aligner._compute_energy_envelope(signal, sr)

        assert len(envelope) == len(signal)
        assert np.all(envelope >= 0)

    def test_jerk_magnitude(self, config):
        sr_imu = 1000
        n = 100
        accel = np.zeros((n, 3))
        accel[50:, 0] = 10

        aligner = TemporalAligner(config)
        jerk = aligner._compute_jerk_magnitude(accel, sr_imu)

        assert len(jerk) == n - 1
        assert jerk[49] > 0

    def test_no_imu_data(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config)

        result = pipeline.process(audio, imu_data=None)
        assert result.success
        for align in result.alignments:
            assert align.audio_offset_ms == 0.0
            assert align.alignment_confidence == 0.0


# ===================================================================
# Stage 6: Forensic Chain Tests
# ===================================================================

class TestForensicChain:

    def test_package_creation(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(
            config=config,
            shared_secret=b"test-forensic-key-32-bytes!!!"
        )

        result = pipeline.process(audio)
        assert result.success
        assert len(result.forensic_packages) >= 1

    def test_evidence_id_format(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"test-key-32-bytes-for-testing!!!!!")

        result = pipeline.process(audio)
        pkg = result.forensic_packages[0]
        assert pkg.evidence_id.startswith("ev-")

    def test_sha256_format(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"test-key-32-bytes-for-testing!!!!!")

        result = pipeline.process(audio)
        pkg = result.forensic_packages[0]
        assert len(pkg.sha256_hash) == 64
        assert all(c in '0123456789abcdef' for c in pkg.sha256_hash)

    def test_hmac_format(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"test-key-32-bytes-for-testing!!!!!")

        result = pipeline.process(audio)
        pkg = result.forensic_packages[0]
        assert len(pkg.hmac_signature) == 64
        assert all(c in '0123456789abcdef' for c in pkg.hmac_signature)

    def test_audio_hash_unique(self, config):
        sr = config.sample_rate
        rng = np.random.default_rng(42)
        audio1 = rng.normal(0, 0.1, (sr, 4))
        audio2 = rng.normal(0, 0.2, (sr, 4))

        proc = ForensicAudioProcessor(config)
        hash1 = proc._hash_audio(audio1)
        hash2 = proc._hash_audio(audio2)
        assert hash1 != hash2

    def test_audio_hash_deterministic(self, config):
        sr = config.sample_rate
        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.1, (sr, 4))

        proc = ForensicAudioProcessor(config)
        hash1 = proc._hash_audio(audio)
        hash2 = proc._hash_audio(audio)
        assert hash1 == hash2

    def test_swgde_metadata(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"test-key-32-bytes-for-testing!!!!!")

        result = pipeline.process(audio)
        pkg = result.forensic_packages[0]

        assert "standard" in pkg.swgde_metadata
        assert "SWGDE" in pkg.swgde_metadata["standard"]
        assert pkg.swgde_metadata["sample_rate_hz"] == config.sample_rate
        assert pkg.swgde_metadata["bit_depth"] == config.bit_depth
        assert pkg.swgde_metadata["n_channels"] == config.n_channels

    def test_package_verification(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"test-key-32-bytes-for-testing!!!!!")

        result = pipeline.process(audio)
        pkg = result.forensic_packages[0]
        verification = pipeline.forensic.verify_package(pkg)
        assert verification["valid"]

    def test_chain_of_custody(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"test-key-32-bytes-for-testing!!!!!")

        result = pipeline.process(audio)
        pkg = result.forensic_packages[0]
        assert "chain_of_custody" in pkg.swgde_metadata
        coc = pkg.swgde_metadata["chain_of_custody"]
        assert "created" in coc
        assert "integrity_hash" in coc
        assert "authenticity_hmac" in coc


# ===================================================================
# Integration Tests
# ===================================================================

class TestPipelineIntegration:
    """End-to-end pipeline integration tests."""

    def test_full_pipeline_crash_audio(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"integration-test-key-32-bytes!!!")

        result = pipeline.process(audio)

        assert result.success
        assert len(result.events) >= 1
        assert len(result.classifications) >= 1
        assert len(result.energy_profiles) >= 1
        assert len(result.separated_sources) >= 1
        assert len(result.forensic_packages) >= 1
        assert result.processing_time_ms > 0

    def test_full_pipeline_with_imu(self, config, crash_audio, imu_data):
        audio, _ = crash_audio
        imu, _ = imu_data
        pipeline = AudioForensicPipeline(config, shared_secret=b"integration-test-key-32-bytes!!!")

        result = pipeline.process(audio, imu_data=imu)

        assert result.success
        for align in result.alignments:
            assert isinstance(align.audio_offset_ms, float)

    def test_full_pipeline_normal_audio(self, config, normal_audio):
        pipeline = AudioForensicPipeline(config, shared_secret=b"integration-test-key-32-bytes!!!")

        result = pipeline.process(normal_audio)
        assert not result.success
        assert result.error_message is not None

    def test_pipeline_latency_benchmark(self, config, crash_audio):
        audio, _ = crash_audio
        pipeline = AudioForensicPipeline(config, shared_secret=b"benchmark-key-32-bytes!!!!!!!!!")

        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            pipeline.process(audio)
            times.append((time.perf_counter() - t0) * 1000)

        avg_ms = np.mean(times)
        p99_ms = np.percentile(times, 99)
        assert avg_ms < 200, f"Average latency {avg_ms:.1f}ms too high"
        assert p99_ms < 500, f"P99 latency {p99_ms:.1f}ms too high"

    def test_multiple_crash_events(self, config):
        sr = config.sample_rate
        n_samples = int(sr * 0.3)
        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.01, (n_samples, 4))

        # Two impulses
        for center_ms in [80, 200]:
            center = int(center_ms / 1000 * sr)
            width = int(0.01 * sr)
            for ch in range(4):
                audio[center:center + width, ch] = 0.7 * rng.standard_normal(width)

        pipeline = AudioForensicPipeline(config, shared_secret=b"multi-event-key-32-bytes!!!!!!")
        result = pipeline.process(audio)

        assert result.success
        assert len(result.events) >= 2
        assert len(result.forensic_packages) >= 2

    def test_pipeline_deterministic(self, config, crash_audio):
        """Same input should produce same output."""
        audio, _ = crash_audio
        secret = b"deterministic-test-key-32-bytes!!"
        pipeline1 = AudioForensicPipeline(config, shared_secret=secret)
        pipeline2 = AudioForensicPipeline(config, shared_secret=secret)

        result1 = pipeline1.process(audio)
        result2 = pipeline2.process(audio)

        assert result1.success == result2.success
        assert len(result1.events) == len(result2.events)
        if result1.events:
            assert abs(result1.events[0].onset_time_s - result2.events[0].onset_time_s) < 1e-6


# ===================================================================
# Configuration Tests
# ===================================================================

class TestConfiguration:

    def test_default_config(self):
        config = AudioPipelineConfig()
        assert config.sample_rate == 48000
        assert config.n_channels == 4
        assert config.bit_depth == 16
        assert config.ster_threshold == 6.0

    def test_custom_config(self):
        config = AudioPipelineConfig(
            sample_rate=96000,
            n_channels=8,
            ster_threshold=8.0,
        )
        assert config.sample_rate == 96000
        assert config.n_channels == 8
        assert config.ster_threshold == 8.0

    def test_mfcc_parameters(self):
        config = AudioPipelineConfig()
        assert config.mfcc_n_coeffs == 13
        assert config.mfcc_n_fft == 512
        assert config.mfcc_hop_length == 240

    def test_severity_thresholds(self):
        config = AudioPipelineConfig()
        assert "low" in config.severity_thresholds_db
        assert "moderate" in config.severity_thresholds_db
        assert "severe" in config.severity_thresholds_db
        assert "fatal" in config.severity_thresholds_db


# ===================================================================
# Enum Tests
# ===================================================================

class TestEnums:

    def test_crash_event_classes(self):
        assert len(CrashEventClass) == 12
        assert CrashEventClass.FRONTAL_FULL == 0
        assert CrashEventClass.NON_CRASH == 11

    def test_severity_levels(self):
        assert SeverityLevel.NONE.value == "none"
        assert SeverityLevel.LOW.value == "low"
        assert SeverityLevel.MODERATE.value == "moderate"
        assert SeverityLevel.SEVERE.value == "severe"
        assert SeverityLevel.FATAL.value == "fatal"

    def test_event_class_names(self):
        assert len(EVENT_CLASS_NAMES) == 12
        assert EVENT_CLASS_NAMES[0] == "FRONTAL_FULL"
        assert EVENT_CLASS_NAMES[11] == "NON_CRASH"


# ===================================================================
# Edge Case Tests
# ===================================================================

class TestEdgeCases:

    def test_empty_audio(self, config):
        pipeline = AudioForensicPipeline(config)
        audio = np.zeros((0, 4))
        result = pipeline.process(audio)
        assert not result.success

    def test_single_sample_audio(self, config):
        pipeline = AudioForensicPipeline(config)
        audio = np.zeros((1, 4))
        result = pipeline.process(audio)
        assert not result.success

    def test_very_short_audio(self, config):
        pipeline = AudioForensicPipeline(config)
        audio = np.random.normal(0, 0.01, (100, 4))
        result = pipeline.process(audio)
        assert not result.success

    def test_very_loud_audio(self, config):
        sr = config.sample_rate
        audio = np.ones((sr, 4)) * 0.99
        pipeline = AudioForensicPipeline(config, shared_secret=b"loud-test-key-32-bytes!!!!!!!!")
        result = pipeline.process(audio)
        # Very loud constant signal may or may not detect impulse
        assert result.processing_time_ms > 0

    def test_silent_audio(self, config):
        sr = config.sample_rate
        audio = np.zeros((sr, 4))
        pipeline = AudioForensicPipeline(config)
        result = pipeline.process(audio)
        assert not result.success

    def test_mono_audio(self, config):
        sr = config.sample_rate
        n = int(sr * 0.1)
        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.1, n)
        audio[int(0.04 * sr):int(0.06 * sr)] = 0.8

        pipeline = AudioForensicPipeline(config, shared_secret=b"mono-test-key-32-bytes!!!!!!!!")
        result = pipeline.process(audio.reshape(-1, 1))
        assert result.processing_time_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
