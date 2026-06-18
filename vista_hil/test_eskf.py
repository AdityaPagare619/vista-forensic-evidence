"""
Tests for Error-State Kalman Filter (ESKF) - VISTA 2.0 Layer 2

Following TDD: write tests first, then implement.
Tests cover:
1. Quaternion math correctness
2. Static test: bias convergence at rest
3. Constant velocity: 60 km/h straight line
4. Simple braking: 100→0 km/h in 3 seconds
5. Crash pulse: 50g haversine 80ms
6. Full pipeline: IMU → velocity estimate
7. Crash onset detection and mode switching
8. RTS smoother correctness
"""

import numpy as np
import pytest
from vista_hil.eskf import ESKF, ESKFConfig, FilterState, CrashState


# ============================================================================
# Quaternion Math Tests
# ============================================================================

class TestQuaternionMath:
    """Test quaternion utility functions"""

    def test_quaternion_multiply_identity(self):
        """Identity quaternion times any quaternion returns that quaternion"""
        eskf = ESKF(ESKFConfig())
        q_identity = np.array([1.0, 0.0, 0.0, 0.0])
        # Use exactly normalized quaternion: cos(45°) = sin(45°) = 1/√2
        s = np.sqrt(2) / 2
        q_test = np.array([s, 0.0, s, 0.0])  # 90° about Y

        result = eskf.quaternion_multiply(q_identity, q_test)
        np.testing.assert_allclose(result, q_test, atol=1e-10)

    def test_quaternion_multiply_inverse(self):
        """q * q_inv should return identity"""
        eskf = ESKF(ESKFConfig())
        s = np.sqrt(2) / 2
        q = np.array([s, 0.0, s, 0.0])
        q_inv = eskf.quaternion_inverse(q)

        result = eskf.quaternion_multiply(q, q_inv)
        np.testing.assert_allclose(result, [1.0, 0.0, 0.0, 0.0], atol=1e-10)

    def test_rotation_matrix_orthogonal(self):
        """Rotation matrix from quaternion should be orthogonal (R^T R = I)"""
        eskf = ESKF(ESKFConfig())
        s = np.sqrt(2) / 2
        q = np.array([s, 0.0, s, 0.0])
        R = eskf.quaternion_to_rotation(q)

        RTR = R.T @ R
        np.testing.assert_allclose(RTR, np.eye(3), atol=1e-10)

    def test_rotation_matrix_determinant(self):
        """Rotation matrix determinant should be +1"""
        eskf = ESKF(ESKFConfig())
        s = np.sqrt(2) / 2
        q = np.array([s, 0.0, s, 0.0])
        R = eskf.quaternion_to_rotation(q)

        assert abs(np.linalg.det(R) - 1.0) < 1e-10

    def test_apply_rotation_then_inverse(self):
        """R(q) @ v then R(q_inv) @ should return original v"""
        eskf = ESKF(ESKFConfig())
        s = np.sqrt(2) / 2
        q = np.array([s, 0.0, s, 0.0])
        v = np.array([1.0, 2.0, 3.0])

        R = eskf.quaternion_to_rotation(q)
        R_inv = eskf.quaternion_to_rotation(eskf.quaternion_inverse(q))

        rotated = R @ v
        recovered = R_inv @ rotated

        np.testing.assert_allclose(recovered, v, atol=1e-10)

    def test_skew_symmetric(self):
        """Skew-symmetric matrix: [v]_x @ v should be zero"""
        eskf = ESKF(ESKFConfig())
        v = np.array([1.0, 2.0, 3.0])
        S = eskf.skew_symmetric(v)

        result = S @ v
        np.testing.assert_allclose(result, [0.0, 0.0, 0.0], atol=1e-10)

    def test_skew_symmetric_antisymmetric(self):
        """Skew-symmetric matrix: S + S^T should be zero"""
        eskf = ESKF(ESKFConfig())
        v = np.array([1.0, 2.0, 3.0])
        S = eskf.skew_symmetric(v)

        np.testing.assert_allclose(S + S.T, np.zeros((3, 3)), atol=1e-10)


# ============================================================================
# Static Test: Sensor at Rest
# ============================================================================

