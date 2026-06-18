"""
Crash Pulse Generator for VISTA 2.0 HIL Simulation
Generates parametric crash pulse waveforms for MEMS sensor simulation
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional
from enum import Enum

class CrashType(Enum):
    """Standard crash pulse shapes from NHTSA research"""
    HAVERSINE = "haversine"      # sin² - Most realistic for frontal crashes
    HALF_SINE = "half_sine"      # sin - Good general approximation
    SQUARE = "square"            # Square wave - Worst case for algorithms
    TRIANGULAR = "triangular"    # Triangle - Simple baseline
    CUSTOM = "custom"            # User-defined pulse shape

class CrashDirection(Enum):
    """Crash impact direction"""
    FRONTAL = "frontal"
    REAR = "rear"
    LEFT_SIDE = "left_side"
    RIGHT_SIDE = "right_side"
    OFFSET = "offset"            # Offset frontal crash
    OBLIQUE = "oblique"          # Angled crash

@dataclass
class CrashPulseConfig:
    """Configuration for crash pulse generation"""
    crash_type: CrashType
    peak_g: float                 # Peak acceleration in g
    duration_ms: float            # Crash duration in milliseconds
    delta_v_kmh: float           # Delta-V in km/h
    direction: CrashDirection
    sampling_rate: int = 1000     # Hz
    vehicle_mass_kg: float = 1500 # Typical passenger vehicle mass
    crush_distance_m: float = 0.5 # Vehicle crush distance
    
    def __post_init__(self):
        """Validate configuration"""
        if self.peak_g <= 0:
            raise ValueError(f"peak_g must be positive, got {self.peak_g}")
        if self.duration_ms <= 0:
            raise ValueError(f"duration_ms must be positive, got {self.duration_ms}")
        if self.delta_v_kmh <= 0:
            raise ValueError(f"delta_v_kmh must be positive, got {self.delta_v_kmh}")


class CrashPulseGenerator:
    """
    Generates realistic crash pulse waveforms based on NHTSA research.
    
    Reference: NHTSA "Crash Pulse Modeling for Vehicle Safety Research"
    (https://www.nhtsa.gov/sites/nhtsa.gov/files/18esv-000501.pdf)
    
    The generator creates parametric crash pulses that can be used to:
    - Test VISTA crash detection algorithms
    - Validate MEMS sensor simulation
    - Generate training data for ML models
    - Run batch simulations of 1000+ scenarios
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize crash pulse generator.
        
        Args:
            seed: Random seed for reproducibility (optional)
        """
        self.rng = np.random.default_rng(seed)
        
    def _haversine_pulse(self, t: np.ndarray, peak_g: float, 
                         duration_s: float) -> np.ndarray:
        """
        Haversine (sin²) crash pulse.
        
        Most realistic for frontal barrier crashes per NHTSA research.
        Formula: a(t) = P × sin²(πt/T) for 0 ≤ t ≤ T
        
        Args:
            t: Time array (seconds)
            peak_g: Peak acceleration (g)
            duration_s: Crash duration (seconds)
            
        Returns:
            Acceleration array (g)
        """
        # Normalize time to [0, 1]
        t_norm = t / duration_s
        
        # Haversine pulse
        pulse = peak_g * np.sin(np.pi * t_norm) ** 2
        
        # Zero outside crash duration
        pulse = np.where((t >= 0) & (t <= duration_s), pulse, 0)
        
        return pulse
    
    def _half_sine_pulse(self, t: np.ndarray, peak_g: float,
                         duration_s: float) -> np.ndarray:
        """
        Half-sine crash pulse.
        
        Good general approximation for various crash types.
        Formula: a(t) = P × sin(πt/T) for 0 ≤ t ≤ T
        
        Args:
            t: Time array (seconds)
            peak_g: Peak acceleration (g)
            duration_s: Crash duration (seconds)
            
        Returns:
            Acceleration array (g)
        """
        t_norm = t / duration_s
        pulse = peak_g * np.sin(np.pi * t_norm)
        pulse = np.where((t >= 0) & (t <= duration_s), pulse, 0)
        
        return pulse
    
    def _square_pulse(self, t: np.ndarray, peak_g: float,
                      duration_s: float) -> np.ndarray:
        """
        Square wave crash pulse.
        
        Worst-case scenario for crash detection algorithms.
        Formula: a(t) = P for 0 ≤ t ≤ T
        
        Args:
            t: Time array (seconds)
            peak_g: Peak acceleration (g)
            duration_s: Crash duration (seconds)
            
        Returns:
            Acceleration array (g)
        """
        pulse = np.where((t >= 0) & (t <= duration_s), peak_g, 0)
        return pulse
    
    def _triangular_pulse(self, t: np.ndarray, peak_g: float,
                          duration_s: float) -> np.ndarray:
        """
        Triangular crash pulse.
        
        Simple baseline for comparison.
        Formula: a(t) = P × (1 - |2t/T - 1|) for 0 ≤ t ≤ T
        
        Args:
            t: Time array (seconds)
            peak_g: Peak acceleration (g)
            duration_s: Crash duration (seconds)
            
        Returns:
            Acceleration array (g)
        """
        t_norm = t / duration_s
        pulse = peak_g * (1 - np.abs(2 * t_norm - 1))
        pulse = np.where((t >= 0) & (t <= duration_s), pulse, 0)
        
        return pulse
    
    def _add_realistic_features(self, pulse: np.ndarray, 
                                 sampling_rate: int) -> np.ndarray:
        """
        Add realistic features to idealized crash pulse.
        
        Features added:
        - Pre-impact vibration (road noise)
        - Impact onset ringing
        - Post-impact oscillation
        - Random variations
        
        Args:
            pulse: Idealized crash pulse (g)
            sampling_rate: Sampling rate (Hz)
            
        Returns:
            Enhanced pulse with realistic features
        """
        n_samples = len(pulse)
        dt = 1.0 / sampling_rate
        
        # Add high-frequency vibration (road noise)
        # Typically 10-50 Hz, amplitude 0.1-0.5g
        t = np.arange(n_samples) * dt
        vibration_freq = self.rng.uniform(10, 50)
        vibration_amp = self.rng.uniform(0.1, 0.5)
        vibration = vibration_amp * np.sin(2 * np.pi * vibration_freq * t)
        
        # Add impact onset ringing (100-500 Hz, decays quickly)
        ring_freq = self.rng.uniform(100, 500)
        ring_amp = self.rng.uniform(0.5, 2.0)
        ring_decay = self.rng.uniform(5, 20)  # Decay rate
        ring = ring_amp * np.exp(-ring_decay * t) * np.sin(2 * np.pi * ring_freq * t)
        
        # Add random noise (0.1-0.3g RMS)
        noise_amp = self.rng.uniform(0.1, 0.3)
        noise = self.rng.normal(0, noise_amp, n_samples)
        
        # Combine all components
        enhanced = pulse + vibration + ring + noise
        
        return enhanced
    
    def _apply_direction_transform(self, pulse: np.ndarray,
                                    direction: CrashDirection) -> Tuple[np.ndarray, np.ndarray]:
        """
        Transform crash pulse based on impact direction.
        
        For frontal/rear crashes: primary acceleration on X-axis
        For side crashes: primary acceleration on Y-axis
        
        Args:
            pulse: 1D crash pulse (g)
            direction: Impact direction
            
        Returns:
            Tuple of (accel_xyz, gyro_xyz) in g and °/s
        """
        n_samples = len(pulse)
        
        # Initialize arrays
        accel_xyz = np.zeros((n_samples, 3))
        gyro_xyz = np.zeros((n_samples, 3))
        
        if direction == CrashDirection.FRONTAL:
            # Frontal crash: deceleration on X-axis
            accel_xyz[:, 0] = pulse  # Forward deceleration
            # Add slight pitch rotation
            gyro_xyz[:, 1] = self.rng.normal(0, 5, n_samples)  # Pitch
            
        elif direction == CrashDirection.REAR:
            # Rear crash: acceleration on X-axis (vehicle pushed forward)
            accel_xyz[:, 0] = -pulse  # Reverse direction
            # Add slight pitch rotation
            gyro_xyz[:, 1] = self.rng.normal(0, 5, n_samples)
            
        elif direction == CrashDirection.LEFT_SIDE:
            # Left side impact: acceleration on Y-axis
            accel_xyz[:, 1] = pulse  # Lateral acceleration
            # Add yaw rotation
            gyro_xyz[:, 2] = self.rng.normal(0, 10, n_samples)  # Yaw
            
        elif direction == CrashDirection.RIGHT_SIDE:
            # Right side impact: acceleration on Y-axis (opposite direction)
            accel_xyz[:, 1] = -pulse
            gyro_xyz[:, 2] = self.rng.normal(0, 10, n_samples)
            
        elif direction == CrashDirection.OFFSET:
            # Offset frontal: mix of X and Y
            offset_pct = self.rng.uniform(0.3, 0.7)
            accel_xyz[:, 0] = pulse * (1 - offset_pct)
            accel_xyz[:, 1] = pulse * offset_pct
            gyro_xyz[:, 2] = self.rng.normal(0, 15, n_samples)  # Yaw
            
        elif direction == CrashDirection.OBLIQUE:
            # Oblique crash: significant rotation
            angle = self.rng.uniform(15, 45)  # Impact angle
            accel_xyz[:, 0] = pulse * np.cos(np.radians(angle))
            accel_xyz[:, 1] = pulse * np.sin(np.radians(angle))
            gyro_xyz[:, 2] = self.rng.normal(0, 20, n_samples)
        
        return accel_xyz, gyro_xyz
    
    def generate(self, 
                 crash_type: str = "haversine",
                 peak_g: float = 50.0,
                 duration_ms: float = 100.0,
                 delta_v_kmh: float = 40.0,
                 direction: str = "frontal",
                 sampling_rate: int = 1000,
                 add_realistic_features: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate a complete crash pulse with realistic features.
        
        Args:
            crash_type: Type of pulse (haversine, half_sine, square, triangular)
            peak_g: Peak acceleration in g
            duration_ms: Crash duration in milliseconds
            delta_v_kmh: Delta-V in km/h
            direction: Impact direction (frontal, rear, left_side, etc.)
            sampling_rate: Sampling rate in Hz
            add_realistic_features: Whether to add realistic vibration/ringing
            
        Returns:
            Tuple of (time_array, accel_xyz, gyro_xyz)
            - time_array: Time in seconds
            - accel_xyz: Acceleration in m/s² (N×3)
            - gyro_xyz: Angular rate in rad/s (N×3)
        """
        # Convert units
        duration_s = duration_ms / 1000.0
        peak_ms2 = peak_g * 9.80665  # Convert g to m/s²
        
        # Generate time array
        n_samples = int(duration_s * sampling_rate) + 100  # Add buffer
        t = np.arange(n_samples) / sampling_rate
        
        # Generate base pulse based on type
        crash_type_enum = CrashType(crash_type)
        
        if crash_type_enum == CrashType.HAVERSINE:
            pulse_g = self._haversine_pulse(t, peak_g, duration_s)
        elif crash_type_enum == CrashType.HALF_SINE:
            pulse_g = self._half_sine_pulse(t, peak_g, duration_s)
        elif crash_type_enum == CrashType.SQUARE:
            pulse_g = self._square_pulse(t, peak_g, duration_s)
        elif crash_type_enum == CrashType.TRIANGULAR:
            pulse_g = self._triangular_pulse(t, peak_g, duration_s)
        else:
            raise ValueError(f"Unknown crash type: {crash_type}")
        
        # Add realistic features if requested
        if add_realistic_features:
            pulse_g = self._add_realistic_features(pulse_g, sampling_rate)
        
        # Apply direction transform
        direction_enum = CrashDirection(direction)
        accel_xyz_g, gyro_xyz_dps = self._apply_direction_transform(
            pulse_g, direction_enum
        )
        
        # Convert to SI units
        accel_xyz_ms2 = accel_xyz_g * 9.80665  # g to m/s²
        gyro_xyz_rads = gyro_xyz_dps * np.pi / 180  # °/s to rad/s
        
        # Trim to actual crash duration + small buffer
        actual_samples = int(duration_s * sampling_rate) + 10
        t = t[:actual_samples]
        accel_xyz_ms2 = accel_xyz_ms2[:actual_samples]
        gyro_xyz_rads = gyro_xyz_rads[:actual_samples]
        
        return t, accel_xyz_ms2, gyro_xyz_rads
    
    def generate_random_crash(self, 
                              seed: Optional[int] = None) -> dict:
        """
        Generate a random crash scenario with realistic parameters.
        
        Based on NHTSA crash statistics:
        - Frontal crashes: 40% of severe crashes
        - Side crashes: 30%
        - Rear crashes: 20%
        - Other: 10%
        
        Delta-V distribution:
        - Minor: 5-20 km/h (30%)
        - Moderate: 20-50 km/h (40%)
        - Severe: 50-100 km/h (25%)
        - Fatal: >100 km/h (5%)
        
        Args:
            seed: Random seed for reproducibility
            
        Returns:
            Dictionary with crash configuration
        """
        if seed is not None:
            rng = np.random.default_rng(seed)
        else:
            rng = self.rng
        
        # Random direction
        direction = rng.choice(
            ['frontal', 'rear', 'left_side', 'right_side'],
            p=[0.4, 0.2, 0.2, 0.2]
        )
        
        # Random delta-V based on severity distribution
        severity = rng.random()
        if severity < 0.3:  # Minor
            delta_v = rng.uniform(5, 20)
        elif severity < 0.7:  # Moderate
            delta_v = rng.uniform(20, 50)
        elif severity < 0.95:  # Severe
            delta_v = rng.uniform(50, 100)
        else:  # Fatal
            delta_v = rng.uniform(100, 150)
        
        # Estimate peak acceleration from delta-V
        # Rule of thumb: peak_g ≈ delta_v_kmh / (duration_ms * 0.0036)
        duration_ms = rng.uniform(20, 150)  # Typical crash duration
        peak_g = delta_v / (duration_ms * 0.0036)
        peak_g = np.clip(peak_g, 5, 200)  # Reasonable range
        
        # Random crash type
        crash_type = rng.choice(['haversine', 'half_sine', 'square', 'triangular'])
        
        return {
            'type': crash_type,
            'peak_g': float(peak_g),
            'duration_ms': float(duration_ms),
            'delta_v_kmh': float(delta_v),
            'direction': direction,
            'severity': 'minor' if delta_v < 20 else 
                       'moderate' if delta_v < 50 else 
                       'severe' if delta_v < 100 else 'fatal',
        }
    
    def generate_batch(self, n_scenarios: int = 1000,
                       seed: int = 42) -> list:
        """
        Generate a batch of diverse crash scenarios.
        
        Args:
            n_scenarios: Number of scenarios to generate
            seed: Random seed for reproducibility
            
        Returns:
            List of crash configuration dictionaries
        """
        rng = np.random.default_rng(seed)
        scenarios = []
        
        for i in range(n_scenarios):
            scenario = self.generate_random_crash(seed=int(rng.integers(0, 2**31)))
            scenario['id'] = i
            scenarios.append(scenario)
        
        return scenarios


def demo_crash_pulses():
    """Demonstrate crash pulse generation"""
    import matplotlib.pyplot as plt
    
    generator = CrashPulseGenerator(seed=42)
    
    # Generate example pulses
    configs = [
        {'type': 'haversine', 'peak_g': 50, 'duration_ms': 100, 
         'delta_v_kmh': 40, 'direction': 'frontal'},
        {'type': 'half_sine', 'peak_g': 30, 'duration_ms': 80,
         'delta_v_kmh': 25, 'direction': 'rear'},
        {'type': 'square', 'peak_g': 80, 'duration_ms': 50,
         'delta_v_kmh': 60, 'direction': 'left_side'},
        {'type': 'triangular', 'peak_g': 40, 'duration_ms': 120,
         'delta_v_kmh': 35, 'direction': 'right_side'},
    ]
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()
    
    for i, config in enumerate(configs):
        t, accel, gyro = generator.generate(**config)
        
        # Convert to g for plotting
        accel_g = accel / 9.80665
        
        axes[i].plot(t * 1000, accel_g[:, 0], 'r-', label='X-axis', alpha=0.8)
        axes[i].plot(t * 1000, accel_g[:, 1], 'g-', label='Y-axis', alpha=0.8)
        axes[i].plot(t * 1000, accel_g[:, 2], 'b-', label='Z-axis', alpha=0.8)
        
        axes[i].set_xlabel('Time (ms)')
        axes[i].set_ylabel('Acceleration (g)')
        axes[i].set_title(f"{config['type'].upper()} - {config['direction']}\n"
                         f"Peak: {config['peak_g']}g, Duration: {config['duration_ms']}ms\n"
                         f"ΔV: {config['delta_v_kmh']} km/h")
        axes[i].grid(True, alpha=0.3)
        axes[i].legend(loc='upper right')
    
    plt.tight_layout()
    plt.savefig('crash_pulse_demo.png', dpi=150)
    plt.show()


if __name__ == "__main__":
    demo_crash_pulses()
