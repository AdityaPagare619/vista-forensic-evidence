"""
VISTA 2.0 — Stress Test: Finding What Breaks

Scientists don't confirm — they BREAK. This test runs ~500 scenarios
specifically designed to find weaknesses, false positives, and edge cases.

GROUND TRUTH RULES (physics-based):
  - ANY impact with a barrier that produces peak >12g AND sustain >60ms IS a crash
  - Side impacts at 60 km/h ARE crashes (they kill people)
  - Rear impacts at 60 km/h ARE crashes (they kill people)
  - Non-crash events: ABS braking, potholes, speed bumps (no barrier impact)
"""

import numpy as np
from vista_hil.realistic_simulation import RealisticCrashSimulator, CrashScenario
from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass
from vista_hil import load_sensor
import time


def _scenario(name, speed, angle, overlap, barrier, vehicle, mass, mounting,
              sensor='mpu6050', temp=25, roughness=0.3, rpm=2500, is_crash=True):
    """Helper to create a scenario tuple: (name, CrashScenario, expected_detect)."""
    return (name, CrashScenario(
        speed_kmh=speed, impact_angle_deg=angle, overlap_percent=overlap,
        barrier_type=barrier, vehicle_class=vehicle, vehicle_mass_kg=mass,
        sensor_mounting=mounting, sensor_name=sensor,
        temperature_c=temp, road_roughness=roughness, engine_rpm=rpm
    ), is_crash)


