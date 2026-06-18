"""
Hardware-in-the-Loop Simulation for VISTA 2.0
Main co-simulation loop connecting crash physics → MEMS sensors → VISTA algorithm
"""

import time
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import numpy as np

from vista_hil.crash_pulse import CrashPulseGenerator, CrashPulseConfig
from vista_hil.mems_simulator import MEMSSensorSimulator, SensorConfig, load_sensor


@dataclass
class HILConfig:
    """Configuration for HIL simulation"""
    # Sensor configuration
    sensor_name: str = "mpu6050"
    sampling_rate: int = 1000  # Hz
    
    # Hardware interface
    hardware_interface: str = "none"  # "serial", "spi", "none"
    serial_port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    
    # Simulation settings
    temperature: float = 25.0  # °C
    add_realistic_features: bool = True
    
    # Output settings
    output_dir: str = "output"
    save_raw_data: bool = True
    save_vista_format: bool = True
    
    # Performance settings
    max_workers: int = 1  # For parallel execution
    batch_size: int = 100  # Scenarios per batch


@dataclass
class SimulationResult:
    """Result from a single crash simulation"""
    scenario_id: int
    crash_config: dict
    sensor_name: str
    
    # Simulation outputs
    timestamp: np.ndarray  # seconds
    accel: np.ndarray  # m/s², shape (N, 3)
    gyro: np.ndarray  # rad/s, shape (N, 3)
    saturation: np.ndarray  # bool, shape (N, 3)
    
    # Metadata
    temperature: float
    sampling_rate: int
    execution_time_ms: float
    
    # Statistics
    max_accel_g: float
    max_gyro_dps: float
    saturation_pct: float
    delta_v_kmh: float
    
    def to_vista_format(self) -> Dict[str, Any]:
        """Convert to VISTA-compatible format"""
        # VISTA expects:
        # - timestamp in milliseconds (int64)
        # - accel in m/s² (int16, scaled by 1000)
        # - gyro in rad/s (int16, scaled by 10000)
        
        return {
            'timestamp_ms': (self.timestamp * 1000).astype(np.int64),
            'accel_x': (self.accel[:, 0] * 1000).astype(np.int16),
            'accel_y': (self.accel[:, 1] * 1000).astype(np.int16),
            'accel_z': (self.accel[:, 2] * 1000).astype(np.int16),
            'gyro_x': (self.gyro[:, 0] * 10000).astype(np.int16),
            'gyro_y': (self.gyro[:, 1] * 10000).astype(np.int16),
            'gyro_z': (self.gyro[:, 2] * 10000).astype(np.int16),
            'saturation': self.saturation.any(axis=1).astype(np.uint8),
        }
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'scenario_id': self.scenario_id,
            'crash_config': self.crash_config,
            'sensor_name': self.sensor_name,
            'temperature': self.temperature,
            'sampling_rate': self.sampling_rate,
            'execution_time_ms': self.execution_time_ms,
            'max_accel_g': self.max_accel_g,
            'max_gyro_dps': self.max_gyro_dps,
            'saturation_pct': self.saturation_pct,
            'delta_v_kmh': self.delta_v_kmh,
        }