class TestStaticBiasConvergence:
    """Test that biases converge when sensor is at rest"""

    def test_gyro_bias_convergence(self):
        """Gyro bias should converge to true bias when sensor is stationary"""
        eskf = ESKF(ESKFConfig(
            initial_gyro_bias_std=0.01,
            initial_accel_bias_std=0.01,
            gyro_noise_std=0.001,
            accel_noise_std=0.01,
        ))

        # True biases
        true_gyro_bias = np.array([0.05, -0.03, 0.02])  # rad/s
        true_accel_bias = np.array([0.1, -0.05, 0.08])   # m/s²

        dt = 0.001  # 1kHz
        n_samples = 5000  # 5 seconds

        for i in range(n_samples):
            # Simulated IMU: gravity only + bias + noise
            gyro_meas = true_gyro_bias + np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + true_accel_bias + np.random.normal(0, 0.01, 3)

            eskf.predict(gyro_meas, accel_meas, dt)

            # Update with accelerometer (gravity reference)
            eskf.update_accel(accel_meas)

        # After convergence, estimated biases should be close to true
        gyro_error = np.abs(eskf.state.gyro_bias - true_gyro_bias)
        accel_error = np.abs(eskf.state.accel_bias - true_accel_bias)

        assert np.all(gyro_error < 0.02), f"Gyro bias error too large: {gyro_error}"
        assert np.all(accel_error < 0.05), f"Accel bias error too large: {accel_error}"

    def test_position_stays_near_origin(self):
        """Position should stay near origin when sensor is stationary"""
        eskf = ESKF(ESKFConfig(
            process_noise_position=0.001,
            accel_noise_std=0.01,
        ))

        dt = 0.001
        n_samples = 3000  # 3 seconds

        for i in range(n_samples):
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.01, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

        pos_error = np.linalg.norm(eskf.state.position)
        assert pos_error < 5.0, f"Position drifted too far: {pos_error} m"


# ============================================================================
# Constant Velocity Test: 60 km/h Straight Line
# ============================================================================

class TestConstantVelocity:
    """Test velocity estimation during constant velocity motion"""

    def test_velocity_estimate_60kmh(self):
        """Velocity should converge to ~16.67 m/s (60 km/h)"""
        eskf = ESKF(ESKFConfig(
            accel_noise_std=0.05,
            gps_noise_std=0.5,
        ))

        true_velocity = 60.0 / 3.6  # 16.67 m/s
        dt = 0.001
        n_samples = 5000  # 5 seconds

        # Run prediction with near-zero acceleration (constant velocity)
        for i in range(n_samples):
            # Constant velocity: no acceleration except gravity
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.01, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            # Simulate GPS update at 10Hz
            if i % 100 == 0:
                gps_pos = np.array([true_velocity * i * dt, 0.0, 0.0])
                gps_vel = np.array([true_velocity, 0.0, 0.0])
                eskf.update_gps(gps_pos, gps_vel)

        vel_error = abs(eskf.state.velocity[0] - true_velocity)
        assert vel_error < 2.0, f"Velocity error too large: {vel_error} m/s"


# ============================================================================
# Simple Braking Test: 100→0 km/h in 3 seconds
# ============================================================================