def create_stress_scenarios():
    """Create ~500 scenarios designed to BREAK the algorithm.

    Ground truth is based on PHYSICS, not sensor output:
      - Impact with barrier → is_crash = True
      - No barrier impact (ABS, pothole, bump) → is_crash = False
    """
    scenarios = []

    # =========================================================================
    # CATEGORY 1: FALSE POSITIVES — These are NOT crashes (no barrier impact)
    # =========================================================================

    # Aggressive ABS braking at various speeds
    for speed in [60, 80, 100, 120]:
        scenarios.append(_scenario(
            f'ABS braking {speed}km/h', speed, 0, 0, 'none',
            'sedan', 1400, 'floor_structural', roughness=0.1, rpm=4000,
            is_crash=False))

    # Pothole impacts at various speeds
    for speed in [30, 50, 70, 90]:
        scenarios.append(_scenario(
            f'Pothole {speed}km/h', speed, 0, 0, 'none',
            'sedan', 1400, 'floor_structural', roughness=0.9, rpm=2500,
            is_crash=False))

    # Speed bumps at various speeds
    for speed in [20, 30, 40, 50]:
        scenarios.append(_scenario(
            f'Speed bump {speed}km/h', speed, 0, 0, 'none',
            'sedan', 1400, 'floor_structural', roughness=0.3, rpm=1500,
            is_crash=False))

    # Hard braking on rough road (no impact)
    for speed in [40, 60, 80]:
        scenarios.append(_scenario(
            f'Hard braking rough road {speed}km/h', speed, 0, 0, 'none',
            'sedan', 1400, 'floor_structural', roughness=0.8, rpm=3500,
            is_crash=False))

    # Curvy road with high lateral acceleration (no impact)
    for speed in [50, 70, 90]:
        scenarios.append(_scenario(
            f'Curvy road {speed}km/h', speed, 30, 0, 'none',
            'sedan', 1400, 'floor_structural', roughness=0.2, rpm=3000,
            is_crash=False))

    # Railroad crossing impact (non-crash vibration)
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'Railroad crossing {speed}km/h', speed, 0, 0, 'none',
            'sedan', 1400, 'floor_structural', roughness=0.6, rpm=2000,
            is_crash=False))

    # =====================================================================
    # CATEGORY 2: FRONTAL CRASHES — These ARE crashes (barrier impact)
    # =====================================================================

    # Low-speed frontal (borderline detection)
    for speed in [5, 8, 10, 12, 15]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h sedan', speed, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural'))

    # Medium-speed frontal
    for speed in [20, 25, 30, 35, 40, 45, 50]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h sedan', speed, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural'))

    # High-speed frontal
    for speed in [60, 70, 80, 90, 100, 110, 120]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h sedan', speed, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural'))

    # SUV frontal at various speeds
    for speed in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h SUV', speed, 0, 100, 'rigid',
            'suv', 2200, 'floor_structural'))

    # Truck frontal at various speeds
    for speed in [20, 40, 60, 80]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h truck', speed, 0, 100, 'rigid',
            'truck', 8000, 'floor_structural'))

    # Motorcycle frontal
    for speed in [20, 30, 40, 50]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h motorcycle', speed, 15, 50, 'pole',
            'motorcycle', 200, 'dashboard'))

    # Deformable barrier frontal
    for speed in [30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Frontal deformable {speed}km/h', speed, 0, 100, 'deformable',
            'sedan', 1400, 'floor_structural'))

    # =====================================================================
    # CATEGORY 3: REAR CRASHES — These ARE crashes (barrier impact)
    # =====================================================================

    # Rear impacts at various speeds — ALL are crashes
    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Rear {speed}km/h sedan', speed, 180, 100, 'rigid',
            'sedan', 1400, 'floor_structural'))

    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Rear {speed}km/h SUV', speed, 180, 100, 'rigid',
            'suv', 2200, 'floor_structural'))

    # Rear with deformable barrier
    for speed in [30, 40, 50, 60]:
        scenarios.append(_scenario(
            f'Rear deformable {speed}km/h', speed, 180, 100, 'deformable',
            'sedan', 1400, 'floor_structural'))

    # =====================================================================
    # CATEGORY 4: SIDE CRASHES — These ARE crashes (barrier impact)
    # =====================================================================

    # Left side impacts at various speeds — ALL are crashes
    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Left side {speed}km/h sedan', speed, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural'))

    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Left side {speed}km/h SUV', speed, 90, 50, 'pole',
            'suv', 2200, 'floor_structural'))

    # Right side impacts at various speeds — ALL are crashes
    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Right side {speed}km/h sedan', speed, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural'))

    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Right side {speed}km/h SUV', speed, 90, 50, 'pole',
            'suv', 2200, 'floor_structural'))

    # Side with deformable barrier (MDB)
    for speed in [30, 40, 50, 60]:
        scenarios.append(_scenario(
            f'Left side MDB {speed}km/h', speed, 90, 50, 'deformable',
            'sedan', 1400, 'floor_structural'))

    for speed in [30, 40, 50, 60]:
        scenarios.append(_scenario(
            f'Right side MDB {speed}km/h', speed, 90, 50, 'deformable',
            'sedan', 1400, 'floor_structural'))

    # =====================================================================
    # CATEGORY 5: OFFSET / OBLIQUE CRASHES — These ARE crashes
    # =====================================================================

    # 30° offset frontal
    for speed in [30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'30° offset {speed}km/h', speed, 30, 40, 'deformable',
            'sedan', 1400, 'floor_structural'))

    # 45° offset
    for speed in [30, 40, 50, 60, 70]:
        scenarios.append(_scenario(
            f'45° offset {speed}km/h', speed, 45, 40, 'deformable',
            'sedan', 1400, 'floor_structural'))

    # 60° oblique
    for speed in [30, 40, 50, 60]:
        scenarios.append(_scenario(
            f'60° oblique {speed}km/h', speed, 60, 30, 'deformable',
            'sedan', 1400, 'floor_structural'))

    # Small overlap (25%)
    for speed in [30, 40, 50, 60, 70]:
        scenarios.append(_scenario(
            f'25% overlap {speed}km/h', speed, 0, 25, 'rigid',
            'sedan', 1400, 'floor_structural'))

    # =====================================================================
    # CATEGORY 6: TEMPERATURE EXTREMES — Crashes in extreme conditions
    # =====================================================================

    for temp in [-20, -10, 0, 60]:
        scenarios.append(_scenario(
            f'Frontal 50km/h temp={temp}°C', 50, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural', temp=temp))

    for temp in [-20, 60]:
        scenarios.append(_scenario(
            f'Left side 50km/h temp={temp}°C', 50, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural', temp=temp))

    for temp in [-20, 60]:
        scenarios.append(_scenario(
            f'Rear 50km/h temp={temp}°C', 50, 180, 100, 'rigid',
            'sedan', 1400, 'floor_structural', temp=temp))

    # =====================================================================
    # CATEGORY 7: SENSOR MOUNTING VARIATION — Crashes with attenuated sensors
    # =====================================================================

    # Dashboard mounting (6dB attenuation + filtering)
    for speed in [30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'Frontal dashboard mount {speed}km/h', speed, 0, 100, 'rigid',
            'sedan', 1400, 'dashboard'))

    for speed in [30, 50, 60]:
        scenarios.append(_scenario(
            f'Left side dashboard mount {speed}km/h', speed, 90, 50, 'pole',
            'sedan', 1400, 'dashboard'))

    for speed in [30, 50, 60]:
        scenarios.append(_scenario(
            f'Rear dashboard mount {speed}km/h', speed, 180, 100, 'rigid',
            'sedan', 1400, 'dashboard'))

    # Seat rail mounting (10dB attenuation + heavy filtering)
    for speed in [40, 50, 60, 70, 80, 90]:
        scenarios.append(_scenario(
            f'Frontal seat rail mount {speed}km/h', speed, 0, 100, 'rigid',
            'sedan', 1400, 'seat_rail'))

    for speed in [50, 60, 70]:
        scenarios.append(_scenario(
            f'Left side seat rail mount {speed}km/h', speed, 90, 50, 'pole',
            'sedan', 1400, 'seat_rail'))

    for speed in [50, 60, 70]:
        scenarios.append(_scenario(
            f'Rear seat rail mount {speed}km/h', speed, 180, 100, 'rigid',
            'sedan', 1400, 'seat_rail'))

    # =====================================================================
    # CATEGORY 8: SENSOR TYPE VARIATION
    # =====================================================================

    # h3lis331dl (±400g range — should never saturate)
    for speed in [30, 50, 70, 90, 110]:
        scenarios.append(_scenario(
            f'Frontal h3lis331dl {speed}km/h', speed, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural', sensor='h3lis331dl'))

    for speed in [40, 60, 80]:
        scenarios.append(_scenario(
            f'Left side h3lis331dl {speed}km/h', speed, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural', sensor='h3lis331dl'))

    # =====================================================================
    # CATEGORY 9: ROAD ROUGHNESS DURING CRASH
    # =====================================================================

    for roughness in [0.1, 0.5, 0.9]:
        scenarios.append(_scenario(
            f'Frontal 50km/h roughness={roughness}', 50, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural', roughness=roughness))

    for roughness in [0.1, 0.5, 0.9]:
        scenarios.append(_scenario(
            f'Left side 50km/h roughness={roughness}', 50, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural', roughness=roughness))

    # =====================================================================
    # CATEGORY 10: ENGINE RPM DURING CRASH
    # =====================================================================

    for rpm in [1000, 3000, 5000]:
        scenarios.append(_scenario(
            f'Frontal 50km/h rpm={rpm}', 50, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural', rpm=rpm))

    for rpm in [1000, 3000, 5000]:
        scenarios.append(_scenario(
            f'Left side 50km/h rpm={rpm}', 50, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural', rpm=rpm))

    # =====================================================================
    # CATEGORY 11: EXTREME HIGH-SPEED CRASHES (saturation expected)
    # =====================================================================

    for speed in [130, 140, 150]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h sedan', speed, 0, 100, 'rigid',
            'sedan', 1400, 'floor_structural'))

    for speed in [120, 140]:
        scenarios.append(_scenario(
            f'Frontal {speed}km/h SUV', speed, 0, 100, 'rigid',
            'suv', 2200, 'floor_structural'))

    for speed in [100, 120]:
        scenarios.append(_scenario(
            f'Left side {speed}km/h sedan', speed, 90, 50, 'pole',
            'sedan', 1400, 'floor_structural'))

    for speed in [100, 120]:
        scenarios.append(_scenario(
            f'Rear {speed}km/h sedan', speed, 180, 100, 'rigid',
            'sedan', 1400, 'floor_structural'))

    return scenarios


def compute_saturation_pct(saturation_array):
    """Compute saturation percentage from boolean saturation array."""
    if saturation_array is None or len(saturation_array) == 0:
        return 0.0
    if saturation_array.ndim > 1:
        return float(np.mean(saturation_array.any(axis=1)) * 100)
    return float(np.mean(saturation_array) * 100)


def run_stress_test():
    """Run all stress test scenarios and analyze results."""
    sim = RealisticCrashSimulator()
    scenarios = create_stress_scenarios()

    results = []
    failures = []
    false_positives = []
    false_negatives = []

    for name, scenario, expected_detect in scenarios:
        try:
            result = sim.simulate_crash(scenario)
            vr = result['vista_result']

            detected = vr['detected']
            sat_pct = compute_saturation_pct(result['sensor_output'].get('saturation', None))

            # Check if result matches expectation
            if expected_detect is not None:
                if detected != expected_detect:
                    failure = {
                        'name': name,
                        'expected': expected_detect,
                        'actual': detected,
                        'delta_v': vr['delta_v_kmh'],
                        'confidence': vr['confidence'],
                        'peak_g': vr['peak_accel_g'],
                        'saturation': sat_pct,
                    }
                    failures.append(failure)
                    if expected_detect and not detected:
                        false_negatives.append(failure)
                    elif not expected_detect and detected:
                        false_positives.append(failure)

            results.append({
                'name': name,
                'detected': detected,
                'expected': expected_detect,
                'confidence': vr['confidence'],
                'delta_v': vr['delta_v_kmh'],
                'peak_g': vr['peak_accel_g'],
                'saturation': sat_pct,
            })

        except Exception as e:
            failures.append({
                'name': name,
                'error': str(e),
                'type': 'CRASH',
            })

    return results, failures, false_positives, false_negatives


def print_results(results, failures, false_positives, false_negatives):
    """Print detailed stress test results."""
    total = len(results)
    crash_scenarios = [r for r in results if r['expected'] is True]
    non_crash_scenarios = [r for r in results if r['expected'] is False]

    detected_crashes = sum(1 for r in crash_scenarios if r['detected'])
    missed_crashes = sum(1 for r in crash_scenarios if not r['detected'])
    detected_non_crashes = sum(1 for r in non_crash_scenarios if r['detected'])
    correct_non_detections = sum(1 for r in non_crash_scenarios if not r['detected'])

    print(f"\nTotal scenarios: {total}")
    print(f"  Crash scenarios: {len(crash_scenarios)}")
    print(f"  Non-crash scenarios: {len(non_crash_scenarios)}")

    print(f"\n--- CRASH DETECTION PERFORMANCE ---")
    print(f"  True Positives (correctly detected):  {detected_crashes}/{len(crash_scenarios)} "
          f"({detected_crashes/max(len(crash_scenarios),1)*100:.1f}%)")
    print(f"  False Negatives (MISSED crashes):     {missed_crashes}/{len(crash_scenarios)} "
          f"({missed_crashes/max(len(crash_scenarios),1)*100:.1f}%)")

    print(f"\n--- FALSE POSITIVE PERFORMANCE ---")
    print(f"  True Negatives (correctly not detected): {correct_non_detections}/{len(non_crash_scenarios)} "
          f"({correct_non_detections/max(len(non_crash_scenarios),1)*100:.1f}%)")
    print(f"  False Positives (wrongly detected):      {detected_non_crashes}/{len(non_crash_scenarios)} "
          f"({detected_non_crashes/max(len(non_crash_scenarios),1)*100:.1f}%)")

    # Per-direction analysis for crashes
    print(f"\n--- DETECTION BY DIRECTION ---")
    for direction in ['frontal', 'rear', 'left', 'right', 'offset', 'oblique']:
        dir_results = [r for r in crash_scenarios
                       if direction in r['name'].lower() or
                       (direction == 'left' and 'left side' in r['name'].lower()) or
                       (direction == 'right' and 'right side' in r['name'].lower())]
        if dir_results:
            detected = sum(1 for r in dir_results if r['detected'])
            print(f"  {direction:10s}: {detected}/{len(dir_results)} "
                  f"({detected/max(len(dir_results),1)*100:.1f}%)")

    # Saturation analysis
    saturated_crashes = [r for r in crash_scenarios if r['saturation'] > 0]
    missed_crashes_list = [r for r in crash_scenarios if not r['detected']]
    missed_saturated = [r for r in missed_crashes_list if r['saturation'] > 0]
    print(f"\n--- SATURATION ANALYSIS ---")
    print(f"  Crashes with sensor saturation: {len(saturated_crashes)}")
    print(f"  Missed crashes due to saturation: {len(missed_saturated)}")

    if false_negatives:
        print(f"\n--- MISSED CRASHES (False Negatives) ---")
        for f in false_negatives[:30]:  # Show first 30
            print(f"  MISS: {f['name']:45s} peak={f['peak_g']:6.1f}g  "
                  f"dV={f['delta_v']:6.1f}km/h  sat={f['saturation']:.0f}%  "
                  f"conf={f['confidence']:.3f}")
        if len(false_negatives) > 30:
            print(f"  ... and {len(false_negatives) - 30} more")

    if false_positives:
        print(f"\n--- FALSE ALARMS (False Positives) ---")
        for f in false_positives:
            print(f"  FP:   {f['name']:45s} peak={f['peak_g']:6.1f}g  "
                  f"dV={f['delta_v']:6.1f}km/h  conf={f['confidence']:.3f}")

    print(f"\n--- OVERALL PASS RATE ---")
    correct = sum(1 for r in results if r['detected'] == r['expected'])
    print(f"  Correct: {correct}/{total} ({correct/max(total,1)*100:.1f}%)")


if __name__ == "__main__":
    print("=" * 70)
    print("VISTA 2.0 — STRESS TEST: FINDING WHAT BREAKS")
    print("=" * 70)

    start = time.time()
    results, failures, false_positives, false_negatives = run_stress_test()
    elapsed = time.time() - start

    print_results(results, failures, false_positives, false_negatives)

    print(f"\nElapsed time: {elapsed:.1f}s ({len(results)/max(elapsed,0.001):.0f} scenarios/sec)")
    print("\n" + "=" * 70)
    print("STRESS TEST COMPLETE")
    print("=" * 70)
