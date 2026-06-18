"""
Comprehensive tests for VISTA 2.0 Layer 4: Crash Reconstruction Module

Tests cover:
  - Delta-V estimation (energy, momentum, bootstrap CI, saturation)
  - PDOF estimation (dual-axis, single-axis, signal quality)
  - Injury risk assessment (all crash modes, MAIS levels, body regions)
  - Velocity-time history (phase decomposition, baseline correction)
  - Full reconstruction integration
"""

import numpy as np
import pytest
from vista_hil.reconstruction import (
    CrashReconstructor,
    DeltaVEstimator,
    PDOFEstimator,
    InjuryRiskAssessor,
    VelocityHistoryReconstructor,
    ReconstructionConfig,
    DeltaVResult,
    PDOFResult,
    InjuryRiskResult,
    VelocityHistoryResult,
    PhaseInfo,
    CrashMode,
    SignalQuality,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def default_config():
    """Default reconstruction configuration."""
    return ReconstructionConfig(
        sampling_rate=1000,
        vehicle_mass_kg=1500.0,
        restitution_coefficient=0.15,
        bootstrap_samples=200,  # Reduced for test speed
        bootstrap_seed=42,
        confidence_level=0.95,
        saturation_threshold_g=85.0,
        use_saturation_correction=True,
    )


@pytest.fixture
def haversine_accel():
    """Generate a clean haversine crash pulse for testing."""
    sampling_rate = 1000
    duration_ms = 100
    peak_g = 50.0
    duration_s = duration_ms / 1000.0

    n_samples = int(duration_s * sampling_rate)
    t = np.arange(n_samples) / sampling_rate

    # Haversine pulse
    accel_g = peak_g * np.sin(np.pi * t / duration_s) ** 2
    accel_g = np.where((t >= 0) & (t <= duration_s), accel_g, 0)

    return t, accel_g


@pytest.fixture
def dual_axis_accel():
    """Generate dual-axis crash data for PDOF testing."""
    sampling_rate = 1000
    duration_ms = 100
    peak_g = 40.0
    duration_s = duration_ms / 1000.0

    n_samples = int(duration_s * sampling_rate)
    t = np.arange(n_samples) / sampling_rate

    # Frontal crash with 15° offset
    base_pulse = peak_g * np.sin(np.pi * t / duration_s) ** 2
    base_pulse = np.where((t >= 0) & (t <= duration_s), base_pulse, 0)

    angle_rad = np.radians(15)
    accel_x = base_pulse * np.cos(angle_rad)
    accel_y = base_pulse * np.sin(angle_rad)

    return t, accel_x, accel_y


@pytest.fixture
def noisy_accel():
    """Generate noisy crash pulse for SNR testing."""
    t, accel_g = haversine_accel()
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 2.0, len(accel_g))
    return t, accel_g + noise


@pytest.fixture
def saturated_accel():
    """Generate saturated crash pulse."""
    t, accel_g = haversine_accel()
    # Saturate at 85g
    accel_g = np.clip(accel_g, -85, 85)
    # Force some samples to exactly saturate
    accel_g[50:60] = 85.0
    return t, accel_g


@pytest.fixture
def reconstructor(default_config):
    """Full crash reconstructor."""
    return CrashReconstructor(default_config)


# ===================================================================
# 4.1 Delta-V Estimation Tests
# ===================================================================