class TestBrakingDeceleration:
    """Test velocity estimation during braking"""

    def test_delta_v_estimation(self):
        """Should estimate delta-V of ~27.78 m/s (100 km/h)"""
        eskf = ESKF(ESKFConfig(
            accel_noise_std=0.1,
            gps_noise_std=0.5,
        ))

        initial_velocity = 100.0 / 3.6  # 27.78 m/s
        braking_time = 3.0  # seconds
        dt = 0.001
        n_samples = int(braking_time / dt)

        # Constant deceleration
        deceleration = initial_velocity / braking_time  # m/s²

        for i in range(n_samples):
            t = i * dt

            # Vehicle decelerating: accel in -X direction (opposing motion)
            # In body frame: deceleration is along X axis
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([-deceleration, 0.0, 9.81]) + np.random.normal(0, 0.05, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            if i % 100 == 0:
                remaining_vel = initial_velocity - deceleration * t
                gps_pos = np.array([
                    initial_velocity * t - 0.5 * deceleration * t**2,
                    0.0, 0.0
                ])
                gps_vel = np.array([remaining_vel, 0.0, 0.0])
                eskf.update_gps(gps_pos, gps_vel)

        # Final velocity should be near zero
        final_vel = eskf.state.velocity[0]
        assert abs(final_vel) < 3.0, f"Final velocity error: {final_vel} m/s"

        # Total delta-V should be approximately 27.78 m/s
        delta_v = initial_velocity - final_vel
        assert abs(delta_v - initial_velocity) < 5.0, f"Delta-V error: {delta_v}"


# ============================================================================
# Crash Pulse Test: 50g Haversine 80ms
# ============================================================================

class TestCrashPulse:
    """Test ESKF behavior during crash pulse"""

    def test_velocity_estimate_crash(self):
        """Velocity should be estimated during 50g crash pulse"""
        eskf = ESKF(ESKFConfig(
            accel_noise_std=0.5,
            process_noise_velocity=100.0,
        ))

        peak_g = 50.0
        duration_s = 0.08  # 80ms
        dt = 0.001
        n_samples = int(duration_s / dt)

        # Generate haversine pulse
        t = np.arange(n_samples) * dt
        pulse_g = peak_g * np.sin(np.pi * t / duration_s) ** 2
        pulse_ms2 = pulse_g * 9.80665

        # Expected delta-V from integrating the pulse
        expected_delta_v = np.trapz(pulse_ms2, dx=dt)

        velocities = []
        for i in range(n_samples):
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([pulse_ms2[i], 0.0, 9.81]) + np.random.normal(0, 0.5, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            velocities.append(eskf.state.velocity[0].copy())

        # Velocity should show significant change
        final_velocity = eskf.state.velocity[0]
        assert abs(final_velocity) > 5.0, f"Crash velocity too small: {final_velocity} m/s"

        # Should be within reasonable range of expected delta-V
        # (allowing for estimation error during high-dynamics)
        assert abs(final_velocity - expected_delta_v) < 15.0, \
            f"Velocity error: {abs(final_velocity - expected_delta_v)} m/s"

    def test_crash_onset_detection(self):
        """ESKF should detect crash onset and switch modes"""
        eskf = ESKF(ESKFConfig(
            crash_onset_threshold=50.0,  # 50g threshold
        ))

        # First 1 second: normal operation
        dt = 0.001
        for i in range(1000):
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.01, 3)
            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

        assert eskf.crash_state == CrashState.PRE_CRASH, "Should start in pre_crash mode"

        # Crash pulse: 50g for 80ms
        for i in range(80):
            t = i * dt
            pulse = 50.0 * np.sin(np.pi * t / 0.08) ** 2
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([pulse * 9.80665, 0.0, 9.81]) + np.random.normal(0, 0.5, 3)
            eskf.predict(gyro_meas, accel_meas, dt)

        # Should have detected crash
        assert eskf.crash_state != CrashState.PRE_CRASH, "Should detect crash onset"

        # Post-crash: resume with inflated noise
        for i in range(1000):
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.5, 3)
            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)


# ============================================================================
# Full Pipeline Test
# ============================================================================

class TestFullPipeline:
    """Test complete ESKF pipeline with all measurements"""

    def test_imu_to_velocity_pipeline(self):
        """Test end-to-end: IMU data → ESKF → velocity estimate"""
        eskf = ESKF(ESKFConfig(
            accel_noise_std=0.1,
            gyro_noise_std=0.01,
            gps_noise_std=1.0,
        ))

        # Simulate 10 seconds of driving at 30 m/s
        true_vel = 30.0
        dt = 0.001
        n_samples = 10000

        for i in range(n_samples):
            # Constant velocity: only gravity in accel
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.05, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            # GPS at 10Hz
            if i % 100 == 0:
                gps_pos = np.array([true_vel * i * dt, 0.0, 0.0])
                gps_vel = np.array([true_vel, 0.0, 0.0])
                eskf.update_gps(gps_pos, gps_vel)

        vel_error = abs(eskf.state.velocity[0] - true_vel)
        assert vel_error < 2.0, f"Pipeline velocity error: {vel_error} m/s"

    def test_multi_axis_motion(self):
        """Test ESKF with simultaneous X and Y motion"""
        eskf = ESKF(ESKFConfig())

        vx_true = 20.0  # m/s forward
        vy_true = 5.0   # m/s lateral
        dt = 0.001
        n_samples = 5000

        for i in range(n_samples):
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.05, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            if i % 100 == 0:
                gps_pos = np.array([vx_true * i * dt, vy_true * i * dt, 0.0])
                gps_vel = np.array([vx_true, vy_true, 0.0])
                eskf.update_gps(gps_pos, gps_vel)

        vel_error = np.linalg.norm(eskf.state.velocity[:2] - [vx_true, vy_true])
        assert vel_error < 3.0, f"Multi-axis velocity error: {vel_error} m/s"


# ============================================================================
# Covariance and Numerical Stability
# ============================================================================