class HILSimulation:
    """
    Hardware-in-the-Loop simulation for VISTA 2.0.
    
    This class orchestrates the complete simulation pipeline:
    1. Generate/retrieve crash pulse
    2. Run MEMS sensor simulation
    3. (Optional) Send to hardware
    4. Record results
    
    Usage:
        hil = HILSimulation(sensor_name="mpu6050")
        result = hil.run_single_crash(config)
        hil.run_batch(scenarios, output_dir="output/")
    """
    
    def __init__(self, config: Optional[HILConfig] = None):
        """
        Initialize HIL simulation.
        
        Args:
            config: HIL configuration (uses defaults if None)
        """
        self.config = config or HILConfig()
        
        # Initialize components
        self.sensor = load_sensor(
            self.config.sensor_name, 
            self.config.sampling_rate
        )
        self.crash_gen = CrashPulseGenerator()
        
        # Hardware interface (if configured)
        self.hw_interface = None
        if self.config.hardware_interface == "serial":
            try:
                from vista_hil.hardware_interface import RPi4SerialInterface
                self.hw_interface = RPi4SerialInterface(
                    self.config.serial_port,
                    self.config.baudrate
                )
            except ImportError:
                print("Warning: Serial interface not available")
        
        # Statistics
        self.stats = {
            'total_scenarios': 0,
            'total_samples': 0,
            'saturation_events': 0,
            'max_accel_g': 0,
            'execution_times': [],
        }
        
        # Create output directory
        os.makedirs(self.config.output_dir, exist_ok=True)
    
    def run_single_crash(self, 
                         crash_config: dict,
                         scenario_id: int = 0) -> SimulationResult:
        """
        Run a single crash scenario.
        
        Args:
            crash_config: Crash configuration dictionary with keys:
                - type: 'haversine', 'half_sine', 'square', 'triangular'
                - peak_g: Peak acceleration in g
                - duration_ms: Crash duration in ms
                - delta_v_kmh: Delta-V in km/h
                - direction: 'frontal', 'rear', 'left_side', 'right_side'
            scenario_id: Unique identifier for this scenario
            
        Returns:
            SimulationResult with all outputs
        """
        start_time = time.time()
        
        # Generate crash pulse
        t, pulse_ms2, gyro_rads = self.crash_gen.generate(
            crash_type=crash_config['type'],
            peak_g=crash_config['peak_g'],
            duration_ms=crash_config['duration_ms'],
            delta_v_kmh=crash_config['delta_v_kmh'],
            direction=crash_config['direction'],
            sampling_rate=self.config.sampling_rate,
            add_realistic_features=self.config.add_realistic_features
        )
        
        # Run MEMS simulation
        sim_result = self.sensor.simulate(
            crash_pulse=pulse_ms2,
            crash_gyro=gyro_rads,
            temperature=self.config.temperature
        )
        
        # Calculate statistics
        exec_time_ms = (time.time() - start_time) * 1000
        
        # Convert to g for statistics
        accel_g = sim_result['accel'] / 9.80665
        gyro_dps = sim_result['gyro'] * 180 / np.pi
        
        max_accel_g = float(np.max(np.abs(accel_g)))
        max_gyro_dps = float(np.max(np.abs(gyro_dps)))
        saturation_pct = float(np.mean(sim_result['saturation'].any(axis=1)) * 100)
        
        # Estimate delta-V from acceleration
        # Integrate acceleration to get velocity change
        dt = 1.0 / self.config.sampling_rate
        velocity_ms2 = np.cumsum(sim_result['accel'][:, 0]) * dt
        delta_v_ms = float(np.max(np.abs(velocity_ms2)))
        delta_v_kmh = delta_v_ms * 3.6  # Convert m/s to km/h
        
        # Create result object
        result = SimulationResult(
            scenario_id=scenario_id,
            crash_config=crash_config,
            sensor_name=self.config.sensor_name,
            timestamp=sim_result['timestamp'],
            accel=sim_result['accel'],
            gyro=sim_result['gyro'],
            saturation=sim_result['saturation'],
            temperature=self.config.temperature,
            sampling_rate=self.config.sampling_rate,
            execution_time_ms=exec_time_ms,
            max_accel_g=max_accel_g,
            max_gyro_dps=max_gyro_dps,
            saturation_pct=saturation_pct,
            delta_v_kmh=delta_v_kmh,
        )
        
        # Update global statistics
        self.stats['total_scenarios'] += 1
        self.stats['total_samples'] += len(t)
        self.stats['saturation_events'] += int(np.sum(sim_result['saturation']))
        self.stats['max_accel_g'] = max(self.stats['max_accel_g'], max_accel_g)
        self.stats['execution_times'].append(exec_time_ms)
        
        # Send to hardware if interface available
        if self.hw_interface is not None:
            self._send_to_hardware(result)
        
        return result
    
    def _send_to_hardware(self, result: SimulationResult):
        """Send simulation result to hardware interface"""
        if self.hw_interface is None:
            return
        
        # Send in real-time (or faster)
        dt = 1.0 / result.sampling_rate
        
        for i in range(len(result.timestamp)):
            ts_ms = int(result.timestamp[i] * 1000)
            
            self.hw_interface.send_imu_packet(
                ts_ms,
                (result.accel[i, 0], result.accel[i, 1], result.accel[i, 2]),
                (result.gyro[i, 0], result.gyro[i, 1], result.gyro[i, 2])
            )
            
            # Sleep to maintain timing (if real-time needed)
            # time.sleep(dt)  # Uncomment for real-time mode
    
    def run_batch(self, 
                  scenarios: List[dict],
                  output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Run batch simulation of multiple crash scenarios.
        
        Args:
            scenarios: List of crash configuration dictionaries
            output_dir: Output directory (uses config default if None)
            
        Returns:
            Dictionary with batch statistics
        """
        output_dir = output_dir or self.config.output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        batch_stats = {
            'total_scenarios': len(scenarios),
            'completed': 0,
            'failed': 0,
            'saturation_events': 0,
            'max_accel_g': 0,
            'results': [],
        }
        
        start_time = time.time()
        
        for i, config in enumerate(scenarios):
            try:
                result = self.run_single_crash(config, scenario_id=i)
                
                # Save result
                if self.config.save_raw_data:
                    output_file = os.path.join(output_dir, f"crash_{i:04d}.npz")
                    np.savez_compressed(
                        output_file,
                        timestamp=result.timestamp,
                        accel=result.accel,
                        gyro=result.gyro,
                        saturation=result.saturation,
                        crash_config=config
                    )
                
                if self.config.save_vista_format:
                    vista_data = result.to_vista_format()
                    vista_file = os.path.join(output_dir, f"vista_{i:04d}.npz")
                    np.savez_compressed(vista_file, **vista_data)
                
                batch_stats['completed'] += 1
                batch_stats['saturation_events'] += int(result.saturation_pct > 0)
                batch_stats['max_accel_g'] = max(
                    batch_stats['max_accel_g'],
                    result.max_accel_g
                )
                batch_stats['results'].append(result.to_dict())
                
                # Progress indicator
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    print(f"Completed {i+1}/{len(scenarios)} scenarios "
                          f"({rate:.1f} scenarios/sec)")
                
            except Exception as e:
                print(f"Failed scenario {i}: {e}")
                batch_stats['failed'] += 1
        
        # Final statistics
        total_time = time.time() - start_time
        batch_stats['total_time_s'] = total_time
        batch_stats['avg_time_ms'] = np.mean(self.stats['execution_times'])
        batch_stats['scenarios_per_second'] = len(scenarios) / total_time
        
        # Save batch stats
        stats_file = os.path.join(output_dir, 'batch_stats.json')
        with open(stats_file, 'w') as f:
            # Remove numpy arrays from stats for JSON serialization
            json_stats = {k: v for k, v in batch_stats.items() 
                         if k != 'results'}
            json.dump(json_stats, f, indent=2)
        
        print(f"\nBatch completed:")
        print(f"  Total scenarios: {batch_stats['completed']}")
        print(f"  Failed: {batch_stats['failed']}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Average time per scenario: {batch_stats['avg_time_ms']:.2f}ms")
        print(f"  Scenarios per second: {batch_stats['scenarios_per_second']:.1f}")
        print(f"  Max acceleration: {batch_stats['max_accel_g']:.1f}g")
        
        return batch_stats
    
    def validate_against_real_data(self, 
                                    real_data: Dict[str, np.ndarray],
                                    scenario_config: dict) -> Dict[str, float]:
        """
        Validate simulation against real sensor data.
        
        Args:
            real_data: Dictionary with keys 'timestamp', 'accel', 'gyro'
            scenario_config: Crash configuration for this real data
            
        Returns:
            Dictionary with validation metrics
        """
        # Run simulation with same config
        result = self.run_single_crash(scenario_config)
        
        # Interpolate simulation to match real timestamps
        from scipy.interpolate import interp1d
        
        # Create interpolation functions
        accel_interp = interp1d(
            result.timestamp, result.accel, 
            axis=0, fill_value='extrapolate'
        )
        
        # Interpolate to real timestamps
        sim_accel = accel_interp(real_data['timestamp'])
        
        # Calculate metrics
        metrics = {}
        
        # RMSE for each axis
        for i, axis in enumerate(['x', 'y', 'z']):
            error = sim_accel[:, i] - real_data['accel'][:, i]
            rmse = np.sqrt(np.mean(error**2))
            metrics[f'accel_{axis}_rmse_ms2'] = float(rmse)
            metrics[f'accel_{axis}_rmse_g'] = float(rmse / 9.80665)
        
        # Correlation coefficient
        for i, axis in enumerate(['x', 'y', 'z']):
            corr = np.corrcoef(sim_accel[:, i], real_data['accel'][:, i])[0, 1]
            metrics[f'accel_{axis}_correlation'] = float(corr)
        
        # Overall metrics
        metrics['overall_rmse_g'] = np.mean([
            metrics['accel_x_rmse_g'],
            metrics['accel_y_rmse_g'],
            metrics['accel_z_rmse_g']
        ])
        
        metrics['overall_correlation'] = np.mean([
            metrics['accel_x_correlation'],
            metrics['accel_y_correlation'],
            metrics['accel_z_correlation']
        ])
        
        return metrics


def generate_test_scenarios(n_scenarios: int = 1000, 
                            seed: int = 42) -> List[dict]:
    """
    Generate test scenarios for batch testing.
    
    Args:
        n_scenarios: Number of scenarios to generate
        seed: Random seed for reproducibility
        
    Returns:
        List of crash configuration dictionaries
    """
    generator = CrashPulseGenerator(seed=seed)
    return generator.generate_batch(n_scenarios, seed=seed)


def main():
    """Main entry point for HIL simulation"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='VISTA 2.0 HIL Simulation'
    )
    parser.add_argument('--sensor', default='mpu6050',
                       choices=['mpu6050', 'h3lis331dl', 'iam20680hp'],
                       help='Sensor to simulate')
    parser.add_argument('--scenarios', type=int, default=1000,
                       help='Number of scenarios to run')
    parser.add_argument('--output', default='output',
                       help='Output directory')
    parser.add_argument('--seed', type=int, default=42,
                       help='Random seed for reproducibility')
    parser.add_argument('--hardware', default='none',
                       choices=['none', 'serial', 'spi'],
                       help='Hardware interface')
    parser.add_argument('--port', default='/dev/ttyUSB0',
                       help='Serial port for hardware interface')
    
    args = parser.parse_args()
    
    # Create config
    config = HILConfig(
        sensor_name=args.sensor,
        output_dir=args.output,
        hardware_interface=args.hardware,
        serial_port=args.port,
    )
    
    # Create simulation
    hil = HILSimulation(config)
    
    # Generate scenarios
    print(f"Generating {args.scenarios} test scenarios...")
    scenarios = generate_test_scenarios(args.scenarios, seed=args.seed)
    
    # Run batch
    print(f"Running batch simulation with {args.sensor}...")
    stats = hil.run_batch(scenarios)
    
    print(f"\nResults saved to {args.output}/")
    print(f"Total scenarios: {stats['completed']}")
    print(f"Max acceleration: {stats['max_accel_g']:.1f}g")


if __name__ == "__main__":
    main()
