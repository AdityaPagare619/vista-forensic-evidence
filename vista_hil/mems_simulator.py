"""
MEMS Sensor Simulation Engine for VISTA 2.0
Simulates realistic MEMS IMU behavior during crash events
"""

import numpy as np
from scipy.signal import butter, sosfilt
from dataclasses import dataclass
from typing import Optional, Tuple
import yaml


@dataclass
class SensorConfig:
    """Configuration for a specific MEMS sensor"""
    name: str
    accel_range_g: float  # ±g
    gyro_range_dps: float  # ±°/s (0 if no gyro)
    accel_noise_density: float  # g/√Hz
    gyro_noise_density: float  # °/s/√Hz
    accel_bias_instability: float  # g
    gyro_bias_instability: float  # °/s
    bias_drift_rate: float  # g/s
    accel_bandwidth_hz: float
    gyro_bandwidth_hz: float
    temp_sensitivity_coeff: float  # /°C
    temp_offset_coeff: float  # g/°C
    reference_temp: float  # °C
    cross_axis_matrix: np.ndarray  # 3x3
    max_odr: int  # Hz
    jitter_pct: float  # ±fraction
    clock_drift_ppm: float
    factory_offset_accel: np.ndarray  # 3-element, g
    factory_offset_gyro: np.ndarray  # 3-element, °/s

    @classmethod
    def from_yaml(cls, path: str) -> 'SensorConfig':
        """Load sensor config from YAML file"""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        s = data['sensor']
        n = data['noise']
        t = data['temperature']
        c = data['cross_axis']
        timing = data['timing']
        cal = data['calibration']
        
        return cls(
            name=s['name'],
            accel_range_g=data['dynamic_range']['accel'],
            gyro_range_dps=data['dynamic_range']['gyro'] or 0,
            accel_noise_density=n['accel_density'],
            gyro_noise_density=n.get('gyro_density', 0),
            accel_bias_instability=n['bias_instability']['accel'],
            gyro_bias_instability=n['bias_instability'].get('gyro', 0),
            bias_drift_rate=n['bias_drift_rate'],
            accel_bandwidth_hz=data['bandwidth']['accel_lp'],
            gyro_bandwidth_hz=data['bandwidth'].get('gyro_lp', 0),
            temp_sensitivity_coeff=t['sensitivity_coeff'],
            temp_offset_coeff=t['offset_coeff'],
            reference_temp=t['reference_temp'],
            cross_axis_matrix=np.array(c['matrix']),
            max_odr=timing['max_odr'],
            jitter_pct=timing['jitter_pct'],
            clock_drift_ppm=timing['clock_drift_ppm'],
            factory_offset_accel=np.array(cal['factory_offset']['accel']),
            factory_offset_gyro=np.array(cal['factory_offset'].get('gyro', [0, 0, 0])),
        )