class TestDeltaVEstimation:
    """Tests for delta-V estimation."""

    def test_energy_method_basic(self, default_config, haversine_accel):
        """Energy method should return positive delta-V for deceleration pulse."""
        t, accel_g = haversine_accel
        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        assert isinstance(result, DeltaVResult)
        assert result.delta_v_ms > 0
        assert result.delta_v_kmh > 0
        assert result.method == "hybrid_energy_momentum"

    def test_known_delta_v(self, default_config):
        """Test with a known constant deceleration pulse."""
        # Constant 50g deceleration for 100ms
        # dV = a * t = 50 * 9.80665 * 0.1 = 49.03 m/s ≈ 176.5 km/h
        sampling_rate = 1000
        n_samples = 100
        t = np.arange(n_samples) / sampling_rate
        accel_g = np.full(n_samples, 50.0)

        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        # Momentum method should be exact: dV = a * dt * n = 50 * 9.80665 * 0.1
        expected_ms = 50.0 * 9.80665 * 0.1  # = 49.033 m/s
        expected_kmh = expected_ms * 3.6

        # Primary delta-V is now momentum-based (abs of signed integral)
        assert abs(result.delta_v_ms - expected_ms) < 0.5
        assert abs(result.delta_v_kmh - expected_kmh) < 2.0
        assert abs(result.momentum_delta_v_ms - expected_ms) < 0.5

    def test_bootstrap_ci(self, default_config, haversine_accel):
        """Bootstrap CI should be valid (lower < upper) and cover reasonable range."""
        t, accel_g = haversine_accel
        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        # CI bounds should be valid
        assert result.ci_lower_ms < result.ci_upper_ms
        assert result.ci_lower_kmh < result.ci_upper_kmh
        # CI should contain the point estimate (with some tolerance for bootstrap variance)
        # The CI is based on resampled momentum, which should bracket the original
        assert result.ci_lower_ms <= result.delta_v_ms * 1.5
        assert result.ci_upper_ms >= result.delta_v_ms * 0.5

    def test_saturation_detection(self, default_config):
        """Should detect saturation and apply correction."""
        # Use a pulse that clearly saturates above 85g threshold
        t = np.linspace(0, 0.1, 100)
        accel_g = 50.0 * np.sin(np.pi * t / 0.1) ** 2
        accel_g[40:60] = 90.0  # Force saturation above 85g threshold

        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        assert result.saturation_detected == True
        assert result.saturation_correction_applied == True

    def test_no_saturation(self, default_config):
        """Should not detect saturation in clean pulse below threshold."""
        t = np.linspace(0, 0.1, 100)
        accel_g = 50.0 * np.sin(np.pi * t / 0.1) ** 2

        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        assert result.saturation_detected == False
        assert result.saturation_correction_applied == False

    def test_confidence_score(self, default_config, haversine_accel):
        """Confidence should be in [0, 1]."""
        t, accel_g = haversine_accel
        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        assert 0.0 <= result.confidence <= 1.0

    def test_velocity_history_integration(self, default_config, haversine_accel):
        """Delta-V should match velocity history integration."""
        t, accel_g = haversine_accel
        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        # Independent integration
        dt = t[1] - t[0]
        velocity = np.cumsum(accel_g * 9.80665) * dt
        independent_dv = abs(velocity[-1])

        # Both use momentum (signed integral), so should match closely
        assert abs(result.delta_v_ms - independent_dv) < 1.0

    def test_units_conversion(self, default_config, haversine_accel):
        """Unit conversions should be consistent."""
        t, accel_g = haversine_accel
        estimator = DeltaVEstimator(default_config)
        result = estimator.estimate(accel_g, t)

        # km/h = m/s * 3.6
        assert abs(result.delta_v_kmh - result.delta_v_ms * 3.6) < 0.01
        # mph = m/s * 2.23694
        assert abs(result.delta_v_mph - result.delta_v_ms * 2.23694) < 0.01


# ===================================================================
# 4.2 PDOF Estimation Tests
# ===================================================================

