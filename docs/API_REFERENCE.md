# VISTA 2.0 API Reference

**Version:** 2.0.0  
**Date:** 2026-06-14  
**Status:** Production Reference  

---

## Table of Contents

1. [vista_hil.mems_simulator](#1-mems_simulatorpy)
2. [vista_hil.crash_pulse](#2-crash_pulsepy)
3. [vista_hil.realistic_simulation](#3-realistic_simulationpy)
4. [vista_hil.eskf](#4-eskfpy)
5. [vista_hil.detection_cascade](#5-detection_cascadepy)
6. [vista_hil.reconstruction](#6-reconstructionpy)
7. [vista_hil.audio_pipeline](#7-audio_pipelinepy)
8. [vista_hil.visual_pipeline](#8-visual_pipelinepy)
9. [vista_hil.evidence_chain](#9-evidence_chainpy)
10. [vista_hil.deployment](#10-deploymentpy)

---

## 1. mems_simulator.py

**Module Purpose:** Simulates realistic MEMS IMU behavior during crash events including saturation, noise, bandwidth limiting, temperature drift, and cross-axis sensitivity.

### SensorConfig

```python
@dataclass
class SensorConfig:
    """Configuration for a specific MEMS sensor."""
    name: str
    accel_range_g: float              # Dynamic range in ±g
    gyro_range_dps: float             # Gyro range in ±°/s (0 if no gyro)
    accel_noise_density: float        # Accelerometer noise density (g/√Hz)
    gyro_noise_density: float         # Gyroscope noise density (°/s/√Hz)
    accel_bias_instability: float     # Accelerometer bias instability (g)
    gyro_bias_instability: float      # Gyroscope bias instability (°/s)
    bias_drift_rate: float            # Bias random walk rate (g/s)
    accel_bandwidth_hz: float         # Accelerometer LP filter cutoff (Hz)
    gyro_bandwidth_hz: float          # Gyroscope LP filter cutoff (Hz)
    temp_sensitivity_coeff: float     # Temperature sensitivity (/°C)
    temp_offset_coeff: float          # Temperature offset coefficient (g/°C)
    reference_temp: float             # Reference temperature (°C)
    cross_axis_matrix: np.ndarray     # 3×3 cross-axis sensitivity matrix
    max_odr: int                      # Maximum output data rate (Hz)
    jitter_pct: float                 # Sampling jitter as ±fraction
    clock_drift_ppm: float            # Clock drift in parts per million
    factory_offset_accel: np.ndarray  # 3-element factory accel offset (g)
    factory_offset_gyro: np.ndarray   # 3-element factory gyro offset (°/s)
```

#### `SensorConfig.from_yaml(path: str) -> SensorConfig`

Load sensor configuration from a YAML file.

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Path to YAML sensor config file (e.g., `sensors/mpu6050.yaml`) |
| **Returns** | `SensorConfig` | Populated configuration dataclass |

**Example:**
```python
config = SensorConfig.from_yaml("sensors/mpu6050.yaml")
print(config.name)  # "MPU6050"
print(config.accel_range_g)  # ±16
```

---

### MEMSSensorSimulator

```python
class MEMSSensorSimulator:
    def __init__(self, config: SensorConfig, sampling_rate: int = 1000)
```

Simulates realistic MEMS sensor behavior during crash events.

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `SensorConfig` | (required) | Sensor configuration |
| `sampling_rate` | `int` | `1000` | Sampling rate in Hz |

#### `MEMSSensorSimulator.simulate(...)`

```python
def simulate(self,
             crash_pulse: np.ndarray,
             crash_gyro: Optional[np.ndarray] = None,
             temperature: float = 25.0,
             start_time: float = 0.0) -> dict
```

Run the full 6-stage MEMS simulation pipeline.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `crash_pulse` | `np.ndarray` | (required) | Nx3 acceleration in m/s² |
| `crash_gyro` | `Optional[np.ndarray]` | `None` | Nx3 angular rates in rad/s |
| `temperature` | `float` | `25.0` | Sensor temperature (°C) |
| `start_time` | `float` | `0.0` | Start time offset (seconds) |

**Returns:** `dict` with keys:

| Key | Type | Description |
|-----|------|-------------|
| `timestamp` | `np.ndarray` | (N,) actual sample timestamps (s) |
| `accel` | `np.ndarray` | (N,3) simulated acceleration (m/s²) |
| `gyro` | `np.ndarray` | (N,3) simulated angular rate (rad/s) |
| `saturation` | `np.ndarray` | (N,3) boolean saturation flags |
| `gyro_saturation` | `np.ndarray` | (N,3) boolean gyro saturation flags |
| `temperature` | `float` | Temperature used |
| `sampling_rate` | `int` | Sampling rate used |
| `sensor_name` | `str` | Sensor name from config |

**Simulation Stages:**
1. Bandwidth limiting (2nd-order Butterworth LP)
2. White noise injection (Allan variance model)
3. Temperature drift (sensitivity + offset)
4. Cross-axis sensitivity (3×3 matrix multiply)
5. Range clipping (saturation detection)
6. Time synchronization (jitter + clock drift)

**Example:**
```python
from vista_hil import load_sensor
import numpy as np

sensor = load_sensor("mpu6050", sampling_rate=1000)

# Generate 50g crash pulse
n = 100
t = np.arange(n) / 1000.0
pulse = np.zeros((n, 3))
pulse[:, 0] = 50 * 9.80665 * np.sin(np.pi * t / 0.1) ** 2

result = sensor.simulate(pulse, temperature=30.0)
print(f"Peak accel: {np.max(np.abs(result['accel']))/9.80665:.1f}g")
print(f"Saturated: {np.any(result['saturation'])}")
```

---

### load_sensor

```python
def load_sensor(sensor_name: str, sampling_rate: int = 1000) -> MEMSSensorSimulator
```

Convenience function to load a sensor by name from YAML files.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sensor_name` | `str` | (required) | Sensor name (e.g., `"mpu6050"`, `"h3lis331dl"`, `"iam20680hp"`) |
| `sampling_rate` | `int` | `1000` | Sampling rate in Hz |
| **Returns** | `MEMSSensorSimulator` | | Configured simulator instance |

**Raises:** `FileNotFoundError` if sensor config YAML not found.

**Example:**
```python
sensor = load_sensor("h3lis331dl", sampling_rate=1000)
result = sensor.simulate(crash_pulse)
```

---

## 2. crash_pulse.py

**Module Purpose:** Generates parametric crash pulse waveforms based on NHTSA research for MEMS sensor simulation and VISTA algorithm testing.

### CrashType

```python
class CrashType(Enum):
    HAVERSINE = "haversine"    # sin² pulse — most realistic for frontal crashes
    HALF_SINE = "half_sine"    # sin pulse — good general approximation
    SQUARE = "square"          # Square wave — worst-case for algorithms
    TRIANGULAR = "triangular"  # Triangle — simple baseline
    CUSTOM = "custom"          # User-defined pulse shape
```

### CrashDirection

```python
class CrashDirection(Enum):
    FRONTAL = "frontal"      # Frontal barrier impact
    REAR = "rear"            # Rear-end collision
    LEFT_SIDE = "left_side"  # Left side impact
    RIGHT_SIDE = "right_side" # Right side impact
    OFFSET = "offset"        # Offset frontal crash
    OBLIQUE = "oblique"      # Angled crash
```

### CrashPulseConfig

```python
@dataclass
class CrashPulseConfig:
    crash_type: CrashType
    peak_g: float                 # Peak acceleration in g
    duration_ms: float            # Crash duration in milliseconds
    delta_v_kmh: float           # Delta-V in km/h
    direction: CrashDirection
    sampling_rate: int = 1000     # Hz
    vehicle_mass_kg: float = 1500 # Typical passenger vehicle mass
    crush_distance_m: float = 0.5 # Vehicle crush distance
```

**Validation:** Raises `ValueError` if `peak_g`, `duration_ms`, or `delta_v_kmh` are non-positive.

---

### CrashPulseGenerator

```python
class CrashPulseGenerator:
    def __init__(self, seed: Optional[int] = None)
```

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `seed` | `Optional[int]` | `None` | Random seed for reproducibility |

#### `CrashPulseGenerator.generate(...)`

```python
def generate(self,
             crash_type: str = "haversine",
             peak_g: float = 50.0,
             duration_ms: float = 100.0,
             delta_v_kmh: float = 40.0,
             direction: str = "frontal",
             sampling_rate: int = 1000,
             add_realistic_features: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray]
```

Generate a complete crash pulse with realistic features.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `crash_type` | `str` | `"haversine"` | Pulse shape type |
| `peak_g` | `float` | `50.0` | Peak acceleration (g) |
| `duration_ms` | `float` | `100.0` | Crash duration (ms) |
| `delta_v_kmh` | `float` | `40.0` | Delta-V (km/h) |
| `direction` | `str` | `"frontal"` | Impact direction |
| `sampling_rate` | `int` | `1000` | Sampling rate (Hz) |
| `add_realistic_features` | `bool` | `True` | Add vibration/ringing |

**Returns:** `Tuple[np.ndarray, np.ndarray, np.ndarray]`
- `time_array`: Time in seconds (N,)
- `accel_xyz`: Acceleration in m/s² (N×3)
- `gyro_xyz`: Angular rate in rad/s (N×3)

**Realistic Features Added:**
- Pre-impact vibration (10–50 Hz, 0.1–0.5g)
- Impact onset ringing (100–500 Hz, exponential decay)
- Random noise (0.1–0.3g RMS)

#### `CrashPulseGenerator.generate_random_crash(seed: Optional[int] = None) -> dict`

Generate a random crash scenario with realistic parameters based on NHTSA statistics.

**Returns:** `dict` with keys: `type`, `peak_g`, `duration_ms`, `delta_v_kmh`, `direction`, `severity`.

#### `CrashPulseGenerator.generate_batch(n_scenarios: int = 1000, seed: int = 42) -> list`

Generate a batch of diverse crash scenarios.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_scenarios` | `int` | `1000` | Number of scenarios |
| `seed` | `int` | `42` | Random seed |
| **Returns** | `list` | | List of crash config dictionaries |

**Example:**
```python
gen = CrashPulseGenerator(seed=42)
t, accel, gyro = gen.generate(
    crash_type="haversine", peak_g=50, duration_ms=100,
    delta_v_kmh=40, direction="frontal"
)
# accel is in m/s², convert to g:
accel_g = accel / 9.80665
```

---

## 3. realistic_simulation.py

**Module Purpose:** Complete physical chain simulation from barrier impact to sensor output — the Virtual Crash Test Lab.

### VehicleTransferConfig

```python
@dataclass
class VehicleTransferConfig:
    natural_freq_hz: float = 30.0      # Body mode frequency (20-50 Hz)
    damping_ratio: float = 0.2         # Underdamped (0.1-0.3)
    mounting_resonance_hz: float = 80.0 # Mount stiffness resonance
    mounting_damping: float = 0.15      # Mount damping
```

**Vehicle Presets:**

| Class | Natural Freq | Damping | Mount Resonance | Mount Damping |
|-------|-------------|---------|----------------|---------------|
| sedan | 30 Hz | 0.20 | 80 Hz | 0.15 |
| suv | 25 Hz | 0.25 | 60 Hz | 0.18 |
| truck | 15 Hz | 0.30 | 40 Hz | 0.20 |
| motorcycle | 45 Hz | 0.15 | 120 Hz | 0.10 |

**Mounting Presets:**

| Location | Resonance | Damping | Attenuation |
|----------|-----------|---------|-------------|
| floor_structural | 80 Hz | 0.15 | 0 dB |
| dashboard | 35 Hz | 0.25 | 6 dB |
| seat_rail | 20 Hz | 0.30 | 10 dB |
| acm_location | 100 Hz | 0.10 | 0 dB |

### VehicleTransferFunction

```python
class VehicleTransferFunction:
    def __init__(self, vehicle_class: str = 'sedan',
                 mounting: str = 'floor_structural')
```

#### `VehicleTransferFunction.filter_crash_pulse(...)`

```python
def filter_crash_pulse(self, crash_pulse_ms2: np.ndarray,
                       sampling_rate: int = 1000) -> np.ndarray
```

Apply vehicle structural transfer function (cascaded 2nd-order low-pass) to crash pulse.

| Parameter | Type | Description |
|-----------|------|-------------|
| `crash_pulse_ms2` | `np.ndarray` | True crash acceleration at impact (m/s²) |
| `sampling_rate` | `int` | Sampling rate (Hz) |
| **Returns** | `np.ndarray` | Filtered acceleration at sensor mount (m/s²) |

### PreCrashVibration

```python
class PreCrashVibration:
    def __init__(self, vehicle_class: str = 'sedan')
```

#### `PreCrashVibration.generate(...)`

```python
def generate(self, duration_s: float, speed_kmh: float,
             rpm: float, road_roughness: float = 0.5,
             sampling_rate: int = 1000) -> Tuple[np.ndarray, np.ndarray]
```

Generate realistic pre-crash vibration from engine, road, and wind.

| Parameter | Type | Description |
|-----------|------|-------------|
| `duration_s` | `float` | Duration in seconds |
| `speed_kmh` | `float` | Vehicle speed (km/h) |
| `rpm` | `float` | Engine RPM |
| `road_roughness` | `float` | 0=smooth, 1=very rough |
| `sampling_rate` | `int` | Hz |
| **Returns** | `Tuple[np.ndarray, np.ndarray]` | (vibration_ms2, timestamps) |

### CrashScenario

```python
@dataclass
class CrashScenario:
    speed_kmh: float              # Vehicle speed at impact
    impact_angle_deg: float       # Impact angle (0=frontal)
    overlap_percent: float        # Barrier overlap (100=full width)
    barrier_type: str             # 'rigid', 'deformable', 'pole'
    vehicle_class: str            # 'sedan', 'suv', 'truck', 'motorcycle'
    vehicle_mass_kg: float        # Vehicle mass
    sensor_mounting: str          # Mounting location
    sensor_name: str              # Sensor model
    temperature_c: float = 25.0
    road_roughness: float = 0.5
    engine_rpm: float = 3000
    pre_crash_duration_s: float = 2.0
```

### RealisticCrashSimulator

```python
class RealisticCrashSimulator:
    def __init__(self)
```

#### `RealisticCrashSimulator.simulate_crash(scenario: CrashScenario) -> dict`

Run the complete simulation chain: Impact → Vehicle → Vibration → Sensor → VISTA.

**Returns:** `dict` with keys:

| Key | Description |
|-----|-------------|
| `true_crash_pulse` | Original crash acceleration (m/s²) |
| `vehicle_response` | After vehicle transfer function |
| `sensor_output` | MEMS sensor output dict |
| `pre_crash_vibration` | Pre-crash vibration environment |
| `vista_result` | VISTA algorithm detection result |
| `scenario` | Input CrashScenario |
| `sampling_rate` | 1000 Hz |

---

## 4. eskf.py

**Module Purpose:** 15-state Error-State Kalman Filter for vehicle dynamics estimation with crash-mode adaptation.

### CrashState

```python
class CrashState(Enum):
    PRE_CRASH = "pre_crash"     # Normal ESKF with gravity convergence
    CRASH_ONSET = "crash_onset" # Freeze bias, inflate process noise
    POST_CRASH = "post_crash"   # Resume with inflated measurement cov
```

### ESKFConfig

```python
@dataclass
class ESKFConfig:
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

    # Limits
    max_gyro_bias: float = 0.5              # rad/s
    max_accel_bias: float = 2.0             # m/s²
    quat_norm_threshold: float = 1e-6
```

### ESKF

```python
class ESKF:
    def __init__(self, config: Optional[ESKFConfig] = None)
```

15-state Error-State Kalman Filter: position(3) + velocity(3) + attitude(3) + gyro_bias(3) + accel_bias(3).

#### Core Methods

##### `predict(gyro, accel, dt)`

```python
def predict(self, gyro: np.ndarray, accel: np.ndarray, dt: float)
```

ESKF prediction step with crash onset detection.

| Parameter | Type | Description |
|-----------|------|-------------|
| `gyro` | `np.ndarray` | Gyroscope measurement (rad/s) [gx, gy, gz] |
| `accel` | `np.ndarray` | Accelerometer measurement (m/s²) [ax, ay, az] |
| `dt` | `float` | Time step (seconds) |

##### `update_accel(accel_meas)`

```python
def update_accel(self, accel_meas: np.ndarray)
```

Update with accelerometer measurement using gravity as reference. Automatically skips during crash onset/post-crash phases.

##### `update_gyro(gyro_meas)`

```python
def update_gyro(self, gyro_meas: np.ndarray)
```

Update with gyroscope measurement using zero-rate assumption for bias estimation.

##### `update_gps(gps_position, gps_velocity)`

```python
def update_gps(self, gps_position: np.ndarray, gps_velocity: np.ndarray)
```

Update with GPS position and velocity.

##### `update(gyro, accel, gps_position=None, gps_velocity=None, dt=0.001)`

```python
def update(self, gyro: np.ndarray, accel: np.ndarray,
           gps_position: Optional[np.ndarray] = None,
           gps_velocity: Optional[np.ndarray] = None,
           dt: float = 0.001)
```

Combined predict + update step.

#### State Access Methods

| Method | Returns |
|--------|---------|
| `get_velocity()` | `np.ndarray` (3,) current velocity (m/s) |
| `get_position()` | `np.ndarray` (3,) current position (m) |
| `get_attitude()` | `np.ndarray` (4,) quaternion [w, x, y, z] |
| `get_attitude_euler()` | `np.ndarray` (3,) [roll, pitch, yaw] (rad) |
| `get_gyro_bias()` | `np.ndarray` (3,) gyro bias (rad/s) |
| `get_accel_bias()` | `np.ndarray` (3,) accel bias (m/s²) |
| `get_covariance_diagonal()` | `np.ndarray` (15,) 1-sigma uncertainties |

#### Quaternion Utilities (Static Methods)

| Method | Description |
|--------|-------------|
| `quaternion_multiply(q1, q2)` | Hamilton product q1 ⊗ q2 |
| `quaternion_inverse(q)` | Conjugate for unit quaternions |
| `quaternion_normalize(q)` | Normalize to unit length |
| `quaternion_to_rotation(q)` | Convert to 3×3 rotation matrix R(q) |
| `rotation_to_quaternion(R)` | Shepperd's method |
| `skew_symmetric(v)` | 3×3 skew matrix [v]× |

#### Crash Mode

| Method | Description |
|--------|-------------|
| `set_crash_state(state)` | Manually set crash state |
| `store_state()` | Store state for RTS smoother |
| `smooth()` | RTS backward pass for offline post-processing |
| `clear_stored_states()` | Clear stored states |

**ESKF State Vector:**
```
δx = [δp(3), δv(3), δθ(3), δbg(3), δba(3)]
 15 DOF: position, velocity, attitude error (rotation vector),
         gyro bias, accel bias
```

---

## 5. detection_cascade.py

**Module Purpose:** 5-method detection cascade with weighted fusion for crash declaration.

### CascadeConfig

```python
@dataclass
class CascadeConfig:
    accel_gate_g: float = 3.0              # Minimum |a| gate (g)
    weight_pdtsa: float = 0.30             # PDTSA detector weight
    weight_energy_flux: float = 0.20       # Energy flux weight
    weight_wavelet: float = 0.20           # Wavelet weight
    weight_kurtosis: float = 0.15          # Kurtosis weight
    weight_template: float = 0.15          # Template match weight
    fusion_threshold: float = 0.50         # Fused score threshold
    energy_flux_threshold_w: float = 500_000.0  # Watts
    energy_mass_kg: float = 1500.0         # Vehicle mass
    wavelet_level: int = 3                 # Decomposition depth
    wavelet_crash_bands: List[int] = [0, 1, 2]  # Crash-relevant bands
    wavelet_energy_threshold: float = 0.40 # Fraction threshold
    kurtosis_threshold: float = 3.0        # Excess kurtosis threshold
    template_match_threshold: float = 0.50 # NCC peak threshold
    vehicle_class: VehicleClass = VehicleClass.UNKNOWN
    sampling_rate: int = 1000              # Hz
```

### DetectorResult

```python
@dataclass
class DetectorResult:
    name: str                # Detector name
    confidence: float        # [0, 1]
    triggered: bool
    detail: Optional[Dict]   # Detector-specific details
```

### CascadeResult

```python
@dataclass
class CascadeResult:
    detected: bool
    fused_score: float
    gate_passed: bool
    detectors: List[DetectorResult]
    n_detectors_triggered: int
    fusion_threshold: float
    accel_peak_g: float
```

### DetectionCascade

```python
class DetectionCascade:
    def __init__(self, config: Optional[CascadeConfig] = None)
```

#### `detect(accel_ms2, timestamps_s) -> CascadeResult`

Run the full 5-detector cascade.

| Parameter | Type | Description |
|-----------|------|-------------|
| `accel_ms2` | `np.ndarray` | (N, 3) acceleration in m/s² |
| `timestamps_s` | `np.ndarray` | (N,) timestamps in seconds |
| **Returns** | `CascadeResult` | Fused detection decision |

#### `detect_streaming(accel_sample, timestamp_s, state) -> Tuple[bool, Dict]`

Sample-by-sample streaming interface for real-time use.

| Parameter | Type | Description |
|-----------|------|-------------|
| `accel_sample` | `np.ndarray` | (3,) single acceleration sample |
| `timestamp_s` | `float` | Sample timestamp |
| `state` | `Optional[Dict]` | Persistent state dict |
| **Returns** | `Tuple[bool, Dict]` | (crash_declared, updated_state) |

**5 Detectors:**

1. **PDTSA** — Jerk magnitude + sustain duration + asymmetry ratio
2. **Energy Flux** — Rate of kinetic energy change: d(½mv²)/dt = m·|a|·|v|
3. **Wavelet Packet** — Haar decomposition, fraction of energy in crash bands
4. **Kurtosis** — Excess kurtosis of jerk signal (da/dt)
5. **Template Matching** — Normalized cross-correlation with haversine/sine/triangle templates

---

## 6. reconstruction.py

**Module Purpose:** Post-crash forensic reconstruction: delta-V, PDOF, injury risk, velocity history.

### ReconstructionConfig

```python
@dataclass
class ReconstructionConfig:
    sampling_rate: int = 1000
    vehicle_mass_kg: float = 1500.0
    restitution_coefficient: float = 0.15   # 0 ≤ e ≤ 1
    bootstrap_samples: int = 2000
    bootstrap_seed: int = 42
    confidence_level: float = 0.95          # 95% CI
    saturation_threshold_g: float = 85.0
    use_saturation_correction: bool = True
    pdof_window_ms: float = 10.0
    pdof_min_duration_ms: float = 5.0
    baseline_pre_crash_ms: float = 20.0
    baseline_method: str = "mean"
    injury_crash_mode: CrashMode = CrashMode.ALL
    injury_age_group: str = "adult"
```

### DeltaVEstimator

```python
class DeltaVEstimator:
    def __init__(self, config: ReconstructionConfig)
```

#### `estimate(accel_g, time_s) -> DeltaVResult`

Hybrid energy-momentum delta-V estimator with bootstrap CI.

| Parameter | Type | Description |
|-----------|------|-------------|
| `accel_g` | `np.ndarray` | Acceleration in g (1D, positive = deceleration) |
| `time_s` | `np.ndarray` | Time array in seconds |
| **Returns** | `DeltaVResult` | Full estimation result |

**DeltaVResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `delta_v_ms` | `float` | Delta-V (m/s) |
| `delta_v_kmh` | `float` | Delta-V (km/h) |
| `delta_v_mph` | `float` | Delta-V (mph) |
| `ci_lower_ms` / `ci_upper_ms` | `float` | 95% CI bounds (m/s) |
| `ci_lower_kmh` / `ci_upper_kmh` | `float` | 95% CI bounds (km/h) |
| `method` | `str` | `"hybrid_energy_momentum"` |
| `saturation_detected` | `bool` | True if sensor saturated |
| `saturation_correction_applied` | `bool` | True if lower-bound used |
| `energy_delta_v_ms` | `float` | Energy-based estimate |
| `momentum_delta_v_ms` | `float` | Momentum-based estimate |
| `combined_delta_v_ms` | `float` | Combined (restitution-corrected) |
| `confidence` | `float` | [0, 1] |

### PDOFEstimator

```python
class PDOFEstimator:
    def __init__(self, config: ReconstructionConfig)
```

#### `estimate(accel_x_g, accel_y_g, time_s, accel_z_g=None) -> PDOFResult`

Principal Direction of Force from dual-axis acceleration.

| Parameter | Type | Description |
|-----------|------|-------------|
| `accel_x_g` | `np.ndarray` | X-axis acceleration (g) |
| `accel_y_g` | `np.ndarray` | Y-axis acceleration (g) |
| `time_s` | `np.ndarray` | Time array (s) |
| `accel_z_g` | `Optional[np.ndarray]` | Z-axis (optional) |
| **Returns** | `PDOFResult` | |

**PDOFResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `angle_deg` / `angle_rad` | `float` | PDOF angle |
| `confidence` | `float` | [0, 1] |
| `signal_quality` | `SignalQuality` | HIGH/MEDIUM/LOW/INSUFFICIENT |
| `peak_accel_g` | `float` | Peak acceleration magnitude |
| `velocity_direction_deg` | `float` | Velocity change direction |

### InjuryRiskAssessor

```python
class InjuryRiskAssessor:
    def __init__(self, config: ReconstructionConfig)
```

#### `assess(delta_v_kmh) -> InjuryRiskResult`

NHTSA injury risk assessment from delta-V using logistic regression curves.

**InjuryRiskResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `mais2_plus` | `float` | MAIS 2+ probability |
| `mais3_plus` | `float` | MAIS 3+ probability |
| `mais4_plus` | `float` | MAIS 4+ probability |
| `mais5_plus` | `float` | MAIS 5+ probability |
| `mais6` | `float` | MAIS 6 (fatal) probability |
| `head_injury_risk` | `float` | AIS 2+ head injury probability |
| `thorax_injury_risk` | `float` | AIS 2+ thorax probability |
| `femur_injury_risk` | `float` | AIS 2+ femur probability |
| `risk_category` | `str` | none/low/moderate/high/critical |

#### `compute_risk_curve(delta_v_range_kmh, n_points=200) -> Dict[str, np.ndarray]`

Compute injury risk curves over a range of delta-V values.

### VelocityHistoryReconstructor

```python
class VelocityHistoryReconstructor:
    def __init__(self, config: ReconstructionConfig)
```

#### `reconstruct(accel_x_g, time_s, accel_y_g=None) -> VelocityHistoryResult`

Full velocity-time history with phase decomposition.

**VelocityHistoryResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `time_s` | `np.ndarray` | Time vector |
| `velocity_ms` | `np.ndarray` | Velocity (m/s) |
| `velocity_kmh` | `np.ndarray` | Velocity (km/h) |
| `acceleration_g` | `np.ndarray` | Baseline-corrected accel (g) |
| `jerk_gps` | `np.ndarray` | Jerk (g/s) |
| `phases` | `List[PhaseInfo]` | Decomposed crash phases |
| `onset_time_ms` | `float` | Time of crash onset |
| `peak_time_ms` | `float` | Time of peak acceleration |
| `peak_acceleration_g` | `float` | Peak acceleration (g) |
| `final_velocity_ms` | `float` | Final velocity (m/s) |
| `duration_ms` | `float` | Total crash duration (ms) |

### CrashReconstructor

```python
class CrashReconstructor:
    def __init__(self, config: Optional[ReconstructionConfig] = None)
```

#### `reconstruct_full(accel_x_g, time_s, accel_y_g=None, accel_z_g=None) -> dict`

Complete crash reconstruction orchestrating all 4 sub-modules.

**Returns:** `dict` with keys: `delta_v`, `pdof`, `injury`, `velocity_history`, `config`.

---

## 7. audio_pipeline.py

**Module Purpose:** 6-stage crash-specific audio forensic pipeline with evidence-grade output.

### AudioPipelineConfig

```python
@dataclass
class AudioPipelineConfig:
    sample_rate: int = 48_000       # IM67D130A operating rate
    n_channels: int = 4             # MEMS array channels
    bit_depth: int = 16
    ster_frame_ms: float = 1.0      # STER analysis frame
    ster_lookback_ms: float = 20.0  # Background energy window
    ster_threshold: float = 6.0     # STER ratio threshold
    mfcc_n_coeffs: int = 13         # MFCC coefficients
    mfcc_n_fft: int = 512           # FFT window
    mfcc_hop_length: int = 240      # Hop (5ms at 48kHz)
    classification_threshold: float = 0.3
    mvdr_smoothing: float = 0.01    # Diagonal loading
    cross_corr_max_lag_ms: float = 50.0
    alignment_precision_ms: float = 0.1
    swgde_compliant: bool = True
```

### CrashEventClass

```python
class CrashEventClass(IntEnum):
    FRONTAL_FULL = 0
    FRONTAL_OFFSET = 1
    FRONTAL_OBLIQUE = 2
    REAR_IMPACT = 3
    SIDE_DRIVER = 4
    SIDE_PASSENGER = 5
    ROLLOVER = 6
    PEDESTRIAN = 7
    CYCLIST = 8
    ANIMAL = 9
    DEBRIS = 10
    NON_CRASH = 11
```

### AudioForensicPipeline

```python
class AudioForensicPipeline:
    def __init__(self, config: Optional[AudioPipelineConfig] = None,
                 shared_secret: Optional[bytes] = None)
```

#### `process(audio, imu_data=None, imu_timestamps=None, audio_start_time=0.0) -> PipelineResult`

Run the full 6-stage pipeline.

| Parameter | Type | Description |
|-----------|------|-------------|
| `audio` | `np.ndarray` | (N,) or (N, C) audio at 48kHz, normalized [-1,1] |
| `imu_data` | `Optional[np.ndarray]` | (M, 3) IMU accel (m/s²) |
| `imu_timestamps` | `Optional[np.ndarray]` | (M,) IMU timestamps (s) |
| `audio_start_time` | `float` | Audio stream start time (s) |
| **Returns** | `PipelineResult` | |

**PipelineResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Pipeline success |
| `events` | `List[ImpulseEvent]` | Detected impulses |
| `classifications` | `List[ClassificationResult]` | 12-class classifications |
| `energy_profiles` | `List[EnergyProfile]` | SPL and severity |
| `separated_sources` | `List[List[SeparatedSource]]` | MVDR beamformed sources |
| `alignments` | `List[TemporalAlignment]` | Audio↔IMU alignment |
| `forensic_packages` | `List[ForensicAudioPackage]` | Cryptographic evidence |
| `processing_time_ms` | `float` | Total processing time |

**6 Pipeline Stages:**

1. **Impulse Detection** — STER broadband energy spike detection (±0.1ms)
2. **Event Classification** — 12-class MFCC nearest-centroid classifier
3. **Energy Characterization** — Peak SPL, severity assessment
4. **Source Separation** — MVDR beamforming for 4-channel array
5. **Temporal Alignment** — GCC-PHAT audio↔IMU cross-correlation (±0.1ms)
6. **Forensic Chain** — SHA-256 + HMAC-SHA256, SWGDE-compliant package

### Stage Classes

| Class | Stage | Description |
|-------|-------|-------------|
| `ImpulseDetector` | 1 | STER-based broadband impulse detection |
| `EventClassifier` | 2 | 12-class MFCC classifier with mel filterbank |
| `EnergyCharacterizer` | 3 | SPL estimation and severity classification |
| `MVDRBeamformer` | 4 | Minimum Variance Distortionless Response beamforming |
| `TemporalAligner` | 5 | GCC-PHAT cross-correlation alignment |
| `ForensicAudioProcessor` | 6 | SHA-256 + HMAC evidence packaging |

---

## 8. visual_pipeline.py

**Module Purpose:** Camera-based forensic evidence pipeline for crash documentation.

### VisualPipelineConfig

```python
@dataclass
class VisualPipelineConfig:
    front_camera: CameraConfig    # 4K (3840×2160) @ 30/60fps
    rear_camera: CameraConfig     # 2K (2560×1440) @ 30/60fps
    pre_crash_buffer_s: float = 5.0
    quality_blur_threshold: float = 100.0
    quality_exposure_target: float = 128.0
    quality_noise_threshold: float = 30.0
```

### VisualForensicPipeline

```python
class VisualForensicPipeline:
    def __init__(self, config: Optional[VisualPipelineConfig] = None)
```

#### `start_recording(event_id: str = "default")`

Start recording from all cameras.

#### `capture_pre_crash_frames(n_frames: int = 30)`

Capture pre-crash frames from circular buffer.

#### `trigger_burst()`

Trigger burst capture on crash detection (60fps × 2s = 120 frames per camera).

#### `stop_recording()`

Stop recording from all cameras.

#### `detect_key_frames() -> Dict[str, List[Frame]]`

Detect key frames across all cameras.

**Key Frame Types:**
- **FIRST_POST_CRASH** — First frame after crash onset
- **BEST_QUALITY** — Clearest frame for evidence
- **SCENE_CONTEXT** — Widest context for reconstruction

#### `generate_evidence_package(event_id, device_id) -> VisualEvidencePackage`

Generate tamper-evident visual evidence package with SHA-256 + SHA-3 + HMAC.

#### `verify_evidence_package(package) -> Dict[str, Any]`

Verify integrity of a visual evidence package.

**Returns:** `{"valid": bool, "checks": dict, "errors": list}`

### ImageQualityAnalyzer

```python
class ImageQualityAnalyzer:
    def __init__(self, config: Optional[VisualPipelineConfig] = None)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `compute_blur_score(image)` | `float` | Laplacian variance (higher=sharper) |
| `compute_exposure_score(image)` | `Dict` | mean_brightness, std, under/overexposed % |
| `compute_noise_score(image)` | `float` | MAD noise estimate (lower=better) |
| `analyze_frame(image)` | `Dict` | Full quality analysis with overall score |

---

## 9. evidence_chain.py

**Module Purpose:** Cryptographic evidence integrity with dual hashing (SHA-256 + SHA-3) and HMAC authentication.

### EvidenceRecord

```python
@dataclass
class EvidenceRecord:
    evidence_id: str              # UUID-style unique identifier
    payload: Dict[str, Any]       # Evidence data
    timestamp_unix: float         # Unix epoch seconds
    sha256_hash: str              # SHA-256 hex digest
    sha3_hash: str                # SHA3-256 (Keccak) hex digest
    hmac_signature: str           # HMAC-SHA256 hex signature
    algorithm_versions: Dict[str, str]  # Algorithm documentation
```

### EvidenceChain

```python
class EvidenceChain:
    def __init__(self, shared_secret: Optional[bytes] = None,
                 sequence_start: int = 0)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `shared_secret` | `Optional[bytes]` | `None` | HMAC key (≥16 bytes) |
| `sequence_start` | `int` | `0` | Initial sequence number |

#### `create_record(payload, evidence_id=None, timestamp=None) -> EvidenceRecord`

Create a new tamper-evident evidence record.

#### `verify(record, check_sequence=True, sequence_number=None) -> Dict[str, Any]`

Verify integrity and authenticity. Checks: SHA-256, SHA-3, HMAC, timestamp.

#### `verify_payload(record, original_payload) -> bool`

Quick payload comparison.

#### Serialization

| Method | Description |
|--------|-------------|
| `to_dict(record)` | Convert to JSON-safe dict |
| `from_dict(data)` | Reconstruct from dict |
| `to_json(record)` | Serialize to JSON string |
| `from_json(json_str)` | Deserialize from JSON |

---

## 10. deployment.py

**Module Purpose:** Fleet management with TPM-like device identity, telemetry, OTA updates, and evidence chain.

### DeviceRegistry

```python
class DeviceRegistry:
    def __init__(self)
```

| Method | Description |
|--------|-------------|
| `register_device(hardware_seed, manufacturer, model)` | Register with TPM-like identity |
| `get_device(device_id)` | Get device identity |
| `verify_identity(device_id, tpm_pubkey)` | Verify TPM public key |
| `update_status(device_id, status)` | Update device status |
| `heartbeat(device_id)` | Record heartbeat |
| `get_stale_devices(timeout_s)` | Get devices past timeout |
| `list_devices(status)` | List devices with optional filter |

### TelemetryCollector

```python
class TelemetryCollector:
    def __init__(self, aggregation_window_s: float = 60.0)
```

| Method | Description |
|--------|-------------|
| `ingest(device_id, telemetry_type, value, timestamp_s)` | Ingest telemetry point |
| `get_entries(device_id, telemetry_type, since_s)` | Query entries |
| `aggregate(device_id, telemetry_type, window_s)` | Min/max/mean aggregation |
| `get_latest_telemetry(device_id)` | Latest per type |

### OTAUpdateManager

```python
class OTAUpdateManager:
    def __init__(self)
```

| Method | Description |
|--------|-------------|
| `create_package(version, description, firmware_data)` | Create OTA package |
| `schedule_update(device_id, package_id)` | Schedule update |
| `simulate_update(device_id, success, from_version, to_version)` | Simulate execution |
| `verify_package(package_id, firmware_data)` | Verify checksum |

### FleetEvidenceChain

```python
class FleetEvidenceChain:
    def __init__(self, shared_secret: bytes)
```

| Method | Description |
|--------|-------------|
| `append_record(device_id, event_type, payload)` | Append to hash-chained ledger |
| `verify_chain(device_id)` | Verify full chain integrity |

### FleetHealthMonitor

```python
class FleetHealthMonitor:
    def __init__(self, heartbeat_timeout_s=300.0, battery_warning_pct=20.0,
                 storage_warning_gb=5.0, temp_warning_c=70.0)
```

| Method | Description |
|--------|-------------|
| `check_heartbeat(device)` | Alert if stale |
| `check_battery(device_id, battery_pct)` | Alert if low |
| `check_storage(device_id, free_gb)` | Alert if low |
| `check_cpu_temp(device_id, temp_c)` | Alert if high |
| `check_crash_event(device_id, crash_data)` | Alert for crash |
| `acknowledge_alert(alert_id)` | Acknowledge alert |

### FleetManager

```python
class FleetManager:
    def __init__(self, shared_secret: bytes = b"fleet-evidence-secret-32b!")
```

Top-level orchestrator coordinating all fleet components.

| Method | Description |
|--------|-------------|
| `register_device(hardware_seed)` | Register + evidence record |
| `process_heartbeat(device_id, telemetry_data)` | Heartbeat + telemetry + health |
| `record_crash_event(device_id, crash_data)` | Record crash + alert |
| `get_fleet_status()` | Comprehensive fleet status |

---

## Package Exports

```python
# vista_hil/__init__.py
from vista_hil.mems_simulator import MEMSSensorSimulator, SensorConfig, load_sensor
from vista_hil.crash_pulse import CrashPulseGenerator, CrashPulseConfig
from vista_hil.hil_simulation import HILSimulation, HILConfig, SimulationResult
```

**Quick Start:**
```python
from vista_hil import load_sensor, CrashPulseGenerator
import numpy as np

# Generate crash pulse
gen = CrashPulseGenerator(seed=42)
t, accel, gyro = gen.generate(peak_g=50, duration_ms=100, delta_v_kmh=40)

# Simulate sensor
sensor = load_sensor("mpu6050", sampling_rate=1000)
result = sensor.simulate(accel, gyro)

# Check saturation
print(f"Peak: {np.max(np.abs(result['accel']))/9.80665:.1f}g")
print(f"Saturated: {np.any(result['saturation'])}")
```
