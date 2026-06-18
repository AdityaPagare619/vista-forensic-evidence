"""
VISTA 2.0 — Visual Analytics Pipeline Test Suite (Layer 6)

Comprehensive tests covering:
  1. Multi-camera capture management
  2. Burst capture (60fps, 2 seconds)
  3. Frame catalog and timestamps
  4. Image quality metrics (blur, exposure, noise)
  5. Key frame detection
  6. Evidence package with hash chain
  7. Tamper detection
  8. Performance benchmarks

Run: python -m pytest test_visual.py -v
"""

import hashlib
import time

import numpy as np
import pytest

from vista_hil.visual_pipeline import (
    CameraConfig,
    CameraPosition,
    Frame,
    FrameCatalog,
    FrameType,
    ImageQualityAnalyzer,
    KeyFrameDetector,
    KeyFrameReason,
    VisualEvidencePackage,
    VisualForensicPipeline,
    VisualPipelineConfig,
    FRONT_CAMERA_ID,
    FRONT_RESOLUTION,
    REAR_CAMERA_ID,
    REAR_RESOLUTION,
    BURST_DURATION_S,
    BURST_FPS,
    BURST_FRAME_COUNT,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def config():
    """Standard pipeline configuration."""
    return VisualPipelineConfig()


@pytest.fixture
def pipeline(config):
    """Initialized pipeline with test HMAC key."""
    return VisualForensicPipeline(config)


@pytest.fixture
def sample_image():
    """Generate a synthetic sharp image for testing."""
    rng = np.random.default_rng(42)
    return rng.normal(128, 30, (216, 384, 3)).astype(np.uint8)


@pytest.fixture
def blurry_image():
    """Generate a synthetic blurry image (uniform)."""
    return np.ones((216, 384, 3), dtype=np.uint8) * 128


@pytest.fixture
def dark_image():
    """Generate a dark (underexposed) image."""
    rng = np.random.default_rng(42)
    return rng.normal(20, 10, (216, 384, 3)).astype(np.uint8)


@pytest.fixture
def bright_image():
    """Generate a bright (overexposed) image."""
    rng = np.random.default_rng(42)
    return rng.normal(240, 10, (216, 384, 3)).astype(np.uint8)


@pytest.fixture
def noisy_image():
    """Generate a high-noise image."""
    rng = np.random.default_rng(42)
    return rng.normal(128, 80, (216, 384, 3)).astype(np.uint8)


# ===================================================================
# Configuration Tests
# ===================================================================

class TestConfiguration:

    def test_default_config(self):
        config = VisualPipelineConfig()
        assert config.front_camera.camera_id == FRONT_CAMERA_ID
        assert config.rear_camera.camera_id == REAR_CAMERA_ID
        assert config.front_camera.resolution == FRONT_RESOLUTION
        assert config.rear_camera.resolution == REAR_RESOLUTION
        assert config.pre_crash_buffer_s == 5.0

    def test_custom_config(self):
        config = VisualPipelineConfig(
            pre_crash_buffer_s=10.0,
            quality_blur_threshold=200.0,
        )
        assert config.pre_crash_buffer_s == 10.0
        assert config.quality_blur_threshold == 200.0

    def test_camera_burst_frame_count(self):
        cam = CameraConfig(
            camera_id="test",
            position=CameraPosition.FRONT,
            resolution=(1920, 1080),
            burst_fps=60,
            burst_duration_s=2.0,
        )
        assert cam.burst_frame_count == 120

    def test_camera_total_pixels(self):
        cam = CameraConfig(
            camera_id="test",
            position=CameraPosition.FRONT,
            resolution=(3840, 2160),
        )
        assert cam.total_pixels == 3840 * 2160


# ===================================================================
# Recording Lifecycle Tests
# ===================================================================

class TestRecordingLifecycle:

    def test_start_stop_recording(self, pipeline):
        pipeline.start_recording("test-event")
        assert pipeline._recording
        assert pipeline._event_start_time is not None

        pipeline.stop_recording()
        assert not pipeline._recording
        assert not pipeline._burst_active

    def test_recording_clears_catalogs(self, pipeline):
        pipeline.start_recording("event-1")
        pipeline.capture_pre_crash_frames(5)

        # Start new event should clear old frames
        pipeline.start_recording("event-2")
        for catalog in pipeline.get_all_catalogs().values():
            assert catalog.frame_count == 0

    def test_event_id_propagated(self, pipeline):
        pipeline.start_recording("my-event-id")
        pipeline.capture_pre_crash_frames(3)

        for catalog in pipeline.get_all_catalogs().values():
            assert catalog.event_id == "my-event-id"

    def test_stop_recording_clears_burst(self, pipeline):
        pipeline.start_recording("test")
        pipeline._burst_active = True
        pipeline.stop_recording()
        assert not pipeline._burst_active


# ===================================================================
# Pre-Crash Capture Tests
# ===================================================================

class TestPreCrashCapture:

    def test_captures_correct_frame_count(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(n_frames=15)

        for cam_id, catalog in pipeline.get_all_catalogs().items():
            assert catalog.frame_count == 15

    def test_frames_are_pre_crash_type(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(n_frames=5)

        for catalog in pipeline.get_all_catalogs().values():
            for frame in catalog.frames:
                assert frame.frame_type == FrameType.PRE_CRASH

    def test_frame_timestamps_are_monotonic(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(n_frames=20)

        for catalog in pipeline.get_all_catalogs().values():
            timestamps = [f.timestamp_s for f in catalog.frames]
            assert timestamps == sorted(timestamps), "Timestamps not monotonic"

    def test_frame_ids_unique(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(n_frames=10)

        for catalog in pipeline.get_all_catalogs().values():
            ids = [f.frame_id for f in catalog.frames]
            assert len(ids) == len(set(ids)), "Duplicate frame IDs"

    def test_no_capture_when_not_recording(self, pipeline):
        pipeline.capture_pre_crash_frames(n_frames=5)
        for catalog in pipeline.get_all_catalogs().values():
            assert catalog.frame_count == 0

    def test_frame_counter_increments(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(n_frames=5)
        counters_before = dict(pipeline._frame_counter)

        pipeline.capture_pre_crash_frames(n_frames=3)
        for cam_id in counters_before:
            assert pipeline._frame_counter[cam_id] == counters_before[cam_id] + 3


# ===================================================================
# Burst Capture Tests
# ===================================================================

class TestBurstCapture:

    def test_burst_captures_correct_count(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(10)
        pipeline.trigger_burst()

        for cam_id, catalog in pipeline.get_all_catalogs().items():
            expected = 10 + BURST_FRAME_COUNT
            assert catalog.frame_count == expected, \
                f"{cam_id}: expected {expected}, got {catalog.frame_count}"

    def test_burst_first_frame_is_crash_onset(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            # Frame at index 5 (after 5 pre-crash) should be crash onset
            burst_start = catalog.frames[5]
            assert burst_start.frame_type == FrameType.CRASH_ONSET

    def test_burst_post_crash_frames(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            post_crash = catalog.post_crash_frames
            # First burst frame is CRASH_ONSET, rest are POST_CRASH
            assert len(post_crash) == BURST_FRAME_COUNT - 1

    def test_burst_timestamps_within_duration(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            burst_frames = [f for f in catalog.frames
                           if f.frame_type != FrameType.PRE_CRASH]
            if burst_frames:
                t_first = burst_frames[0].timestamp_s
                t_last = burst_frames[-1].timestamp_s
                duration = t_last - t_first
                # Allow some tolerance for simulation overhead
                assert duration <= BURST_DURATION_S + 0.1, \
                    f"Burst duration {duration:.3f}s exceeds {BURST_DURATION_S}s"

    def test_burst_sets_catalog_flag(self, pipeline):
        pipeline.start_recording("test")
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            assert not catalog.burst_active  # Should be False after burst completes

    def test_burst_without_recording(self, pipeline):
        # Should not crash
        pipeline.trigger_burst()
        for catalog in pipeline.get_all_catalogs().values():
            assert catalog.frame_count == 0

    def test_burst_frame_ids_sequential(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            ids = [f.frame_id for f in catalog.frames]
            assert len(ids) == len(set(ids)), "Duplicate frame IDs in burst"


# ===================================================================
# Image Quality Metrics Tests
# ===================================================================

class TestImageQualityAnalyzer:

    def test_blur_score_sharp高于blurry(self, config, sample_image, blurry_image):
        analyzer = ImageQualityAnalyzer(config)
        sharp_blur = analyzer.compute_blur_score(sample_image)
        blurry_blur = analyzer.compute_blur_score(blurry_image)
        assert sharp_blur > blurry_blur

    def test_blur_score_positive(self, config, sample_image):
        analyzer = ImageQualityAnalyzer(config)
        score = analyzer.compute_blur_score(sample_image)
        assert score >= 0

    def test_blur_score_grayscale(self, config):
        analyzer = ImageQualityAnalyzer(config)
        gray = np.random.default_rng(42).normal(128, 30, (216, 384)).astype(np.uint8)
        score = analyzer.compute_blur_score(gray)
        assert score >= 0

    def test_exposure_bright_image(self, config, bright_image):
        analyzer = ImageQualityAnalyzer(config)
        exposure = analyzer.compute_exposure_score(bright_image)
        assert exposure["mean_brightness"] > 200
        assert exposure["overexposed_pct"] > 0

    def test_exposure_dark_image(self, config, dark_image):
        analyzer = ImageQualityAnalyzer(config)
        exposure = analyzer.compute_exposure_score(dark_image)
        assert exposure["mean_brightness"] < 50
        assert exposure["underexposed_pct"] > 0

    def test_exposure_normal_image(self, config, sample_image):
        analyzer = ImageQualityAnalyzer(config)
        exposure = analyzer.compute_exposure_score(sample_image)
        assert 80 < exposure["mean_brightness"] < 180

    def test_noise_score_noisy_image(self, config, noisy_image):
        analyzer = ImageQualityAnalyzer(config)
        noise = analyzer.compute_noise_score(noisy_image)
        assert noise > 0

    def test_noise_score_smooth_image(self, config):
        analyzer = ImageQualityAnalyzer(config)
        smooth = np.ones((216, 384, 3), dtype=np.uint8) * 128
        noise = analyzer.compute_noise_score(smooth)
        assert noise < 5.0  # Very low noise for uniform image

    def test_analyze_frame_returns_all_metrics(self, config, sample_image):
        analyzer = ImageQualityAnalyzer(config)
        result = analyzer.analyze_frame(sample_image)
        assert "blur_score" in result
        assert "exposure" in result
        assert "noise_score" in result
        assert "overall_quality" in result

    def test_overall_quality_range(self, config, sample_image):
        analyzer = ImageQualityAnalyzer(config)
        result = analyzer.analyze_frame(sample_image)
        assert 0 <= result["overall_quality"] <= 100


# ===================================================================
# Key Frame Detection Tests
# ===================================================================

class TestKeyFrameDetector:

    def _build_catalog_with_frames(self):
        """Helper to build a catalog with pre/post crash frames."""
        catalog = FrameCatalog(camera_id="test_cam", event_id="test")
        rng = np.random.default_rng(42)

        # 10 pre-crash frames
        for i in range(10):
            quality = {"blur_score": 50 + i * 10, "noise_score": 10,
                       "exposure": {"mean_brightness": 128}, "overall_quality": 30 + i * 5}
            frame = Frame(
                frame_id=f"pre_{i}", camera_id="test_cam",
                timestamp_s=i * 0.033, frame_number=i,
                resolution=(1920, 1080), frame_type=FrameType.PRE_CRASH,
                quality_metrics=quality,
            )
            catalog.frames.append(frame)

        # 5 post-crash frames
        for i in range(5):
            quality = {"blur_score": 100 + i * 20, "noise_score": 15,
                       "exposure": {"mean_brightness": 120}, "overall_quality": 40 + i * 10}
            frame = Frame(
                frame_id=f"post_{i}", camera_id="test_cam",
                timestamp_s=0.33 + i * 0.016, frame_number=10 + i,
                resolution=(1920, 1080), frame_type=FrameType.POST_CRASH,
                quality_metrics=quality,
            )
            catalog.frames.append(frame)

        return catalog

    def test_detects_first_post_crash(self):
        detector = KeyFrameDetector()
        catalog = self._build_catalog_with_frames()
        key_frames = detector.detect_key_frames(catalog)

        reasons = [kf.key_frame_reason for kf in key_frames]
        assert KeyFrameReason.FIRST_POST_CRASH in reasons

    def test_detects_best_quality(self):
        detector = KeyFrameDetector()
        catalog = self._build_catalog_with_frames()
        key_frames = detector.detect_key_frames(catalog)

        reasons = [kf.key_frame_reason for kf in key_frames]
        assert KeyFrameReason.BEST_QUALITY in reasons

    def test_detects_scene_context(self):
        detector = KeyFrameDetector()
        catalog = self._build_catalog_with_frames()
        key_frames = detector.detect_key_frames(catalog)

        reasons = [kf.key_frame_reason for kf in key_frames]
        assert KeyFrameReason.SCENE_CONTEXT in reasons

    def test_key_frames_marked_correctly(self):
        detector = KeyFrameDetector()
        catalog = self._build_catalog_with_frames()
        key_frames = detector.detect_key_frames(catalog)

        for kf in key_frames:
            assert kf.is_key_frame
            assert kf.key_frame_reason is not None

    def test_no_key_frames_empty_catalog(self):
        detector = KeyFrameDetector()
        catalog = FrameCatalog(camera_id="empty", event_id="test")
        key_frames = detector.detect_key_frames(catalog)
        assert len(key_frames) == 0

    def test_no_post_crash_no_first_frame(self):
        detector = KeyFrameDetector()
        catalog = FrameCatalog(camera_id="test", event_id="test")
        # Only pre-crash frames
        for i in range(5):
            frame = Frame(
                frame_id=f"pre_{i}", camera_id="test",
                timestamp_s=i * 0.033, frame_number=i,
                resolution=(1920, 1080), frame_type=FrameType.PRE_CRASH,
                quality_metrics={"overall_quality": 30},
            )
            catalog.frames.append(frame)

        key_frames = detector.detect_key_frames(catalog)
        reasons = [kf.key_frame_reason for kf in key_frames]
        assert KeyFrameReason.FIRST_POST_CRASH not in reasons


# ===================================================================
# Frame Catalog Tests
# ===================================================================

class TestFrameCatalog:

    def test_frame_count(self):
        catalog = FrameCatalog(camera_id="cam", event_id="ev")
        assert catalog.frame_count == 0

        catalog.frames.append(Frame(
            frame_id="f1", camera_id="cam", timestamp_s=0.0,
            frame_number=0, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH,
        ))
        assert catalog.frame_count == 1

    def test_key_frames_property(self):
        catalog = FrameCatalog(camera_id="cam", event_id="ev")
        catalog.frames.append(Frame(
            frame_id="f1", camera_id="cam", timestamp_s=0.0,
            frame_number=0, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH, is_key_frame=True,
        ))
        catalog.frames.append(Frame(
            frame_id="f2", camera_id="cam", timestamp_s=0.033,
            frame_number=1, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH, is_key_frame=False,
        ))
        assert len(catalog.key_frames) == 1

    def test_pre_crash_frames_property(self):
        catalog = FrameCatalog(camera_id="cam", event_id="ev")
        catalog.frames.append(Frame(
            frame_id="f1", camera_id="cam", timestamp_s=0.0,
            frame_number=0, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH,
        ))
        catalog.frames.append(Frame(
            frame_id="f2", camera_id="cam", timestamp_s=0.1,
            frame_number=1, resolution=(1920, 1080),
            frame_type=FrameType.POST_CRASH,
        ))
        assert len(catalog.pre_crash_frames) == 1
        assert len(catalog.post_crash_frames) == 1

    def test_get_frame_by_id(self):
        catalog = FrameCatalog(camera_id="cam", event_id="ev")
        target = Frame(
            frame_id="target", camera_id="cam", timestamp_s=0.0,
            frame_number=0, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH,
        )
        catalog.frames.append(target)
        catalog.frames.append(Frame(
            frame_id="other", camera_id="cam", timestamp_s=0.033,
            frame_number=1, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH,
        ))

        assert catalog.get_frame_by_id("target") is target
        assert catalog.get_frame_by_id("nonexistent") is None

    def test_to_dict(self):
        catalog = FrameCatalog(camera_id="cam", event_id="ev")
        catalog.frames.append(Frame(
            frame_id="f1", camera_id="cam", timestamp_s=0.0,
            frame_number=0, resolution=(1920, 1080),
            frame_type=FrameType.PRE_CRASH,
        ))
        d = catalog.to_dict()
        assert d["camera_id"] == "cam"
        assert d["frame_count"] == 1
        assert len(d["frames"]) == 1


# ===================================================================
# Frame Data Tests
# ===================================================================

class TestFrame:

    def test_to_dict(self):
        frame = Frame(
            frame_id="f_001", camera_id="cam_front",
            timestamp_s=1.234, frame_number=42,
            resolution=(3840, 2160),
            frame_type=FrameType.CRASH_ONSET,
            is_key_frame=True,
            key_frame_reason=KeyFrameReason.FIRST_POST_CRASH,
        )
        d = frame.to_dict()
        assert d["frame_id"] == "f_001"
        assert d["frame_type"] == "crash_onset"
        assert d["is_key_frame"] is True
        assert d["key_frame_reason"] == "first_post_crash"

    def test_to_dict_no_key_frame(self):
        frame = Frame(
            frame_id="f_002", camera_id="cam_rear",
            timestamp_s=2.0, frame_number=0,
            resolution=(2560, 1440),
            frame_type=FrameType.PRE_CRASH,
        )
        d = frame.to_dict()
        assert d["is_key_frame"] is False
        assert d["key_frame_reason"] is None


# ===================================================================
# Evidence Package Tests
# ===================================================================

class TestEvidencePackage:

    def test_package_creation(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        pipeline.trigger_burst()

        package = pipeline.generate_evidence_package("test-001", "device-01")
        assert package.evidence_id.startswith("vis-")
        assert package.event_id == "test-001"
        assert package.device_id == "device-01"
        assert package.total_frames > 0

    def test_sha256_format(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        assert len(package.sha256_hash) == 64
        assert all(c in '0123456789abcdef' for c in package.sha256_hash)

    def test_sha3_format(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        assert len(package.sha3_hash) == 64
        assert all(c in '0123456789abcdef' for c in package.sha3_hash)

    def test_hmac_format(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        assert len(package.hmac_signature) == 64
        assert all(c in '0123456789abcdef' for c in package.hmac_signature)

    def test_dual_hash_different(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        assert package.sha256_hash != package.sha3_hash

    def test_key_frames_included(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(10)
        pipeline.trigger_burst()

        package = pipeline.generate_evidence_package("ev-001", "dev-01")
        assert len(package.key_frames) >= 1  # At least first post-crash

    def test_catalog_summary_included(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        assert FRONT_CAMERA_ID in package.frame_catalog_summary
        assert REAR_CAMERA_ID in package.frame_catalog_summary

    def test_quality_summary_included(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        assert FRONT_CAMERA_ID in package.quality_summary
        assert REAR_CAMERA_ID in package.quality_summary
        assert "overall" in package.quality_summary

    def test_to_dict(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        d = package.to_dict()
        assert "evidence_id" in d
        assert "sha256_hash" in d
        assert "key_frames" in d


# ===================================================================
# Evidence Verification Tests
# ===================================================================

class TestEvidenceVerification:

    def test_valid_package_passes(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        result = pipeline.verify_evidence_package(package)
        assert result["valid"]
        assert result["checks"]["sha256"]
        assert result["checks"]["sha3"]
        assert result["checks"]["hmac"]
        assert result["checks"]["timestamp"]

    def test_tampered_total_frames_fails(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        package.total_frames = 99999
        result = pipeline.verify_evidence_package(package)
        assert not result["valid"]
        assert not result["checks"]["sha256"]

    def test_tampered_event_id_fails(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        package.event_id = "tampered-event"
        result = pipeline.verify_evidence_package(package)
        assert not result["valid"]

    def test_tampered_device_id_fails(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        package.device_id = "wrong-device"
        result = pipeline.verify_evidence_package(package)
        assert not result["valid"]

    def test_tampered_key_frames_fails(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        package.key_frames = []
        result = pipeline.verify_evidence_package(package)
        assert not result["valid"]

    def test_tampered_sha256_fails(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        package.sha256_hash = "a" * 64
        result = pipeline.verify_evidence_package(package)
        assert not result["valid"]
        assert not result["checks"]["sha256"]

    def test_tampered_hmac_fails(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(3)
        package = pipeline.generate_evidence_package("ev-001", "dev-01")

        package.hmac_signature = "b" * 64
        result = pipeline.verify_evidence_package(package)
        assert not result["valid"]
        assert not result["checks"]["hmac"]


# ===================================================================
# Quality Summary Tests
# ===================================================================

class TestQualitySummary:

    def test_summary_structure(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(10)
        pipeline.trigger_burst()

        summary = pipeline.compute_quality_summary()
        assert FRONT_CAMERA_ID in summary
        assert REAR_CAMERA_ID in summary
        assert "overall" in summary

    def test_summary_has_metrics(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(5)

        summary = pipeline.compute_quality_summary()
        for cam_id in [FRONT_CAMERA_ID, REAR_CAMERA_ID]:
            assert summary[cam_id]["frame_count"] == 5
            assert "blur_mean" in summary[cam_id]
            assert "noise_mean" in summary[cam_id]
            assert "exposure_mean" in summary[cam_id]

    def test_summary_empty_catalog(self, pipeline):
        summary = pipeline.compute_quality_summary()
        for cam_id in [FRONT_CAMERA_ID, REAR_CAMERA_ID]:
            assert summary[cam_id]["frame_count"] == 0


# ===================================================================
# Integration Tests
# ===================================================================

class TestPipelineIntegration:

    def test_full_crash_workflow(self, pipeline):
        """Test complete workflow: record → pre-crash → burst → evidence."""
        pipeline.start_recording("integration-001")

        # Simulate pre-crash recording
        pipeline.capture_pre_crash_frames(n_frames=30)

        # Crash trigger
        pipeline.trigger_burst()

        # Stop and generate evidence
        pipeline.stop_recording()
        package = pipeline.generate_evidence_package(
            event_id="integration-001",
            device_id="vista-sim-integration",
        )

        # 30 pre-crash + 120 burst = 150 frames per camera, 2 cameras = 300
        assert package.total_frames == (30 + BURST_FRAME_COUNT) * 2
        verification = pipeline.verify_evidence_package(package)
        assert verification["valid"]

    def test_multiple_events(self):
        """Test multiple sequential events."""
        config = VisualPipelineConfig()
        pipeline = VisualForensicPipeline(config)

        for event_num in range(3):
            pipeline.start_recording(f"event-{event_num}")
            pipeline.capture_pre_crash_frames(5)
            pipeline.trigger_burst()
            pipeline.stop_recording()

            package = pipeline.generate_evidence_package(
                f"event-{event_num}", "device-01"
            )
            verification = pipeline.verify_evidence_package(package)
            assert verification["valid"], f"Event {event_num} failed verification"

    def test_deterministic_output(self):
        """Same inputs should produce same hashes when timestamps are equal."""
        from unittest.mock import patch

        config = VisualPipelineConfig()
        pipeline1 = VisualForensicPipeline(config)
        pipeline2 = VisualForensicPipeline(config)

        fixed_time = 1700000000.0
        with patch('vista_hil.visual_pipeline.time') as mock_time:
            mock_time.time.return_value = fixed_time

            pipeline1.start_recording("det-test")
            pipeline1.capture_pre_crash_frames(5)
            pipeline1.trigger_burst()

            pipeline2.start_recording("det-test")
            pipeline2.capture_pre_crash_frames(5)
            pipeline2.trigger_burst()

            pkg1 = pipeline1.generate_evidence_package("det-test", "dev-01")
            pkg2 = pipeline2.generate_evidence_package("det-test", "dev-01")

        assert pkg1.sha256_hash == pkg2.sha256_hash
        assert pkg1.sha3_hash == pkg2.sha3_hash

    def test_pipeline_latency_benchmark(self, pipeline):
        """Pipeline operations should complete within time bounds."""
        pipeline.start_recording("bench")

        t0 = time.perf_counter()
        pipeline.capture_pre_crash_frames(10)
        capture_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pipeline.trigger_burst()
        burst_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pipeline.detect_key_frames()
        detect_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pkg = pipeline.generate_evidence_package("bench", "dev-01")
        gen_ms = (time.perf_counter() - t0) * 1000

        assert capture_ms < 5000, f"Pre-crash capture too slow: {capture_ms:.1f}ms"
        assert burst_ms < 10000, f"Burst capture too slow: {burst_ms:.1f}ms"
        assert detect_ms < 500, f"Key frame detection too slow: {detect_ms:.1f}ms"
        assert gen_ms < 2000, f"Package generation too slow: {gen_ms:.1f}ms"


# ===================================================================
# Edge Case Tests
# ===================================================================

class TestEdgeCases:

    def test_single_frame_capture(self, pipeline):
        pipeline.start_recording("test")
        pipeline.capture_pre_crash_frames(1)
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            assert catalog.frame_count == 1 + BURST_FRAME_COUNT

    def test_zero_pre_crash_frames(self, pipeline):
        pipeline.start_recording("test")
        # No pre-crash frames
        pipeline.trigger_burst()

        for catalog in pipeline.get_all_catalogs().values():
            assert catalog.frame_count == BURST_FRAME_COUNT

    def test_burst_without_pre_crash(self, pipeline):
        pipeline.start_recording("test")
        pipeline.trigger_burst()
        pipeline.stop_recording()

        package = pipeline.generate_evidence_package("ev-001", "dev-01")
        verification = pipeline.verify_evidence_package(package)
        assert verification["valid"]

    def test_evidence_package_no_key_frames(self):
        """Evidence package should work even if no key frames detected."""
        config = VisualPipelineConfig()
        pipeline = VisualForensicPipeline(config)
        pipeline.start_recording("test")
        # Single pre-crash frame, no burst
        pipeline.capture_pre_crash_frames(1)

        package = pipeline.generate_evidence_package("ev-001", "dev-01")
        # Should still be valid
        verification = pipeline.verify_evidence_package(package)
        assert verification["valid"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