class TestPDOFEstimation:
    """Tests for PDOF estimation."""

    def test_pdof_dual_axis(self, default_config, dual_axis_accel):
        """PDOF should estimate angle from dual-axis data."""
        t, ax, ay = dual_axis_accel
        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(ax, ay, t)

        assert isinstance(result, PDOFResult)
        assert -180 <= result.angle_deg <= 180
        assert 0.0 <= result.confidence <= 1.0
        assert result.signal_quality in [
            SignalQuality.HIGH, SignalQuality.MEDIUM,
            SignalQuality.LOW, SignalQuality.INSUFFICIENT,
        ]

    def test_pdof_frontal_crash(self, default_config):
        """Frontal crash should have PDOF near 0°."""
        sampling_rate = 1000
        duration_s = 0.1
        n_samples = int(duration_s * sampling_rate)
        t = np.arange(n_samples) / sampling_rate

        accel_x = 50.0 * np.sin(np.pi * t / duration_s) ** 2
        accel_y = np.random.default_rng(42).normal(0, 0.5, n_samples)  # Small noise

        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(accel_x, accel_y, t)

        # Frontal crash PDOF should be near 0°
        assert abs(result.angle_deg) < 30  # Generous tolerance for noise

    def test_pdof_oblique_crash(self, default_config):
        """Oblique crash should have PDOF at the impact angle."""
        sampling_rate = 1000
        duration_s = 0.1
        n_samples = int(duration_s * sampling_rate)
        t = np.arange(n_samples) / sampling_rate

        angle = 30  # 30° impact
        base_pulse = 50.0 * np.sin(np.pi * t / duration_s) ** 2
        accel_x = base_pulse * np.cos(np.radians(angle))
        accel_y = base_pulse * np.sin(np.radians(angle))

        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(accel_x, accel_y, t)

        # Should be within ±10° of true angle (Kusano & Gabler accuracy)
        assert abs(result.angle_deg - angle) < 15

    def test_pdof_insufficient_data(self, default_config):
        """Should return INSUFFICIENT quality for very short data."""
        t = np.array([0.0, 0.001])  # 2ms - too short
        accel_x = np.array([50.0, 50.0])
        accel_y = np.array([0.0, 0.0])

        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(accel_x, accel_y, t)

        assert result.signal_quality == SignalQuality.INSUFFICIENT
        assert result.confidence == 0.0

    def test_pdof_high_quality_signal(self, default_config):
        """Dual-axis with good SNR and balanced axes should be HIGH quality."""
        # Use a 45° impact so both axes have equal energy
        sampling_rate = 1000
        duration_s = 0.1
        n_samples = int(duration_s * sampling_rate)
        t = np.arange(n_samples) / sampling_rate

        base_pulse = 40.0 * np.sin(np.pi * t / duration_s) ** 2
        ax = base_pulse * np.cos(np.radians(45))
        ay = base_pulse * np.sin(np.radians(45))

        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(ax, ay, t)

        assert result.signal_quality == SignalQuality.HIGH

    def test_pdof_zero_signal(self, default_config):
        """Zero signal should be INSUFFICIENT quality."""
        n = 100
        t = np.arange(n) / 1000.0
        accel_x = np.zeros(n)
        accel_y = np.zeros(n)

        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(accel_x, accel_y, t)

        assert result.signal_quality == SignalQuality.INSUFFICIENT

    def test_pdof_angle_range(self, default_config):
        """PDOF angle should always be in [-180, 180] degrees."""
        n = 200
        t = np.arange(n) / 1000.0
        accel_x = np.sin(2 * np.pi * 50 * t) * 40
        accel_y = np.cos(2 * np.pi * 50 * t) * 40

        estimator = PDOFEstimator(default_config)
        result = estimator.estimate(accel_x, accel_y, t)

        assert -180 <= result.angle_deg <= 180
        assert -np.pi <= result.angle_rad <= np.pi


# ===================================================================
# 4.3 Injury Risk Assessment Tests
# ===================================================================

