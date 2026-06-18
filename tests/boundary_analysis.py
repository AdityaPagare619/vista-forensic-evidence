"""Boundary analysis for VISTA 2.0 stress test."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vista_hil.realistic_simulation import RealisticCrashSimulator, CrashScenario, VehicleTransferConfig
from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass
from vista_hil import load_sensor
import numpy as np

class EnhancedCrashSimulator(RealisticCrashSimulator):
    def simulate_crash_with_shape(self, scenario, shape='haversine'):
        sampling_rate = 1000
        crash_pulse = self._generate_crash_pulse_shaped(scenario, sampling_rate, shape)
        vtf = VehicleTransferConfig(
            natural_freq_hz=self._get_vehicle_freq(scenario.vehicle_class),
            damping_ratio=self._get_vehicle_damping(scenario.vehicle_class)
        )
        vehicle_response = self._apply_transfer_function(crash_pulse, vtf, sampling_rate)
        vibration, vib_timestamps = self._generate_vibration(scenario, sampling_rate)
        sensor_output = self._simulate_sensor(vehicle_response, scenario, sampling_rate)
        vista_result = self._run_vista(sensor_output, scenario)
        return {'true_crash_pulse': crash_pulse, 'vehicle_response': vehicle_response,
                'sensor_output': sensor_output, 'vista_result': vista_result,
                'scenario': scenario, 'sampling_rate': sampling_rate, 'shape': shape}

    def _generate_crash_pulse_shaped(self, scenario, fs, shape):
        v_ms = scenario.speed_kmh / 3.6
        kinetic_energy = 0.5 * scenario.vehicle_mass_kg * v_ms**2
        crush_time_s = 0.05
        avg_force = kinetic_energy / (0.5 * v_ms * crush_time_s)
        peak_accel_g = avg_force / (scenario.vehicle_mass_kg * 9.81) * 1.5
        overlap_factor = scenario.overlap_percent / 100.0
        peak_accel_g *= overlap_factor
        n_samples = int(crush_time_s * 1000)
        t = np.arange(n_samples) / 1000.0
        shapes = {
            'haversine': lambda t, d: np.sin(np.pi * t / d) ** 2,
            'half_sine': lambda t, d: np.sin(np.pi * t / d),
            'triangular': lambda t, d: 1.0 - np.abs(2 * t / d - 1.0),
        }
        pulse_g = peak_accel_g * shapes.get(shape, shapes['haversine'])(t, crush_time_s)
        pulse_ms2 = np.zeros((n_samples, 3))
        angle_rad = np.radians(scenario.impact_angle_deg)
        pulse_ms2[:, 0] = pulse_g * 9.81 * np.cos(angle_rad)
        pulse_ms2[:, 1] = pulse_g * 9.81 * np.sin(angle_rad)
        pulse_ms2[:, 2] = 9.81
        return pulse_ms2

sim = EnhancedCrashSimulator()

def test(speed, angle, overlap, vehicle, sensor, mounting, temp=25, rough=0.3, shape='haversine', label=''):
    mass_map = {'sedan': 1400, 'suv': 2200, 'truck': 8000, 'motorcycle': 200}
    barrier = 'rigid' if overlap > 0 else 'none'
    sc = CrashScenario(speed_kmh=speed, impact_angle_deg=angle, overlap_percent=overlap,
        barrier_type=barrier, vehicle_class=vehicle, vehicle_mass_kg=mass_map[vehicle],
        sensor_mounting=mounting, sensor_name=sensor,
        temperature_c=temp, road_roughness=rough, engine_rpm=2500)
    result = sim.simulate_crash_with_shape(sc, shape)
    vr = result['vista_result']
    sat_arr = result['sensor_output'].get('saturation', None)
    sat_pct = 0.0
    if sat_arr is not None and len(sat_arr) > 0:
        if sat_arr.ndim > 1:
            sat_pct = float(np.mean(sat_arr.any(axis=1)) * 100)
        else:
            sat_pct = float(np.mean(sat_arr) * 100)
    print(f"  {label:45s} det={vr['detected']!s:5s} peak={vr['peak_accel_g']:6.1f}g "
          f"conf={vr['confidence']:.3f} dV={vr['delta_v_kmh']:5.1f} sat={sat_pct:.0f}%")

print("=" * 90)
print("VISTA 2.0 — DETECTION BOUNDARY ANALYSIS")
print("=" * 90)

print("\n--- LOW-SPEED CRASH DETECTION (frontal, sedan, mpu6050, floor) ---")
for s in [5, 8, 10, 12, 15, 20, 25, 30]:
    test(s, 0, 100, 'sedan', 'mpu6050', 'floor_structural', label=f'{s} km/h frontal')

print("\n--- MOTORCYCLE CRASH DETECTION (dashboard mount) ---")
for s in [10, 15, 20, 25, 30, 40, 50]:
    test(s, 15, 50, 'motorcycle', 'mpu6050', 'dashboard', label=f'{s} km/h motorcycle')

print("\n--- SEAT RAIL MOUNTING (most attenuated, 10dB loss) ---")
for s in [20, 30, 40, 50, 60, 70, 80]:
    test(s, 0, 100, 'sedan', 'mpu6050', 'seat_rail', label=f'{s} km/h seat_rail')

print("\n--- DASHBOARD MOUNTING (6dB loss) ---")
for s in [20, 30, 40, 50, 60, 70]:
    test(s, 0, 100, 'sedan', 'mpu6050', 'dashboard', label=f'{s} km/h dashboard')

print("\n--- LOW OVERLAP (25%) ---")
for s in [20, 30, 40, 50, 60, 70, 80]:
    test(s, 0, 25, 'sedan', 'mpu6050', 'floor_structural', label=f'{s} km/h 25% overlap')

print("\n--- OBLIQUE 75 DEGREES (worst case) ---")
for s in [30, 50, 70, 90]:
    test(s, 75, 50, 'sedan', 'mpu6050', 'floor_structural', label=f'{s} km/h 75deg oblique')

print("\n--- TEMPERATURE EXTREMES ---")
for t in [-20, -10, 0, 40, 50, 60]:
    test(50, 0, 100, 'sedan', 'mpu6050', 'floor_structural', temp=t, label=f'50 km/h temp={t}C')

print("\n--- HIGH ROUGHNESS + LOW OVERLAP ---")
for r in [0.7, 0.9]:
    for o in [25, 50]:
        test(40, 0, o, 'sedan', 'mpu6050', 'floor_structural', rough=r,
             label=f'40 km/h overlap={o}% rough={r}')

print("\n--- IAM20680HP (same 16g range as MPU6050) ---")
for s in [20, 35, 50, 65, 80]:
    test(s, 0, 100, 'sedan', 'iam20680hp', 'floor_structural', label=f'{s} km/h iam20680hp')

print("\n--- H3LIS331DL (400g, should never saturate) ---")
for s in [30, 60, 90, 120]:
    test(s, 0, 100, 'sedan', 'h3lis331dl', 'floor_structural', label=f'{s} km/h h3lis331dl')

print("\n--- CRASH SHAPE VARIATION ---")
for shape in ['haversine', 'half_sine', 'triangular']:
    for s in [20, 40, 60, 80]:
        test(s, 0, 100, 'sedan', 'mpu6050', 'floor_structural', shape=shape,
             label=f'{s} km/h {shape}')

print("\n--- TRUCK (low jerk threshold=100, high mass) ---")
for s in [20, 40, 60, 80, 100]:
    test(s, 0, 100, 'truck', 'h3lis331dl', 'floor_structural', label=f'{s} km/h truck')

print("\n--- SUV (jerk threshold=180) ---")
for s in [10, 20, 30, 50, 70, 90]:
    test(s, 0, 100, 'suv', 'mpu6050', 'floor_structural', label=f'{s} km/h SUV')

print("\n--- SIDE IMPACTS (all are crashes) ---")
for s in [20, 30, 40, 50, 60, 70, 80]:
    test(s, 90, 50, 'sedan', 'mpu6050', 'floor_structural', label=f'{s} km/h left side')

print("\n--- REAR IMPACTS (all are crashes) ---")
for s in [20, 30, 40, 50, 60, 70, 80]:
    test(s, 180, 100, 'sedan', 'mpu6050', 'floor_structural', label=f'{s} km/h rear')

print("\n" + "=" * 90)
print("BOUNDARY ANALYSIS COMPLETE")
print("=" * 90)
