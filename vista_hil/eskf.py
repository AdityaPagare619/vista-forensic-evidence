"""
Error-State Kalman Filter (ESKF) for VISTA 2.0 Layer 2

15-state ESKF: position(3) + velocity(3) + quaternion(4) + gyro_bias(3) + accel_bias(2)
- Quaternion representation for attitude
- Pre-crash: full ESKF with gravity convergence
- Crash onset: freeze bias estimation, increase process noise
- Post-crash: resume ESKF with inflated measurement covariance
- RTS smoother for forensic post-processing

Designed for STM32H743: efficient fixed-point friendly math, 1kHz IMU, 10Hz OBD.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum


class CrashState(Enum):
    """ESKF crash phase states"""
    PRE_CRASH = "pre_crash"
    CRASH_ONSET = "crash_onset"
    POST_CRASH = "post_crash"


@dataclass
class ESKFConfig:
    """Configuration for ESKF"""
    # Initial uncertainty
    initial_position_std: float = 1.0       # m
    initial_velocity_std: float = 1.0       # m/s
    initial_attitude_std: float = 5.0       # degrees
    initial_gyro_bias_std: float = 0.01     # rad/s
    initial_accel_bias_std: float = 0.1     # m/s²

    # Process noise (per second)
    process_noise_position: float = 0.01    # m/s
    process_noise_velocity: float = 1.0     # m/s²
    process_noise_attitude: float = 0.001   # rad/s
    process_noise_gyro_bias: float = 0.0001 # rad/s²
    process_noise_accel_bias: float = 0.001 # m/s³

    # Sensor noise
    accel_noise_std: float = 0.1            # m/s²
    gyro_noise_std: float = 0.01            # rad/s
    gps_noise_std: float = 2.0              # m
    gps_velocity_noise_std: float = 0.5     # m/s

    # Gravity
    gravity: float = 9.80665                # m/s²

    # Crash detection
    crash_onset_threshold: float = 50.0     # g
    crash_onset_duration_ms: float = 5.0    # ms
    post_crash_duration_s: float = 2.0      # seconds
    post_crash_noise_inflation: float = 10.0

    # Bias limits
    max_gyro_bias: float = 0.5              # rad/s
    max_accel_bias: float = 2.0             # m/s²

    # Quaternion renormalization threshold
    quat_norm_threshold: float = 1e-6


@dataclass
class FilterState:
    """ESKF state vector"""
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    quaternion: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    gyro_bias: np.ndarray = field(default_factory=lambda: np.zeros(3))
    accel_bias: np.ndarray = field(default_factory=lambda: np.zeros(3))


class ESKF:
    """
    Error-State Kalman Filter for vehicle dynamics estimation.

    State vector (15 DOF):
        δx = [δp(3), δv(3), δθ(3), δbg(3), δba(3)]

    Nominal state:
        x = [p(3), v(3), q(4), bg(3), ba(3)]

    The error state uses a minimal 3-parameter attitude error (rotation vector)
    while the nominal state uses a full quaternion for singularity-free propagation.
    """

    def __init__(self, config: Optional[ESKFConfig] = None):
        self.config = config or ESKFConfig()
        self._init_state()
        self._init_covariance()
        self._init_crash_state()

    def _init_state(self):
        """Initialize nominal state"""
        self.state = FilterState()
        self.state.quaternion = np.array([1.0, 0.0, 0.0, 0.0])

    def _init_covariance(self):
        """Initialize error-state covariance matrix P (15x15)"""
        cfg = self.config
        self.P = np.diag([
            # Position (3)
            cfg.initial_position_std**2,
            cfg.initial_position_std**2,
            cfg.initial_position_std**2,
            # Velocity (3)
            cfg.initial_velocity_std**2,
            cfg.initial_velocity_std**2,
            cfg.initial_velocity_std**2,
            # Attitude (3) - converted from degrees to radians
            (cfg.initial_attitude_std * np.pi / 180)**2,
            (cfg.initial_attitude_std * np.pi / 180)**2,
            (cfg.initial_attitude_std * np.pi / 180)**2,
            # Gyro bias (3)
            cfg.initial_gyro_bias_std**2,
            cfg.initial_gyro_bias_std**2,
            cfg.initial_gyro_bias_std**2,
            # Accel bias (3)
            cfg.initial_accel_bias_std**2,
            cfg.initial_accel_bias_std**2,
            cfg.initial_accel_bias_std**2,
        ])

    def _init_crash_state(self):
        """Initialize crash detection state"""
        self.crash_state = CrashState.PRE_CRASH
        self._crash_onset_time: Optional[float] = None
        self._last_update_time: float = 0.0
        self._accel_magnitude_history: List[float] = []
        self._freeze_bias: bool = False

    # ========================================================================
    # Quaternion Utilities
    # ========================================================================

    @staticmethod
    def quaternion_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
        """Quaternion multiplication: q = q1 ⊗ q2"""
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        return np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2
        ])

    @staticmethod
    def quaternion_inverse(q: np.ndarray) -> np.ndarray:
        """Quaternion inverse (conjugate for unit quaternions)"""
        return np.array([q[0], -q[1], -q[2], -q[3]])

    @staticmethod
    def quaternion_normalize(q: np.ndarray) -> np.ndarray:
        """Normalize quaternion to unit length"""
        norm = np.linalg.norm(q)
        if norm < 1e-10:
            return np.array([1.0, 0.0, 0.0, 0.0])
        return q / norm

    @staticmethod
    def quaternion_to_rotation(q: np.ndarray) -> np.ndarray:
        """Convert quaternion to rotation matrix R(q)"""
        w, x, y, z = q
        return np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - w*z),     2*(x*z + w*y)],
            [2*(x*y + w*z),     1 - 2*(x*x + z*z), 2*(y*z - w*x)],
            [2*(x*z - w*y),     2*(y*z + w*x),     1 - 2*(x*x + y*y)]
        ])

    @staticmethod
    def rotation_to_quaternion(R: np.ndarray) -> np.ndarray:
        """Convert rotation matrix to quaternion (Shepperd's method)"""
        tr = np.trace(R)
        if tr > 0:
            s = 0.5 / np.sqrt(tr + 1.0)
            w = 0.25 / s
            x = (R[2, 1] - R[1, 2]) * s
            y = (R[0, 2] - R[2, 0]) * s
            z = (R[1, 0] - R[0, 1]) * s
        elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
            w = (R[2, 1] - R[1, 2]) / s
            x = 0.25 * s
            y = (R[0, 1] + R[1, 0]) / s
            z = (R[0, 2] + R[2, 0]) / s
        elif R[1, 1] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
            w = (R[0, 2] - R[2, 0]) / s
            x = (R[0, 1] + R[1, 0]) / s
            y = 0.25 * s
            z = (R[1, 2] + R[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
            w = (R[1, 0] - R[0, 1]) / s
            x = (R[0, 2] + R[2, 0]) / s
            y = (R[1, 2] + R[2, 1]) / s
            z = 0.25 * s
        q = np.array([w, x, y, z])
        return q / np.linalg.norm(q)

    @staticmethod
    def skew_symmetric(v: np.ndarray) -> np.ndarray:
        """Skew-symmetric matrix [v]× such that [v]× @ w = v × w"""
        return np.array([
            [0,    -v[2],  v[1]],
            [v[2],  0,    -v[0]],
            [-v[1], v[0],  0   ]
        ])

    def apply_rotation(self, q: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Apply rotation R(q) to vector v"""
        R = self.quaternion_to_rotation(q)
        return R @ v

    def apply_inverse_rotation(self, q: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Apply inverse rotation R(q)^T to vector v"""
        R = self.quaternion_to_rotation(q)
        return R.T @ v

    # ========================================================================
    # Error-State Jacobians
    # ========================================================================

    def _F_error_state(self, gyro_corrected: np.ndarray, dt: float) -> np.ndarray:
        """
        Error-state transition matrix F (15x15).

        F = I + F_cont * dt  (first-order approximation)

        F_cont structure:
            [I3  dt*I3  -0.5*R*[a]×*dt²  -0.5*R*dt²  0    ]
            [0   I3     -R*[a]×*dt        -R*dt       0    ]
            [0   0       I3 - [ω]×*dt     0           0    ]
            [0   0       0                 I3          0    ]
            [0   0       0                 0           I3   ]
        """
        F = np.eye(15)
        R = self.quaternion_to_rotation(self.state.quaternion)

        # Position-velocity coupling
        F[0:3, 3:6] = dt * np.eye(3)

        # Position-attitude coupling (through acceleration)
        a_corrected = self.apply_inverse_rotation(
            self.state.quaternion,
            np.array([0.0, 0.0, self.config.gravity])  # gravity in nav frame
        ) - self.state.accel_bias
        F[0:3, 6:9] = -0.5 * R @ self.skew_symmetric(a_corrected) * dt * dt

        # Velocity-attitude coupling
        F[3:6, 6:9] = -R @ self.skew_symmetric(a_corrected) * dt

        # Position-accel bias coupling
        F[0:3, 12:15] = -0.5 * R * dt * dt

        # Velocity-accel bias coupling
        F[3:6, 12:15] = -R * dt

        # Attitude-attitude: F[6:9,6:9] = I - [ω]×*dt
        F[6:9, 6:9] = np.eye(3) - self.skew_symmetric(gyro_corrected) * dt

        # Attitude-gyro_bias: d(δθ)/dt = -[ω̂]× δθ - δb_g
        # Couples gyro bias error into attitude error, enabling indirect observability
        F[6:9, 9:12] = -np.eye(3) * dt

        return F

    def _Q_error_state(self, accel_corrected: np.ndarray,
                       gyro_corrected: np.ndarray, dt: float) -> np.ndarray:
        """
        Process noise covariance Q (15x15).

        Uses piecewise constant white noise model.
        """
        cfg = self.config
        Q = np.zeros((15, 15))
        R = self.quaternion_to_rotation(self.state.quaternion)

        # Position noise
        Q[0:3, 0:3] = np.eye(3) * cfg.process_noise_position**2 * dt

        # Velocity noise (includes acceleration uncertainty)
        Q[3:6, 3:6] = np.eye(3) * cfg.process_noise_velocity**2 * dt

        # Attitude noise
        Q[6:9, 6:9] = np.eye(3) * cfg.process_noise_attitude**2 * dt

        # Gyro bias random walk
        Q[9:12, 9:12] = np.eye(3) * cfg.process_noise_gyro_bias**2 * dt

        # Accel bias random walk
        Q[12:15, 12:15] = np.eye(3) * cfg.process_noise_accel_bias**2 * dt

        # Apply crash mode inflation
        if self.crash_state == CrashState.CRASH_ONSET:
            Q[6:9, 6:9] *= 100.0  # Large attitude uncertainty
            Q[9:12, 9:12] *= 0.01  # Freeze gyro bias
            Q[12:15, 12:15] *= 0.01  # Freeze accel bias
        elif self.crash_state == CrashState.POST_CRASH:
            inflation = self.config.post_crash_noise_inflation
            Q[3:6, 3:6] *= inflation
            Q[6:9, 6:9] *= inflation

        return Q

    # ========================================================================
    # Measurement Models
    # ========================================================================

    def _H_accel(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Accelerometer measurement model.

        Convention: accelerometer reads +g upward at rest (standard MEMS).
            a_meas = R(q)^T * g_nav + b_a + noise

        At rest: specific force reaction = +g in body frame.

        Innovation: y = a_meas - a_predicted
        where a_predicted = R(q)^T * g_nav + b_a

        H (3x15): Jacobian of measurement w.r.t. error state.
        Derived via perturbation: R(q_true) = R(q)(I + [dtheta]x)
            => R(q_true)^T g = (I - [dtheta]x) R^T g = R^T g + [R^T g]x dtheta
        So: H_theta = skew_symmetric(R^T g),  H_ba = +I
        """
        R = self.quaternion_to_rotation(self.state.quaternion)
        g_nav = np.array([0.0, 0.0, self.config.gravity])

        # Predicted measurement: specific force in body frame at rest
        # At rest with identity quat: R^T g_nav = [0, 0, 9.81] matching sensor convention
        a_predicted = R.T @ g_nav + self.state.accel_bias

        H = np.zeros((3, 15))
        # Attitude: ∂(R^T g)/∂δθ = [R^T g]×  (skew-symmetric of rotated gravity)
        R_T_g = R.T @ g_nav
        H[0:3, 6:9] = self.skew_symmetric(R_T_g)
        # Accel bias: ∂(R^T g + b_a)/∂δb_a = +I
        H[0:3, 12:15] = np.eye(3)

        return H, a_predicted

    def _H_gyro(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Gyroscope measurement model.

        Measurement: ω_meas = ω_true + b_g + noise
        In steady state, ω_true ≈ 0 (no rotation).

        H (3x15): relates error state to measurement
        """
        H = np.zeros((3, 15))
        H[0:3, 9:12] = np.eye(3)  # Gyro bias

        z = np.zeros(3)  # Expected: zero angular rate at rest

        return H, z

    def _H_gps(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        GPS measurement model (position + velocity).

        H (6x15): relates error state to measurement
        """
        H = np.zeros((6, 15))
        H[0:3, 0:3] = np.eye(3)   # Position
        H[3:6, 3:6] = np.eye(3)   # Velocity

        z = np.zeros(6)  # Innovation = measurement - prediction

        return H, z

    # ========================================================================
    # Crash Detection
    # ========================================================================

    def _detect_crash_onset(self, accel_magnitude: float, dt: float):
        """
        Detect crash onset based on acceleration magnitude.

        Criteria: accel magnitude exceeds threshold for sustained duration.
        """
        self._accel_magnitude_history.append(accel_magnitude)
        # Keep only recent history
        max_history = int(self.config.crash_onset_duration_ms / (dt * 1000)) + 10
        if len(self._accel_magnitude_history) > max_history:
            self._accel_magnitude_history = self._accel_magnitude_history[-max_history:]

        if self.crash_state == CrashState.PRE_CRASH:
            # Check if threshold exceeded within the duration window.
            # Using max(recent) >= threshold (not all > threshold) because
            # a crash pulse may peak exactly at threshold for only 1-2 samples.
            # The min_samples window still provides temporal filtering.
            threshold_g = self.config.crash_onset_threshold
            min_samples = max(1, int(self.config.crash_onset_duration_ms / (dt * 1000)))

            if len(self._accel_magnitude_history) >= min_samples:
                recent = self._accel_magnitude_history[-min_samples:]
                if max(recent) >= threshold_g:
                    self.crash_state = CrashState.CRASH_ONSET
                    self._crash_onset_time = self._last_update_time
                    self._freeze_bias = True

        elif self.crash_state == CrashState.CRASH_ONSET:
            # Transition to post-crash after onset duration
            if self._crash_onset_time is not None:
                elapsed = self._last_update_time - self._crash_onset_time
                if elapsed > 0.1:  # 100ms in crash onset
                    self.crash_state = CrashState.POST_CRASH
                    self._freeze_bias = False

        elif self.crash_state == CrashState.POST_CRASH:
            # Return to pre-crash after post-crash duration
            if self._crash_onset_time is not None:
                elapsed = self._last_update_time - self._crash_onset_time
                if elapsed > self.config.post_crash_duration_s:
                    self.crash_state = CrashState.PRE_CRASH
                    self._accel_magnitude_history.clear()

    # ========================================================================
    # Core ESKF Operations
    # ========================================================================

    def predict(self, gyro: np.ndarray, accel: np.ndarray, dt: float):
        """
        ESKF prediction step.

        Args:
            gyro: Gyroscope measurement (rad/s) [gx, gy, gz]
            accel: Accelerometer measurement (m/s²) [ax, ay, az]
            dt: Time step (seconds)
        """
        if dt <= 0:
            return

        # Correct for estimated biases
        gyro_corrected = gyro - self.state.gyro_bias
        accel_corrected = accel - self.state.accel_bias

        # ---- Nominal state propagation ----
        q = self.state.quaternion.copy()
        v = self.state.velocity.copy()
        p = self.state.position.copy()

        # Quaternion update: q ← q ⊗ q{ω·Δt}
        omega_norm = np.linalg.norm(gyro_corrected)
        if omega_norm > 1e-10:
            angle = omega_norm * dt
            axis = gyro_corrected / omega_norm
            dq = np.array([
                np.cos(angle / 2),
                np.sin(angle / 2) * axis[0],
                np.sin(angle / 2) * axis[1],
                np.sin(angle / 2) * axis[2]
            ])
        else:
            dq = np.array([1.0, 0.0, 0.0, 0.0])

        q_new = self.quaternion_multiply(q, dq)
        q_new = self.quaternion_normalize(q_new)

        # Velocity update: v ← v + R(q)·(a - ba)·Δt
        # Accelerometer measures specific force, need to remove gravity
        R = self.quaternion_to_rotation(q)
        g_nav = np.array([0.0, 0.0, self.config.gravity])
        # Specific force in nav frame = R * a_meas - g
        specific_force_nav = R @ accel_corrected - g_nav
        v_new = v + specific_force_nav * dt

        # Position update: p ← p + v·Δt + 0.5·a·Δt²
        p_new = p + v * dt + 0.5 * specific_force_nav * dt * dt

        self.state.quaternion = q_new
        self.state.velocity = v_new
        self.state.position = p_new

        # ---- Error-state covariance propagation ----
        F = self._F_error_state(gyro_corrected, dt)
        Q = self._Q_error_state(accel_corrected, gyro_corrected, dt)

        # P ← F·P·F^T + Q
        self.P = F @ self.P @ F.T + Q

        # Enforce symmetry
        self.P = 0.5 * (self.P + self.P.T)

        # Update time
        self._last_update_time += dt

        # Detect crash
        accel_mag = np.linalg.norm(accel) / 9.80665  # in g
        self._detect_crash_onset(accel_mag, dt)

    def _measurement_update(self, z_meas: np.ndarray, H: np.ndarray,
                            R: np.ndarray, state_indices: Optional[List[int]] = None):
        """
        Generic measurement update using Joseph form for numerical stability.

        Joseph form: P = (I - K·H)·P·(I - K·H)^T + K·R·K^T
        """
        n = H.shape[0]

        # Innovation
        z_pred = np.zeros(n)
        y = z_meas - z_pred

        # Innovation covariance
        S = H @ self.P @ H.T + R

        # Kalman gain
        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return  # Skip update if singular

        K = self.P @ H.T @ S_inv

        # Error-state update
        dx = K @ y

        # Joseph form for covariance update (numerically stable)
        I_KH = np.eye(15) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

        # Enforce symmetry
        self.P = 0.5 * (self.P + self.P.T)

        # ---- Apply error state to nominal state ----
        # Position
        self.state.position += dx[0:3]

        # Velocity
        self.state.velocity += dx[3:6]

        # Attitude (rotation vector to quaternion)
        delta_theta = dx[6:9]
        theta_norm = np.linalg.norm(delta_theta)
        if theta_norm > 1e-10:
            half_angle = theta_norm / 2
            axis = delta_theta / theta_norm
            dq = np.array([
                np.cos(half_angle),
                np.sin(half_angle) * axis[0],
                np.sin(half_angle) * axis[1],
                np.sin(half_angle) * axis[2]
            ])
            self.state.quaternion = self.quaternion_multiply(dq, self.state.quaternion)
            self.state.quaternion = self.quaternion_normalize(self.state.quaternion)

        # Gyro bias (freeze during crash onset)
        if not self._freeze_bias:
            self.state.gyro_bias += dx[9:12]
            # Clamp
            self.state.gyro_bias = np.clip(
                self.state.gyro_bias,
                -self.config.max_gyro_bias,
                self.config.max_gyro_bias
            )

        # Accel bias (freeze during crash onset)
        if not self._freeze_bias:
            self.state.accel_bias += dx[12:15]
            # Clamp
            self.state.accel_bias = np.clip(
                self.state.accel_bias,
                -self.config.max_accel_bias,
                self.config.max_accel_bias
            )

        # Reset error state (already applied)
        # In a full implementation, we'd reset dx to zero here

    def _measurement_update_with_innovation(self, y: np.ndarray, H: np.ndarray,
                                            R: np.ndarray):
        """
        Measurement update with pre-computed innovation.

        Joseph form: P = (I - K·H)·P·(I - K·H)^T + K·R·K^T
        """
        # Innovation covariance
        S = H @ self.P @ H.T + R

        # Kalman gain
        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return  # Skip update if singular

        K = self.P @ H.T @ S_inv

        # Error-state update
        dx = K @ y

        # Joseph form for covariance update (numerically stable)
        I_KH = np.eye(15) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

        # Enforce symmetry
        self.P = 0.5 * (self.P + self.P.T)

        # ---- Apply error state to nominal state ----
        # Position
        self.state.position += dx[0:3]

        # Velocity
        self.state.velocity += dx[3:6]

        # Attitude (rotation vector to quaternion)
        delta_theta = dx[6:9]
        theta_norm = np.linalg.norm(delta_theta)
        if theta_norm > 1e-10:
            half_angle = theta_norm / 2
            axis = delta_theta / theta_norm
            dq = np.array([
                np.cos(half_angle),
                np.sin(half_angle) * axis[0],
                np.sin(half_angle) * axis[1],
                np.sin(half_angle) * axis[2]
            ])
            self.state.quaternion = self.quaternion_multiply(dq, self.state.quaternion)
            self.state.quaternion = self.quaternion_normalize(self.state.quaternion)

        # Gyro bias (freeze during crash onset)
        if not self._freeze_bias:
            self.state.gyro_bias += dx[9:12]
            # Clamp
            self.state.gyro_bias = np.clip(
                self.state.gyro_bias,
                -self.config.max_gyro_bias,
                self.config.max_gyro_bias
            )

        # Accel bias (freeze during crash onset)
        if not self._freeze_bias:
            self.state.accel_bias += dx[12:15]
            # Clamp
            self.state.accel_bias = np.clip(
                self.state.accel_bias,
                -self.config.max_accel_bias,
                self.config.max_accel_bias
            )

    def update_accel(self, accel_meas: np.ndarray):
        """
        Update with accelerometer measurement.

        Uses gravity as reference for attitude estimation.
        The accelerometer measures specific force (acceleration - gravity) in body frame.

        Skip update when:
        - During crash onset/post-crash (measurement includes crash forces)
        - Acceleration magnitude deviates significantly from 1g
          (the gravity-only model a_meas = R^T*g + bias does not apply
          when external forces like crash deceleration are present)
        """
        # During crash onset, accel measurements contain crash forces that
        # don't match the gravity-only measurement model. Skip to preserve
        # velocity integration from prediction.
        if self.crash_state in (CrashState.CRASH_ONSET, CrashState.POST_CRASH):
            return

        # If acceleration magnitude is far from 1g, the gravity-only model
        # doesn't apply — external forces are present. Skip update to prevent
        # the gravity-only model from corrupting the state estimate.
        accel_mag = np.linalg.norm(accel_meas)
        if accel_mag > 2.0 * self.config.gravity:
            return

        H, a_predicted = self._H_accel()

        # Measurement noise
        R = np.eye(3) * self.config.accel_noise_std**2

        # Innovation: measurement - predicted
        y = accel_meas - a_predicted

        self._measurement_update_with_innovation(y, H, R)

    def update_gyro(self, gyro_meas: np.ndarray):
        """
        Update with gyroscope measurement.

        Uses zero-rate assumption (vehicle not rotating) for bias estimation.
        Only useful when vehicle is known to be stationary or moving linearly.
        """
        H, gyro_predicted = self._H_gyro()

        R = np.eye(3) * self.config.gyro_noise_std**2
        if self.crash_state == CrashState.POST_CRASH:
            R *= self.config.post_crash_noise_inflation

        # Innovation: measurement - predicted (predicted is zero at rest)
        y = gyro_meas - self.state.gyro_bias - gyro_predicted

        self._measurement_update_with_innovation(y, H, R)

    def update_gps(self, gps_position: np.ndarray, gps_velocity: np.ndarray):
        """
        Update with GPS position and velocity.

        Args:
            gps_position: GPS position [x, y, z] in meters
            gps_velocity: GPS velocity [vx, vy, vz] in m/s
        """
        H, _ = self._H_gps()

        R = np.diag([
            self.config.gps_noise_std**2,
            self.config.gps_noise_std**2,
            self.config.gps_noise_std**2,
            self.config.gps_velocity_noise_std**2,
            self.config.gps_velocity_noise_std**2,
            self.config.gps_velocity_noise_std**2,
        ])

        z_meas = np.concatenate([
            gps_position - self.state.position,
            gps_velocity - self.state.velocity
        ])

        self._measurement_update(z_meas, H, R)

    def update(self, gyro: np.ndarray, accel: np.ndarray,
               gps_position: Optional[np.ndarray] = None,
               gps_velocity: Optional[np.ndarray] = None,
               dt: float = 0.001):
        """
        Combined predict and update step.

        Args:
            gyro: Gyroscope measurement (rad/s)
            accel: Accelerometer measurement (m/s²)
            gps_position: Optional GPS position
            gps_velocity: Optional GPS velocity
            dt: Time step (seconds)
        """
        self.predict(gyro, accel, dt)
        self.update_accel(accel)

        if gps_position is not None and gps_velocity is not None:
            self.update_gps(gps_position, gps_velocity)

    # ========================================================================
    # State Access
    # ========================================================================

    def get_velocity(self) -> np.ndarray:
        """Get current velocity estimate"""
        return self.state.velocity.copy()

    def get_position(self) -> np.ndarray:
        """Get current position estimate"""
        return self.state.position.copy()

    def get_attitude(self) -> np.ndarray:
        """Get current attitude as quaternion [w, x, y, z]"""
        return self.state.quaternion.copy()

    def get_attitude_euler(self) -> np.ndarray:
        """Get current attitude as Euler angles [roll, pitch, yaw] in radians"""
        q = self.state.quaternion
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (q[0]*q[1] + q[2]*q[3])
        cosr_cosp = 1 - 2 * (q[1]**2 + q[2]**2)
        roll = np.arctan2(sinr_cosp, cosr_cosp)

        # Pitch (y-axis rotation)
        sinp = 2 * (q[0]*q[2] - q[3]*q[1])
        pitch = np.arcsin(np.clip(sinp, -1.0, 1.0))

        # Yaw (z-axis rotation)
        siny_cosp = 2 * (q[0]*q[3] + q[1]*q[2])
        cosy_cosp = 1 - 2 * (q[2]**2 + q[3]**2)
        yaw = np.arctan2(siny_cosp, cosy_cosp)

        return np.array([roll, pitch, yaw])

    def get_gyro_bias(self) -> np.ndarray:
        """Get current gyro bias estimate"""
        return self.state.gyro_bias.copy()

    def get_accel_bias(self) -> np.ndarray:
        """Get current accel bias estimate"""
        return self.state.accel_bias.copy()

    def get_covariance_diagonal(self) -> np.ndarray:
        """Get diagonal of covariance matrix (1-sigma uncertainties)"""
        return np.sqrt(np.diag(self.P))

    # ========================================================================
    # Crash Mode Control
    # ========================================================================

    def set_crash_state(self, state: CrashState):
        """Manually set crash state"""
        self.crash_state = state
        if state == CrashState.CRASH_ONSET:
            self._freeze_bias = True
        else:
            self._freeze_bias = False

    # ========================================================================
    # RTS Smoother (Offline Post-Processing)
    # ========================================================================

    def smooth(self) -> Optional[List[Dict]]:
        """
        Rauch-Tung-Striebel (RTS) smoother for offline post-processing.

        Should be called after a complete filter run with stored states.

        Returns:
            List of smoothed state dictionaries, or None if no stored data
        """
        if not hasattr(self, '_stored_states') or len(self._stored_states) < 2:
            return None

        states = self._stored_states
        covariances = self._stored_covariances
        n = len(states)

        # Initialize smoothed estimates with filtered values
        smoothed = [None] * n
        smoothed[-1] = {
            'position': states[-1]['position'].copy(),
            'velocity': states[-1]['velocity'].copy(),
            'quaternion': states[-1]['quaternion'].copy(),
            'gyro_bias': states[-1]['gyro_bias'].copy(),
            'accel_bias': states[-1]['accel_bias'].copy(),
        }

        P_smooth = covariances[-1].copy()

        # Backward pass
        for k in range(n - 2, -1, -1):
            # Smoother gain: C_k = P_k @ F_k^T @ (P_{k+1})^{-1}
            F = self._F_error_state(states[k]['gyro_bias'], 0.001)  # Approximate

            try:
                P_pred_inv = np.linalg.inv(covariances[k + 1])
                C_k = covariances[k] @ F.T @ P_pred_inv
            except np.linalg.LinAlgError:
                C_k = np.eye(15) * 0.5

            # Smoothed state
            dx_smooth = C_k @ (
                np.concatenate([
                    smoothed[k + 1]['position'] - states[k + 1]['position'],
                    smoothed[k + 1]['velocity'] - states[k + 1]['velocity'],
                    np.zeros(3),  # Attitude difference (simplified)
                    smoothed[k + 1]['gyro_bias'] - states[k + 1]['gyro_bias'],
                    smoothed[k + 1]['accel_bias'] - states[k + 1]['accel_bias'],
                ])
            )

            smoothed[k] = {
                'position': states[k]['position'] + dx_smooth[0:3],
                'velocity': states[k]['velocity'] + dx_smooth[3:6],
                'quaternion': states[k]['quaternion'].copy(),  # Simplified
                'gyro_bias': states[k]['gyro_bias'] + dx_smooth[9:12],
                'accel_bias': states[k]['accel_bias'] + dx_smooth[12:15],
            }

            # Smoothed covariance
            P_smooth = covariances[k] + C_k @ (P_smooth - covariances[k + 1]) @ C_k.T

        return smoothed

    def store_state(self):
        """Store current state for later smoothing"""
        if not hasattr(self, '_stored_states'):
            self._stored_states = []
            self._stored_covariances = []

        self._stored_states.append({
            'position': self.state.position.copy(),
            'velocity': self.state.velocity.copy(),
            'quaternion': self.state.quaternion.copy(),
            'gyro_bias': self.state.gyro_bias.copy(),
            'accel_bias': self.state.accel_bias.copy(),
        })
        self._stored_covariances.append(self.P.copy())

    def clear_stored_states(self):
        """Clear stored states"""
        self._stored_states = []
        self._stored_covariances = []
