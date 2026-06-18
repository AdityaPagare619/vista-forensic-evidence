"""
VISTA 2.0 HIL Simulation Demo
Demonstrates the complete simulation pipeline
"""

import numpy as np
import matplotlib.pyplot as plt
from vista_hil import HILSimulation, HILConfig, load_sensor, CrashPulseGenerator


def demo_sensor_comparison():
    """Compare different MEMS sensors"""
    print("=" * 60)
    print("MEMS Sensor Comparison for Crash Detection")
    print("=" * 60)
    
    # Define sensors
    sensors = {
        'MPU6050': 'mpu6050',
        'H3LIS331DL': 'h3lis331dl',
        'IAM-20680HP': 'iam20680hp',
    }
    
    # Generate test crash pulse
    gen = CrashPulseGenerator(seed=42)
    t, pulse, gyro = gen.generate(
        crash_type='haversine',
        peak_g=50,
        duration_ms=100,
        delta_v_kmh=40,
        direction='frontal'
    )
    
    # Simulate each sensor
    results = {}
    for name, sensor_file in sensors.items():
        sensor = load_sensor(sensor_file, sampling_rate=1000)
        result = sensor.simulate(pulse, gyro, temperature=25.0)
        results[name] = result
        
        # Calculate statistics
        accel_g = result['accel'] / 9.80665
        sat_pct = np.mean(result['saturation'].any(axis=1)) * 100
        
        print(f"\n{name}:")
        print(f"  Max acceleration: {np.max(np.abs(accel_g)):.1f}g")
        print(f"  Saturation: {sat_pct:.1f}% of samples")
        print(f"  Noise (std): {np.std(accel_g[:, 0]):.3f}g")
    
    # Plot comparison
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    for i, (name, result) in enumerate(results.items()):
        accel_g = result['accel'] / 9.80665
        
        axes[i].plot(t * 1000, accel_g[:, 0], 'r-', label='X-axis', alpha=0.8)
        axes[i].plot(t * 1000, accel_g[:, 1], 'g-', label='Y-axis', alpha=0.8)
        axes[i].plot(t * 1000, accel_g[:, 2], 'b-', label='Z-axis', alpha=0.8)
        
        # Mark saturation
        sat_mask = result['saturation'].any(axis=1)
        if np.any(sat_mask):
            axes[i].axhline(y=16 if name != 'H3LIS331DL' else 400, 
                           color='k', linestyle='--', alpha=0.5, label='Saturation limit')
        
        axes[i].set_ylabel(f'{name}\nAcceleration (g)')
        axes[i].grid(True, alpha=0.3)
        axes[i].legend(loc='upper right')
    
    axes[0].set_title('MEMS Sensor Comparison for 50g Frontal Crash')
    axes[-1].set_xlabel('Time (ms)')
    
    plt.tight_layout()
    plt.savefig('sensor_comparison.png', dpi=150)
    plt.show()


def demo_batch_simulation():
    """Demonstrate batch simulation of 1000 scenarios"""
    print("\n" + "=" * 60)
    print("Batch Simulation: 1000 Crash Scenarios")
    print("=" * 60)
    
    # Configure HIL
    config = HILConfig(
        sensor_name='mpu6050',
        sampling_rate=1000,
        output_dir='demo_output',
        save_raw_data=True,
        save_vista_format=True,
    )
    
    hil = HILSimulation(config)
    
    # Generate 1000 diverse scenarios
    gen = CrashPulseGenerator(seed=42)
    scenarios = gen.generate_batch(1000, seed=42)
    
    # Run batch
    stats = hil.run_batch(scenarios)
    
    print(f"\nBatch completed successfully!")
    print(f"Results saved to: {config.output_dir}/")


def demo_hil_pipeline():
    """Demonstrate complete HIL pipeline"""
    print("\n" + "=" * 60)
    print("Complete HIL Pipeline Demo")
    print("=" * 60)
    
    # Configure
    config = HILConfig(
        sensor_name='mpu6050',
        sampling_rate=1000,
        temperature=25.0,
    )
    
    hil = HILSimulation(config)
    
    # Run single crash
    crash_config = {
        'type': 'haversine',
        'peak_g': 80,
        'duration_ms': 80,
        'delta_v_kmh': 50,
        'direction': 'frontal',
    }
    
    result = hil.run_single_crash(crash_config)
    
    # Display results
    print(f"\nSimulation Results:")
    print(f"  Scenario ID: {result.scenario_id}")
    print(f"  Sensor: {result.sensor_name}")
    print(f"  Execution time: {result.execution_time_ms:.2f}ms")
    print(f"  Max acceleration: {result.max_accel_g:.1f}g")
    print(f"  Max gyro: {result.max_gyro_dps:.1f}°/s")
    print(f"  Saturation: {result.saturation_pct:.1f}%")
    print(f"  Delta-V: {result.delta_v_kmh:.1f} km/h")
    
    # Convert to VISTA format
    vista_data = result.to_vista_format()
    print(f"\nVISTA Format Data:")
    print(f"  Timestamps: {len(vista_data['timestamp_ms'])} samples")
    print(f"  Accel range: [{vista_data['accel_x'].min()}, {vista_data['accel_x'].max()}]")
    
    # Plot results
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    
    accel_g = result.accel / 9.80665
    
    axes[0].plot(result.timestamp * 1000, accel_g[:, 0], 'r-', label='X-axis')
    axes[0].plot(result.timestamp * 1000, accel_g[:, 1], 'g-', label='Y-axis')
    axes[0].plot(result.timestamp * 1000, accel_g[:, 2], 'b-', label='Z-axis')
    axes[0].set_ylabel('Acceleration (g)')
    axes[0].set_title(f'Simulated Crash Pulse - {result.sensor_name}')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    
    gyro_dps = result.gyro * 180 / np.pi
    axes[1].plot(result.timestamp * 1000, gyro_dps[:, 0], 'r-', label='X-axis')
    axes[1].plot(result.timestamp * 1000, gyro_dps[:, 1], 'g-', label='Y-axis')
    axes[1].plot(result.timestamp * 1000, gyro_dps[:, 2], 'b-', label='Z-axis')
    axes[1].set_ylabel('Angular Rate (°/s)')
    axes[1].set_xlabel('Time (ms)')
    axes[1].set_title('Simulated Gyroscope Output')
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig('hil_pipeline_demo.png', dpi=150)
    plt.show()


def main():
    """Run all demos"""
    print("VISTA 2.0 HIL Simulation Demo")
    print("=" * 60)
    
    # Demo 1: Sensor comparison
    demo_sensor_comparison()
    
    # Demo 2: Batch simulation
    demo_batch_simulation()
    
    # Demo 3: Complete pipeline
    demo_hil_pipeline()
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("Check output files for detailed results.")
    print("=" * 60)


if __name__ == "__main__":
    main()