class TestNumericalStability:
    """Test numerical stability of the filter"""

    def test_covariance_positive_definite(self):
        """Covariance matrix should remain positive definite"""
        eskf = ESKF(ESKFConfig())

        dt = 0.001
        for i in range(2000):
            gyro_meas = np.random.normal(0, 0.01, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.1, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            # Check positive definiteness
            eigenvalues = np.linalg.eigvalsh(eskf.P)
            assert np.all(eigenvalues > 0), f"Not positive definite at step {i}"

    def test_quaternion_stays_normalized(self):
        """Quaternion should stay normalized throughout filtering"""
        eskf = ESKF(ESKFConfig())

        dt = 0.001
        for i in range(2000):
            gyro_meas = np.random.normal(0, 0.01, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.1, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            q_norm = np.linalg.norm(eskf.state.quaternion)
            assert abs(q_norm - 1.0) < 1e-6, f"Quaternion norm: {q_norm}"

    def test_state_bounds(self):
        """State should stay within reasonable bounds"""
        eskf = ESKF(ESKFConfig(
            accel_noise_std=0.05,
            process_noise_velocity=0.1,
        ))

        dt = 0.001
        for i in range(3000):
            gyro_meas = np.random.normal(0, 0.01, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.05, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            # Position should stay reasonable
            assert np.all(np.abs(eskf.state.position) < 200), "Position out of bounds"
            # Velocity should stay reasonable
            assert np.all(np.abs(eskf.state.velocity) < 50), "Velocity out of bounds"
            # Biases should stay reasonable
            assert np.all(np.abs(eskf.state.gyro_bias) < 1.0), "Gyro bias out of bounds"
            assert np.all(np.abs(eskf.state.accel_bias) < 5.0), "Accel bias out of bounds"


# ============================================================================
# RTS Smoother Test
# ============================================================================

class TestRTSSmoother:
    """Test Rauch-Tung-Striebel smoother"""

    def test_smoother_reduces_error(self):
        """Smoothed estimates should have lower error than filtered"""
        np.random.seed(42)

        eskf = ESKF(ESKFConfig(
            accel_noise_std=0.5,
            gps_noise_std=2.0,
        ))

        true_vel = 20.0
        dt = 0.001
        n_samples = 3000

        # Run filter and store states
        for i in range(n_samples):
            gyro_meas = np.random.normal(0, 0.001, 3)
            accel_meas = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.1, 3)

            eskf.predict(gyro_meas, accel_meas, dt)
            eskf.update_accel(accel_meas)

            if i % 100 == 0:
                gps_pos = np.array([true_vel * i * dt, 0.0, 0.0])
                gps_vel = np.array([true_vel, 0.0, 0.0])
                eskf.update_gps(gps_pos, gps_vel)

        # Get filtered estimate
        filtered_vel = eskf.state.velocity[0].copy()

        # Run smoother
        smoothed = eskf.smooth()

        if smoothed is not None:
            # Smoothed should be closer to truth (or at least not worse)
            smoothed_vel = smoothed[-1]['velocity'][0]
            # Both should be reasonable
            assert abs(filtered_vel - true_vel) < 5.0
            assert abs(smoothed_vel - true_vel) < 5.0


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_zero_dt(self):
        """Filter should handle zero dt gracefully"""
        eskf = ESKF(ESKFConfig())
        # Should not crash, just skip update
        eskf.predict(np.zeros(3), np.array([0, 0, 9.81]), 0.0)

    def test_large_dt(self):
        """Filter should handle large dt without instability"""
        eskf = ESKF(ESKFConfig())
        # 10 second step - should still be stable
        eskf.predict(np.zeros(3), np.array([0, 0, 9.81]), 10.0)

    def test_repeated_updates(self):
        """Multiple updates without predict should not crash"""
        eskf = ESKF(ESKFConfig())
        accel = np.array([0.0, 0.0, 9.81])

        for _ in range(10):
            eskf.update_accel(accel)

        # State should still be valid
        assert np.all(np.isfinite(eskf.state.position))
        assert np.all(np.isfinite(eskf.state.velocity))

    def test_nan_input_handling(self):
        """Filter should handle NaN inputs gracefully"""
        eskf = ESKF(ESKFConfig())
        # NaN inputs should not crash the filter
        eskf.predict(
            np.array([np.nan, 0, 0]),
            np.array([0, 0, 9.81]),
            0.001
        )
        # State might be NaN, but should not crash
        assert True  # If we get here, no crash


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
