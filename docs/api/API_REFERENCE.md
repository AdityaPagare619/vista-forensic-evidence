# VISTA 2.0 — API Reference
**Version:** 2.0.0 | **Date:** 2026-06-14

---

## Package: vista_hil

### Import

```python
from vista_hil import (
    MEMSSensorSimulator, SensorConfig, load_sensor,
    CrashPulseGenerator, CrashPulseConfig,
    HILSimulation, HILConfig, SimulationResult
)
from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass
from vista_hil.detection_cascade import DetectionCascade
from vista_hil.reconstruction import CrashReconstructor
from vista_hil.audio_pipeline import AudioForensicPipeline
from vista_hil.visual_pipeline import VisualAnalyticsPipeline
from vista_hil.evidence_chain import EvidenceChain
from vista_hil.deployment import FleetManager
from vista_hil.eskf import ErrorStateKalmanFilter
from vista_hil.realistic_simulation import RealisticCrashSimulator, CrashScenario
```

---

## MEMS Sensor Simulator

### load_sensor(name, sampling_rate=1000) → MEMSSensorSimulator

Load a sensor by name from YAML config files.

```python
sensor = load_sensor('mpu6050', sampling_rate=1000)
# Available: 'mpu6050', 'h3lis331dl', 'iam20680hp'
```

### MEMSSensorSimulator.simulate(crash_pulse, crash_gyro=None, temperature=25.0, start_time=0.0) → dict

Simulate sensor response to a crash pulse.

| Parameter | Type | Description |
|-----------|------|-------------|
| crash_pulse | np.ndarray (N×3) | True acceleration in m/s² [ax, ay, az] |
| crash_gyro | np.ndarray (N×3) or None | True angular rate in rad/s [gx, gy, gz] |
| temperature | float | Sensor temperature in °C (default: 25) |
| start_time | float | Time offset in seconds (default: 0) |

**Returns:** dict with keys `timestamp`, `accel`, `gyro`, `saturation`, `gyro_saturation`, `temperature`, `sampling_rate`, `sensor_name`

**Processing chain:** Range clipping → Bandwidth limiting → Noise injection → Temperature drift → Cross-axis coupling → Bias + offset

---

## Crash Pulse Generator v2

### CrashPulseGeneratorV2.generate(config) → (timestamps, accel_ms2, gyro_rads)

Generate realistic multi-peak crash pulse.

```python
config = CrashPulseConfig(
    vehicle_class='sedan',   # 'sedan','suv','truck','motorcycle'
    speed_kmh=50,            # Vehicle speed at impact
    overlap_percent=100,     # Barrier overlap percentage
    direction='frontal',     # 'frontal','rear','left_side','right_side'
    vehicle_mass_kg=1500,    # Vehicle mass in kg
)
gen = CrashPulseGeneratorV2()
t, accel, gyro = gen.generate(config)
```

**Physics:** Multi-peak parametric model with published NCAP/IIHS reference shapes. Each peak represents structural folding event. Amplitudes calibrated to preserve delta-V = initial speed.

---

## PDTSA v2

### PDTSAv2(config=None).detect(accel_ms2, timestamps_s, pitch_rad=0.0) → DeltaVResult

Run full 4-tier detection + reconstruction pipeline.

```python
config = PDTSAConfig(vehicle_class=VehicleClass.SEDAN)
pdtsa = PDTSAv2(config)
result = pdtsa.detect(accel_ms2, timestamps)
```

**Returns:** DeltaVResult with delta_v_ms, delta_v_kmh, ci_lower, ci_upper, pdof_degrees, saturated, features (PDTSAFeatures)

**Detection logic:**
1. Pre-check: peak acceleration > accel_gate_g (3.0g)
2. Tier 1: Jerk ≥ 200 g/s
3. Tier 2: Sustain ≥ 30ms
4. Tier 3: Asymmetry soft gate (R_a = N_decay/N_rise, score = min(1, R_a/2))
5. Tier 4: C = 0.4s_j + 0.3s_a + 0.3s_s + b_OBD + b_audio ≥ 0.65

---

## Detection Cascade

### DetectionCascade(config).detect(accel, gyro, obd_data=None, audio_data=None) → DetectionResult

5-method weighted fusion detection.

```python
cascade = DetectionCascade()
result = cascade.detect(accel, gyro)
print(result.detected, result.confidence, result.delta_v_kmh)
```

**Methods:** Energy Flux (0.30) + PDTSA (0.20) + Wavelet Packet (0.20) + Kurtosis (0.15) + Template (0.15)

---

## Reconstruction

### CrashReconstructor(ekf, pdtsa).reconstruct(accel, timestamps, gyro=None, pitch_rad=0.0) → ReconstructionResult

Full crash reconstruction: delta-V + PDOF + injury risk + velocity history.

```python
recon = CrashReconstructor()
result = recon.reconstruct(accel, timestamps)
print(result.delta_v_kmh, result.pdof_degrees, result.injury_prob)
```

---

## Error-State Kalman Filter

### ErrorStateKalmanFilter().predict(imu_data, dt) / .update_gps(pos, vel) / .update_obd(vel) / .get_state()

15-state ESKF with quaternion attitude representation.

**States:** position(3) + velocity(3) + quaternion(4) + gyro_bias(3) + accel_bias(3)

```python
ekf = ErrorStateKalmanFilter()
ekf.predict(filtered_imu, dt=0.001)
ekf.update_obd(obd_velocity)
state = ekf.get_state()
```

---

## Evidence Chain

### EvidenceChain(secret_key).create(payload_dict) → EvidenceRecord
### EvidenceChain(secret_key).verify(record) → dict (all checks)

```python
chain = EvidenceChain(secret_key=b'vista-key-1234')
record = chain.create({'delta_v_kmh': 45.2, 'pdof': -1.2})
result = chain.verify(record)
# result['overall'] == True
```

---

## Realistic Simulation

### RealisticCrashSimulator().simulate_crash(scenario) → dict

Complete simulation chain: Impact → Vehicle TF → Sensor → VISTA.

```python
sim = RealisticCrashSimulator()
scenario = CrashScenario(
    speed_kmh=50, impact_angle_deg=0, overlap_percent=100,
    barrier_type='rigid', vehicle_class='sedan',
    sensor_mounting='floor_structural', sensor_name='mpu6050'
)
result = sim.simulate_crash(scenario)
print(result['vista_result']['detected'], result['vista_result']['delta_v_kmh'])
```

---

## FleetManager

### FleetManager().register_device(info) / .submit_telemetry(id, data) / .check_health()

Fleet management with device identity, telemetry, and health monitoring.

```python
fleet = FleetManager()
device_id = fleet.register_device({'serial': 'VISTA-001', 'model': 'VISTA-Core'})
fleet.submit_telemetry(device_id, {'speed_kmh': 80, 'event_detected': False})
health = fleet.check_health(device_id)
```

---

*This API reference covers all public interfaces in VISTA 2.0. Internal implementation details are documented in source code comments.*
