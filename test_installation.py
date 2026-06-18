"""
Simple test script to verify VISTA HIL installation and basic functionality
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from vista_hil import MEMSSensorSimulator, SensorConfig, load_sensor
        print("  [OK] MEMS Simulator imported successfully")
    except ImportError as e:
        print(f"  [FAIL] Failed to import MEMS Simulator: {e}")
        return False
    
    try:
        from vista_hil import CrashPulseGenerator, CrashPulseConfig
        print("  [OK] Crash Pulse Generator imported successfully")
    except ImportError as e:
        print(f"  [FAIL] Failed to import Crash Pulse Generator: {e}")
        return False
    
    try:
        from vista_hil import HILSimulation, HILConfig, SimulationResult
        print("  [OK] HIL Simulation imported successfully")
    except ImportError as e:
        print(f"  [FAIL] Failed to import HIL Simulation: {e}")
        return False
    
    return True


def test_sensor_loading():
    """Test sensor configuration loading"""
    print("\nTesting sensor loading...")
    
    from vista_hil import load_sensor
    
    sensors = ['mpu6050', 'h3lis331dl', 'iam20680hp']
    
    for sensor_name in sensors:
        try:
            sensor = load_sensor(sensor_name, sampling_rate=1000)
            print(f"  [OK] {sensor_name.upper()} loaded successfully")
            print(f"    - Range: +/-{sensor.config.accel_range_g}g")
            print(f"    - Noise: {sensor.config.accel_noise_density*1000:.1f} mg/sqrt(Hz)")
        except Exception as e:
            print(f"  [FAIL] Failed to load {sensor_name}: {e}")
            return False
    
    return True


def test_crash_pulse_generation():
    """Test crash pulse generation"""
    print("\nTesting crash pulse generation...")
    
    from vista_hil import CrashPulseGenerator
    
    gen = CrashPulseGenerator(seed=42)
    
    # Test single pulse
    try:
        t, accel, gyro = gen.generate(
            crash_type='haversine',
            peak_g=50,
            duration_ms=100,
            delta_v_kmh=40,
            direction='frontal'
        )
        print(f"  [OK] Haversine pulse generated")
        print(f"    - Samples: {len(t)}")
        print(f"    - Duration: {t[-1]*1000:.1f} ms")
        print(f"    - Max accel: {abs(accel).max()/9.80665:.1f} g")
    except Exception as e:
        print(f"  [FAIL] Failed to generate pulse: {e}")
        return False
    
    # Test batch generation
    try:
        scenarios = gen.generate_batch(10, seed=42)
        print(f"  [OK] Batch generation successful ({len(scenarios)} scenarios)")
    except Exception as e:
        print(f"  [FAIL] Failed to generate batch: {e}")
        return False
    
    return True


def test_simulation():
    """Test full simulation pipeline"""
    print("\nTesting simulation pipeline...")
    
    from vista_hil import HILSimulation, HILConfig
    
    config = HILConfig(
        sensor_name='mpu6050',
        sampling_rate=1000,
        output_dir='test_output',
    )
    
    hil = HILSimulation(config)
    
    crash_config = {
        'type': 'haversine',
        'peak_g': 50,
        'duration_ms': 100,
        'delta_v_kmh': 40,
        'direction': 'frontal',
    }
    
    try:
        result = hil.run_single_crash(crash_config)
        print(f"  [OK] Simulation completed successfully")
        print(f"    - Execution time: {result.execution_time_ms:.2f} ms")
        print(f"    - Max acceleration: {result.max_accel_g:.1f} g")
        print(f"    - Saturation: {result.saturation_pct:.1f}%")
        print(f"    - Delta-V: {result.delta_v_kmh:.1f} km/h")
    except Exception as e:
        print(f"  [FAIL] Simulation failed: {e}")
        return False
    
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("VISTA 2.0 HIL Simulation - Installation Test")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_imports),
        ("Sensor Loading Test", test_sensor_loading),
        ("Crash Pulse Test", test_crash_pulse_generation),
        ("Simulation Test", test_simulation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  [FAIL] Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "[PASSED]" if success else "[FAILED]"
        print(f"  {test_name}: {status}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed! VISTA HIL is ready to use.")
        return 0
    else:
        print("\n[ERROR] Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