class MEMSSensorSimulator:
    """
    Simulates realistic MEMS sensor behavior during crash events.
    
    Handles:
    - Range clipping (saturation)
    - Bandwidth limiting (low-pass filter)
    - Noise injection (Allan variance model)
    - Temperature drift
    - Cross-axis sensitivity
    - Time synchronization (jitter, clock drift)
    """
    
    def __init__(self, config: SensorConfig, sampling_rate: int = 1000):
        self.config = config
        self.sampling_rate = sampling_rate
        self.dt = 1.0 / sampling_rate
        
        # Build low-pass filter
        nyquist = sampling_rate / 2
        if config.accel_bandwidth_hz < nyquist:
            self.accel_sos = butter(
                2, config.accel_bandwidth_hz / nyquist, 
                btype='low', output='sos'
            )
        else:
            self.accel_sos = None
            
        if config.gyro_bandwidth_hz > 0 and config.gyro_bandwidth_hz < nyquist:
            self.gyro_sos = butter(
                2, config.gyro_bandwidth_hz / nyquist,
                btype='low', output='sos'
            )
        else:
            self.gyro_sos = None
        
        # Initialize bias states (random walk)
        self.accel_bias = np.random.normal(0, config.accel_bias_instability, 3)
        self.gyro_bias = np.random.normal(0, config.gyro_bias_instability, 3)
        
    def _clip_to_range(self, values: np.ndarray, 
                       range_val: float) -> Tuple[np.ndarray, np.ndarray]:
        """Clip values to sensor range, return clipped + saturation flags"""
        max_val = range_val * 9.80665  # Convert g to m/s²
        clipped = np.clip(values, -max_val, max_val)
        saturated = np.abs(values) > max_val
        return clipped, saturated
    
    def _apply_noise(self, values: np.ndarray, 
                     noise_density: float,
                     axis: int = 0) -> np.ndarray:
        """Add white noise based on noise density"""
        noise_std = noise_density * 9.80665 * np.sqrt(self.sampling_rate)
        noise = np.random.normal(0, noise_std, values.shape)
        return values + noise
    
    def _update_bias(self, dt: float):
        """Update bias with random walk"""
        # Bias drift as random walk
        accel_noise = np.random.normal(
            0, self.config.bias_drift_rate * 9.80665 * np.sqrt(dt), 3
        )
        self.accel_bias += accel_noise
        
        if self.config.gyro_bias_instability > 0:
            gyro_noise = np.random.normal(
                0, self.config.gyro_bias_instability * np.pi/180 * np.sqrt(dt), 3
            )
            self.gyro_bias += gyro_noise
    
    def _apply_temperature_drift(self, accel: np.ndarray, 
                                  temperature: float) -> np.ndarray:
        """Apply temperature-dependent sensitivity and offset changes"""
        delta_t = temperature - self.config.reference_temp
        
        # Sensitivity change
        sensitivity_factor = 1.0 + self.config.temp_sensitivity_coeff * delta_t
        
        # Offset change
        offset_change = self.config.temp_offset_coeff * delta_t * 9.80665
        
        return accel * sensitivity_factor + offset_change
    
    def _apply_cross_axis(self, values: np.ndarray) -> np.ndarray:
        """Apply cross-axis sensitivity matrix"""
        return self.config.cross_axis_matrix @ values
    
    def _apply_time_sync(self, n_samples: int) -> np.ndarray:
        """Generate timestamps with jitter and clock drift"""
        # Ideal timestamps
        ideal_times = np.arange(n_samples) * self.dt
        
        # Add sampling jitter
        jitter = np.random.uniform(
            -self.config.jitter_pct * self.dt,
            self.config.jitter_pct * self.dt,
            n_samples
        )
        
        # Add clock drift (cumulative)
        drift_rate = self.config.clock_drift_ppm * 1e-6  # Convert ppm
        drift = drift_rate * ideal_times * self.dt
        
        actual_times = ideal_times + jitter + drift
        return actual_times
    
    def simulate(self, 
                 crash_pulse: np.ndarray,
                 crash_gyro: Optional[np.ndarray] = None,
                 temperature: float = 25.0,
                 start_time: float = 0.0) -> dict:
        """
        Simulate MEMS sensor output for a crash pulse.
        
        Args:
            crash_pulse: Nx3 array of accelerations (m/s²) [ax, ay, az]
            crash_gyro: Nx3 array of angular rates (rad/s) [gx, gy, gz] (optional)
            temperature: Sensor temperature in °C
            start_time: Start time offset in seconds
            
        Returns:
            Dictionary with simulated sensor readings
        """
        n_samples = len(crash_pulse)
        
        # Ensure crash_gyro exists (zeros if not provided)
        if crash_gyro is None:
            crash_gyro = np.zeros((n_samples, 3))
        
        # Stage 1: Bandwidth limiting (before clipping to match real analog chain)
        if self.accel_sos is not None:
            accel_filtered = sosfilt(self.accel_sos, crash_pulse, axis=0)
        else:
            accel_filtered = crash_pulse.copy()
            
        # Stage 2: Noise injection
        accel_noisy = np.zeros_like(accel_filtered)
        for i in range(3):
            accel_noisy[:, i] = self._apply_noise(
                accel_filtered[:, i], 
                self.config.accel_noise_density,
                i
            )
        
        # Stage 3: Temperature drift
        accel_temp = self._apply_temperature_drift(accel_noisy, temperature)
        
        # Stage 4: Cross-axis sensitivity
        accel_cross = np.apply_along_axis(
            self._apply_cross_axis, 1, accel_temp
        )
        
        # Add factory offset and bias
        accel_offset = accel_cross + self.config.factory_offset_accel * 9.80665
        accel_offset += self.accel_bias * 9.80665
        
        # Stage 5: Range clipping (LAST - after all analog processing)
        # This matches real MEMS behavior: ADC clips at the end of the signal chain
        accel_final, accel_sat = self._clip_to_range(
            accel_offset, self.config.accel_range_g
        )
        
        # Update bias for next call
        self._update_bias(n_samples * self.dt)
        
        # Process gyroscope if available
        if self.config.gyro_range_dps > 0:
            gyro_clipped, gyro_sat = self._clip_to_range(
                crash_gyro * 180 / np.pi, self.config.gyro_range_dps
            )
            
            if self.gyro_sos is not None:
                gyro_filtered = sosfilt(self.gyro_sos, gyro_clipped, axis=0)
            else:
                gyro_filtered = gyro_clipped
                
            gyro_noisy = np.zeros_like(gyro_filtered)
            for i in range(3):
                gyro_noisy[:, i] = self._apply_noise(
                    gyro_filtered[:, i],
                    self.config.gyro_noise_density,
                    i
                )
                
            gyro_final = gyro_noisy + self.config.factory_offset_gyro * np.pi/180
            gyro_final += self.gyro_bias * np.pi/180
        else:
            gyro_final = np.zeros((n_samples, 3))
            gyro_sat = np.zeros((n_samples, 3), dtype=bool)
        
        # Stage 6: Time synchronization
        timestamps = self._apply_time_sync(n_samples) + start_time
        
        return {
            'timestamp': timestamps,
            'accel': accel_final,
            'gyro': gyro_final,
            'saturation': accel_sat,
            'gyro_saturation': gyro_sat,
            'temperature': temperature,
            'sampling_rate': self.sampling_rate,
            'sensor_name': self.config.name,
        }


def load_sensor(sensor_name: str, sampling_rate: int = 1000) -> MEMSSensorSimulator:
    """Convenience function to load a sensor by name"""
    import os
    
    # Get the directory where this file is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Navigate to sensors directory
    sensors_dir = os.path.join(os.path.dirname(current_dir), 'sensors')
    
    config_path = os.path.join(sensors_dir, f"{sensor_name.lower()}.yaml")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Sensor configuration not found: {config_path}")
    
    config = SensorConfig.from_yaml(config_path)
    return MEMSSensorSimulator(config, sampling_rate)
