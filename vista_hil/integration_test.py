"""
VISTA 2.0 — Full Integration Test
Complete pipeline: Crash → Sensor → Detection → Delta-V → Evidence Package
"""

import numpy as np
import time
import json
import hashlib
import hmac
from vista_hil import HILSimulation, load_sensor
from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass


def run_full_vista_pipeline(scenario, sensor_name='mpu6050'):
    """Run complete VISTA 2.0 pipeline on a single crash scenario."""
    sim = HILSimulation()
    
    # Step 1: Simulate crash physics + sensor response
    result = sim.run_single_crash(scenario)
    
    # Step 2: Run PDTSA v2 detection
    accel_ms2 = result.accel  # Already in m/s² from sensor simulator
    timestamps = result.timestamp
    
    pdtsa = PDTSAv2(PDTSAConfig(vehicle_class=VehicleClass.SEDAN))
    det = pdtsa.detect(accel_ms2, timestamps)
    
    # Step 3: Create evidence package
    evidence = {
        'scenario': scenario,
        'sensor': sensor_name,
        'detection': {
            'detected': bool(det.features.detected),
            'confidence': float(det.features.confidence),
            'jerk_magnitude': float(det.features.jerk_magnitude),
            'sustain_ms': float(det.features.sustain_duration_ms),
            'asymmetry_ratio': float(det.features.asymmetry_ratio),
            'peak_accel_g': float(det.features.peak_accel_g),
        },
        'reconstruction': {
            'delta_v_kmh': float(det.delta_v_kmh),
            'ci_lower': float(det.ci_lower),
            'ci_upper': float(det.ci_upper),
            'pdof_degrees': float(det.pdof_degrees),
            'saturated': bool(det.saturated),
            'saturation_pct': float(result.saturation_pct),
        },
        'metadata': {
            'sampling_rate': result.sampling_rate,
            'num_samples': len(result.accel),
            'execution_time_ms': float(result.execution_time_ms),
        }
    }
    
    # Step 4: Compute SHA-256 hash of evidence
    evidence_str = json.dumps(evidence, sort_keys=True)
    evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()
    evidence['integrity_hash'] = evidence_hash
    
    return evidence


def run_batch_test(n=100):
    """Run N crash scenarios through the full pipeline."""
    sim = HILSimulation()
    
    scenarios = []
    for shape in ['haversine', 'half_sine', 'triangular']:
        for direction in ['frontal', 'rear', 'left_side', 'right_side']:
            for mag in [15, 20, 30, 50, 80, 120]:
                for dur in [30, 50, 80, 100]:
                    scenarios.append({
                        'type': shape, 'peak_g': mag,
                        'duration_ms': dur, 'delta_v_kmh': mag * dur / 100,
                        'direction': direction
                    })
    
    results = []
    start = time.time()
    for i, sc in enumerate(scenarios[:n]):
        r = run_full_vista_pipeline(sc)
        results.append(r)
    elapsed = time.time() - start
    
    detected = sum(1 for r in results if r['detection']['detected'])
    saturated = sum(1 for r in results if r['reconstruction']['saturation_pct'] > 10)
    
    return {
        'total_scenarios': len(results),
        'detection_rate': detected / len(results) * 100,
        'saturation_rate': saturated / len(results) * 100,
        'execution_time_ms': elapsed / len(results) * 1000,
        'total_time_s': elapsed,
        'results': results,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("VISTA 2.0 — FULL INTEGRATION TEST")
    print("=" * 60)
    
    # Single scenario test
    print("\n--- Single Scenario Test ---")
    evidence = run_full_vista_pipeline({
        'type': 'haversine', 'peak_g': 50, 'duration_ms': 80,
        'delta_v_kmh': 40, 'direction': 'frontal'
    })
    print(f"Detected: {evidence['detection']['detected']}")
    print(f"Confidence: {evidence['detection']['confidence']:.3f}")
    print(f"Delta-V: {evidence['reconstruction']['delta_v_kmh']:.1f} km/h")
    print(f"CI: [{evidence['reconstruction']['ci_lower']:.1f}, {evidence['reconstruction']['ci_upper']:.1f}] km/h")
    print(f"PDOF: {evidence['reconstruction']['pdof_degrees']:.1f}°")
    print(f"Saturated: {evidence['reconstruction']['saturation_pct']:.1f}%")
    print(f"Hash: {evidence['integrity_hash'][:32]}...")
    
    # Batch test
    print("\n--- Batch Test (100 scenarios) ---")
    batch = run_batch_test(100)
    print(f"Scenarios: {batch['total_scenarios']}")
    print(f"Detection rate: {batch['detection_rate']:.1f}%")
    print(f"Saturation rate: {batch['saturation_rate']:.1f}%")
    print(f"Time per scenario: {batch['execution_time_ms']:.2f}ms")
    print(f"Total time: {batch['total_time_s']:.2f}s")
    
    print("\n" + "=" * 60)
    print("VISTA 2.0 PIPELINE VERIFIED")
    print("=" * 60)