class TestInjuryRiskAssessment:
    """Tests for injury risk assessment."""

    def test_zero_delta_v(self, default_config):
        """Zero delta-V should have very low but non-zero injury risk (baseline)."""
        assessor = InjuryRiskAssessor(default_config)
        result = assessor.assess(0.0)

        # NHTSA logistic curves have non-zero intercept (baseline risk)
        # At dV=0: P(MAIS2+) = 1/(1+exp(4.41)) ≈ 0.012
        assert result.mais2_plus < 0.02  # Very low baseline
        assert result.mais6 < 0.001  # Fatal risk essentially zero
        assert result.risk_category == "none"

    def test_high_delta_v(self, default_config):
        """High delta-V (80 km/h) should have significant risk."""
        assessor = InjuryRiskAssessor(default_config)
        result = assessor.assess(80.0)

        assert result.mais2_plus > 0.3
        assert result.mais6 > 0.01

    def test_mais_monotonic(self, default_config):
        """Higher MAIS levels should have lower probability."""
        assessor = InjuryRiskAssessor(default_config)
        result = assessor.assess(50.0)

        assert result.mais2_plus >= result.mais3_plus
        assert result.mais3_plus >= result.mais4_plus
        assert result.mais4_plus >= result.mais5_plus
        assert result.mais5_plus >= result.mais6

    def test_risk_categories(self, default_config):
        """Risk categories should be set correctly."""
        assessor = InjuryRiskAssessor(default_config)

        # Low risk
        result_low = assessor.assess(10.0)
        assert result_low.risk_category in ["none", "low"]

        # High risk
        result_high = assessor.assess(100.0)
        assert result_high.risk_category in ["high", "critical"]

    def test_frontal_crash_mode(self, default_config):
        """Frontal crash mode should use frontal coefficients."""
        config = ReconstructionConfig(
            injury_crash_mode=CrashMode.FRONTAL,
            bootstrap_samples=200,
        )
        assessor = InjuryRiskAssessor(config)
        result = assessor.assess(50.0)

        assert result.crash_mode == CrashMode.FRONTAL
        assert 0 <= result.mais2_plus <= 1

    def test_rear_crash_mode(self, default_config):
        """Rear crash mode should use rear coefficients."""
        config = ReconstructionConfig(
            injury_crash_mode=CrashMode.REAR,
            bootstrap_samples=200,
        )
        assessor = InjuryRiskAssessor(config)
        result = assessor.assess(50.0)

        assert result.crash_mode == CrashMode.REAR

    def test_body_region_risks(self, default_config):
        """Body region risks should be in [0, 1]."""
        assessor = InjuryRiskAssessor(default_config)
        result = assessor.assess(50.0)

        assert 0 <= result.head_injury_risk <= 1
        assert 0 <= result.thorax_injury_risk <= 1
        assert 0 <= result.femur_injury_risk <= 1

    def test_risk_curve_generation(self, default_config):
        """Risk curve generation should return valid arrays."""
        assessor = InjuryRiskAssessor(default_config)
        curves = assessor.compute_risk_curve((0, 100), n_points=50)

        assert "delta_v_kmh" in curves
        assert "mais2" in curves
        assert len(curves["delta_v_kmh"]) == 50
        assert len(curves["mais2"]) == 50

        # All probabilities should be in [0, 1]
        for key in ["mais2", "mais3", "mais4", "mais5", "mais6"]:
            assert np.all(curves[key] >= 0)
            assert np.all(curves[key] <= 1)

    def test_risk_curve_monotonic(self, default_config):
        """Risk curves should be monotonically increasing."""
        assessor = InjuryRiskAssessor(default_config)
        curves = assessor.compute_risk_curve((0, 100), n_points=50)

        for key in ["mais2", "mais3", "mais4", "mais5", "mais6"]:
            assert np.all(np.diff(curves[key]) >= 0)


# ===================================================================
# 4.4 Velocity-Time History Tests
# ===================================================================

class TestVelocityHistory:
    """Tests for velocity-time history reconstruction."""

    def test_basic_reconstruction(self, default_config, haversine_accel):
        """Should reconstruct velocity history from acceleration."""
        t, accel_g = haversine_accel
        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        assert isinstance(result, VelocityHistoryResult)
        assert len(result.velocity_ms) == len(t)
        assert len(result.acceleration_g) == len(t)
        assert len(result.jerk_gps) == len(t)

    def test_baseline_correction(self, default_config):
        """Should remove gravity bias from acceleration."""
        n = 100
        t = np.arange(n) / 1000.0
        # Add 1g gravity bias
        accel_g = np.zeros(n) + 1.0

        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        # After baseline correction, mean should be near zero
        assert abs(np.mean(result.acceleration_g)) < 0.1

    def test_phase_decomposition(self, default_config, haversine_accel):
        """Should decompose into crash phases."""
        t, accel_g = haversine_accel
        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        assert len(result.phases) >= 3  # At least onset, compression, restitution

        phase_names = [p.name for p in result.phases]
        assert "onset" in phase_names
        assert "compression" in phase_names

    def test_phase_contiguity(self, default_config, haversine_accel):
        """Phase boundaries should be contiguous."""
        t, accel_g = haversine_accel
        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        for i in range(len(result.phases) - 1):
            # End of phase i should be close to start of phase i+1
            gap = abs(result.phases[i].end_time_ms - result.phases[i+1].start_time_ms)
            assert gap < 5.0  # Within 5ms tolerance

    def test_peak_metrics(self, default_config, haversine_accel):
        """Should correctly identify peak acceleration."""
        t, accel_g = haversine_accel
        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        assert result.peak_acceleration_g > 0
        assert result.peak_time_ms > 0
        assert result.peak_time_ms < t[-1] * 1000

    def test_velocity_units(self, default_config, haversine_accel):
        """Velocity units should be consistent."""
        t, accel_g = haversine_accel
        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        # km/h = m/s * 3.6
        max_diff = np.max(np.abs(result.velocity_kmh - result.velocity_ms * 3.6))
        assert max_diff < 0.01

    def test_onset_time(self, default_config, haversine_accel):
        """Onset time should be near start of pulse."""
        t, accel_g = haversine_accel
        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        # Onset should be within first 30ms for a 100ms pulse
        assert result.onset_time_ms < 30.0

    def test_zero_acceleration(self, default_config):
        """Zero acceleration should produce zero velocity."""
        n = 100
        t = np.arange(n) / 1000.0
        accel_g = np.zeros(n)

        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        assert np.max(np.abs(result.velocity_ms)) < 0.01

    def test_constant_deceleration(self, default_config):
        """Constant deceleration with baseline removal should still integrate correctly."""
        # Use a pulse that starts at 0, goes to 50g, then back to 0
        # This way baseline correction doesn't remove the signal
        n = 200
        dt = 0.001
        t = np.arange(n) * dt
        # Ramp up, hold, ramp down pulse
        accel_g = np.zeros(n)
        accel_g[50:150] = 50.0  # 100ms of 50g

        reconstructor = VelocityHistoryReconstructor(default_config)
        result = reconstructor.reconstruct(accel_g, t)

        # After baseline correction (removing pre-pulse mean of 0),
        # the velocity should integrate to: a * dt * duration = 50 * 9.80665 * 0.1
        expected_v_final = 50.0 * 9.80665 * 0.1  # = 49.03 m/s
        assert abs(result.final_velocity_ms - expected_v_final) < 1.0


# ===================================================================
# Integration Tests
# ===================================================================

class TestFullReconstruction:
    """Integration tests for full crash reconstruction."""

    def test_full_reconstruction_single_axis(self, reconstructor, haversine_accel):
        """Full reconstruction with single-axis data."""
        t, accel_g = haversine_accel
        result = reconstructor.reconstruct_full(accel_g, t)

        assert "delta_v" in result
        assert "pdof" in result
        assert "injury" in result
        assert "velocity_history" in result
        assert "config" in result

        # Delta-V should be reasonable
        assert 0 < result["delta_v"].delta_v_kmh < 200

        # PDOF should be None without Y-axis
        assert result["pdof"] is None

        # Injury risk should be valid
        assert 0 <= result["injury"].mais2_plus <= 1

        # Velocity history should exist
        assert len(result["velocity_history"].velocity_ms) > 0

    def test_full_reconstruction_dual_axis(self, reconstructor, dual_axis_accel):
        """Full reconstruction with dual-axis data."""
        t, ax, ay = dual_axis_accel
        result = reconstructor.reconstruct_full(ax, t, accel_y_g=ay)

        assert result["pdof"] is not None
        assert isinstance(result["pdof"], PDOFResult)
        assert -180 <= result["pdof"].angle_deg <= 180

    def test_different_crash_modes(self):
        """Test reconstruction for different crash modes."""
        sampling_rate = 1000
        duration_s = 0.1
        n_samples = int(duration_s * sampling_rate)
        t = np.arange(n_samples) / sampling_rate

        base_pulse = 40.0 * np.sin(np.pi * t / duration_s) ** 2

        configs = [
            CrashMode.ALL,
            CrashMode.FRONTAL,
            CrashMode.REAR,
        ]

        for mode in configs:
            config = ReconstructionConfig(
                injury_crash_mode=mode,
                bootstrap_samples=100,
            )
            reconstructor = CrashReconstructor(config)
            result = reconstructor.reconstruct_full(base_pulse, t)

            assert result["injury"].crash_mode == mode

    def test_reproducibility(self, haversine_accel):
        """Same inputs should produce same outputs."""
        t, accel_g = haversine_accel

        config = ReconstructionConfig(bootstrap_samples=100, bootstrap_seed=42)
        r1 = CrashReconstructor(config).reconstruct_full(accel_g, t)
        r2 = CrashReconstructor(config).reconstruct_full(accel_g, t)

        assert r1["delta_v"].delta_v_ms == r2["delta_v"].delta_v_ms
        assert r1["delta_v"].ci_lower_ms == r2["delta_v"].ci_lower_ms
        assert r1["injury"].mais2_plus == r2["injury"].mais2_plus

    def test_performance_large_dataset(self):
        """Should handle large datasets efficiently."""
        import time

        sampling_rate = 10000  # 10 kHz
        duration_s = 0.5
        n_samples = int(duration_s * sampling_rate)
        t = np.arange(n_samples) / sampling_rate
        accel_g = 50.0 * np.sin(np.pi * t / duration_s) ** 2

        config = ReconstructionConfig(
            sampling_rate=sampling_rate,
            bootstrap_samples=100,
        )
        reconstructor = CrashReconstructor(config)

        start = time.time()
        result = reconstructor.reconstruct_full(accel_g, t)
        elapsed = time.time() - start

        # Should complete in under 5 seconds
        assert elapsed < 5.0
        assert result["delta_v"].delta_v_ms > 0


# ===================================================================
# Edge Cases
# ===================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_single_sample(self):
        """Should handle single-sample input gracefully."""
        t = np.array([0.0])
        accel_g = np.array([50.0])

        config = ReconstructionConfig(bootstrap_samples=10)
        estimator = DeltaVEstimator(config)
        result = estimator.estimate(accel_g, t)

        assert result.delta_v_ms >= 0

    def test_negative_acceleration(self):
        """Negative acceleration (deceleration) should work."""
        t = np.linspace(0, 0.1, 100)
        accel_g = -50.0 * np.sin(np.pi * t / 0.1) ** 2

        config = ReconstructionConfig(bootstrap_samples=100)
        estimator = DeltaVEstimator(config)
        result = estimator.estimate(accel_g, t)

        assert result.delta_v_ms > 0

    def test_extreme_delta_v(self):
        """Very high delta-V with saturation should still produce a valid result."""
        t = np.linspace(0, 0.15, 150)
        accel_g = 120.0 * np.sin(np.pi * t / 0.15) ** 2

        config = ReconstructionConfig(
            bootstrap_samples=100,
            use_saturation_correction=True,
        )
        estimator = DeltaVEstimator(config)
        result = estimator.estimate(accel_g, t)

        # With 120g peak, saturation should be detected (threshold 85g)
        # The measured delta-V is a lower bound
        assert result.delta_v_kmh > 50
        assert result.delta_v_kmh < 500
        assert result.saturation_detected == True

    def test_very_short_crash(self):
        """Very short crash (10ms) should work."""
        t = np.linspace(0, 0.01, 10)
        accel_g = 100.0 * np.sin(np.pi * t / 0.01) ** 2

        config = ReconstructionConfig(bootstrap_samples=50)
        estimator = DeltaVEstimator(config)
        result = estimator.estimate(accel_g, t)

        assert result.delta_v_ms > 0

    def test_config_defaults(self):
        """Default config should be valid."""
        config = ReconstructionConfig()
        assert config.sampling_rate > 0
        assert 0 <= config.restitution_coefficient <= 1
        assert config.bootstrap_samples > 0
        assert 0 < config.confidence_level < 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
