"""
VISTA 2.0 — Vehicle Transfer Function + Realistic Simulation Chain

Models the complete physical chain from barrier impact to sensor output:
Impact Event → Vehicle Structural Response → Sensor Mounting → MEMS Dynamics → VISTA Algorithm

This is the VIRTUAL CRASH TEST LAB that replaces physical hardware for development.
"""

import numpy as np
from scipy.signal import butter, sosfilt, lfilter
from dataclasses import dataclass
from typing import Optional, Tuple


# =============================================================================
# VEHICLE TRANSFER FUNCTION
# =============================================================================

@dataclass
class VehicleTransferConfig:
    """Vehicle structural response parameters.
    
    Based on vibration theory: the vehicle body acts as a 2nd-order 
    low-pass filter between the impact point and the sensor mounting location.
    
    Natural frequency (ωn): determined by vehicle mass and structural stiffness.
    Damping ratio (ζ): determined by material damping and structural joints.
    """
    natural_freq_hz: float = 30.0   # Body mode frequency (20-50 Hz typical)
    damping_ratio: float = 0.2      # Underdamped (0.1-0.3 typical)
    mounting_resonance_hz: float = 80.0  # Mount stiffness resonance
    mounting_damping: float = 0.15   # Mount damping


# Vehicle class presets (estimated from crash test literature)
VEHICLE_PRESETS = {
    'sedan': VehicleTransferConfig(natural_freq_hz=30, damping_ratio=0.20, 
                                    mounting_resonance_hz=80, mounting_damping=0.15),
    'suv': VehicleTransferConfig(natural_freq_hz=25, damping_ratio=0.25,
                                  mounting_resonance_hz=60, mounting_damping=0.18),
    'truck': VehicleTransferConfig(natural_freq_hz=15, damping_ratio=0.30,
                                    mounting_resonance_hz=40, mounting_damping=0.20),
    'motorcycle': VehicleTransferConfig(natural_freq_hz=45, damping_ratio=0.15,
                                         mounting_resonance_hz=120, mounting_damping=0.10),
}

# Mounting location presets
MOUNTING_PRESETS = {
    'floor_structural': {'resonance_hz': 80, 'damping': 0.15, 'attenuation_db': 0},
    'floor柔性': {'resonance_hz': 40, 'damping': 0.20, 'attenuation_db': 3},
    'dashboard': {'resonance_hz': 35, 'damping': 0.25, 'attenuation_db': 6},
    'seat_rail': {'resonance_hz': 20, 'damping': 0.30, 'attenuation_db': 10},
    'acm_location': {'resonance_hz': 100, 'damping': 0.10, 'attenuation_db': 0},  # EDR reference
}


class VehicleTransferFunction:
    """Models how a vehicle's structural response filters the crash pulse.
    
    The vehicle body acts as a mechanical filter between the impact point 
    and the sensor mounting location. This filter is characterized by:
    - Natural frequency (ωn): vehicle body mode
    - Damping ratio (ζ): structural damping
    - Mounting resonance: sensor attachment point stiffness
    
    For a rigid ACM mount (EDR reference): minimal filtering
    For a flexible floor mount: significant high-frequency attenuation
    For a dashboard mount: moderate filtering with resonance peaks
    """
    
    def __init__(self, vehicle_class: str = 'sedan', 
                 mounting: str = 'floor_structural'):
        self.vehicle_config = VEHICLE_PRESETS.get(vehicle_class, VEHICLE_PRESETS['sedan'])
        self.mounting_config = MOUNTING_PRESETS.get(mounting, MOUNTING_PRESETS['floor_structural'])
        
        # Build the transfer function as cascaded 2nd-order sections
        # Section 1: Vehicle body dynamics
        wn1 = 2 * np.pi * self.vehicle_config.natural_freq_hz
        zeta1 = self.vehicle_config.damping_ratio
        # Section 2: Mounting dynamics
        wn2 = 2 * np.pi * self.mounting_config['resonance_hz']
        zeta2 = self.mounting_config['damping']
        
        # Design Butterworth-like 2nd-order sections
        # Vehicle body: low-pass at natural frequency
        nyquist = 500  # Assume 1kHz sampling
        self.body_sos = butter(2, min(self.vehicle_config.natural_freq_hz / nyquist, 0.99), 
                               btype='low', output='sos')
        # Mounting: additional filtering
        self.mount_sos = butter(2, min(self.mounting_config['resonance_hz'] / nyquist, 0.99),
                                btype='low', output='sos')
        
        # Attenuation from mounting (dB to linear)
        self.mount_attenuation = 10**(-self.mounting_config['attenuation_db'] / 20)
    
    def filter_crash_pulse(self, crash_pulse_ms2: np.ndarray, 
                           sampling_rate: int = 1000) -> np.ndarray:
        """Apply vehicle transfer function to crash pulse.
        
        Args:
            crash_pulse_ms2: True crash acceleration at impact point (m/s²)
            sampling_rate: Sampling rate in Hz
            
        Returns:
            Filtered acceleration at sensor mounting point (m/s²)
        """
        # Apply vehicle body dynamics (low-pass filter)
        body_filtered = sosfilt(self.body_sos, crash_pulse_ms2, axis=0)
        
        # Apply mounting dynamics (additional filtering)
        mount_filtered = sosfilt(self.mount_sos, body_filtered, axis=0)
        
        # Apply mounting attenuation
        attenuated = mount_filtered * self.mount_attenuation
        
        return attenuated


# =============================================================================
# PRE-CRASH VIBRATION MODEL
# =============================================================================

class PreCrashVibration:
    """Models realistic pre-crash vibration environment.
    
    A moving vehicle produces continuous vibration from:
    - Engine firing (RPM-dependent frequency)
    - Road surface interaction (broadband noise)
    - Wind buffeting (speed-dependent)
    - Tire noise (speed-dependent)
    
    This vibration is ALWAYS present before the crash and must be
    realistic enough to test VISTA's ability to discriminate crash
    events from normal driving vibration.
    """
    
    def __init__(self, vehicle_class: str = 'sedan'):
        # Engine parameters
        self.engine_cylinders = {'sedan': 4, 'suv': 6, 'truck': 8, 'motorcycle': 2}
        self.n_cyl = self.engine_cylinders.get(vehicle_class, 4)
        
        # Vibration amplitudes (in g)
        self.engine_vibration_g = 0.3  # 0.3g at 3000 RPM
        self.road_vibration_g = 0.15   # 0.15g on rough road
        self.wind_vibration_g = 0.05   # 0.05g at highway speed
    
    def generate(self, duration_s: float, speed_kmh: float, 
                 rpm: float, road_roughness: float = 0.5,
                 sampling_rate: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """Generate pre-crash vibration signal.
        
        Args:
            duration_s: Duration in seconds
            speed_kmh: Vehicle speed in km/h
            rpm: Engine RPM
            road_roughness: 0=smooth, 1=very rough
            sampling_rate: Hz
            
        Returns:
            vibration_ms2: 3-axis vibration in m/s²
            timestamps: Time array in seconds
        """
        n_samples = int(duration_s * sampling_rate)
        t = np.arange(n_samples) / sampling_rate
        
        # Engine vibration (fundamental + harmonics)
        f_engine = rpm * self.n_cyl / 60  # Firing frequency
        engine_amp = self.engine_vibration_g * (rpm / 3000) * 9.81
        engine_vib = engine_amp * (
            0.6 * np.sin(2 * np.pi * f_engine * t) +
            0.3 * np.sin(2 * np.pi * 2 * f_engine * t) +
            0.1 * np.sin(2 * np.pi * 3 * f_engine * t)
        )
        
        # Road vibration (band-limited noise)
        road_amp = self.road_vibration_g * road_roughness * 9.81
        road_vib = road_amp * np.random.randn(n_samples)
        # Low-pass filter at 50 Hz
        sos = butter(4, 50 / (sampling_rate / 2), btype='low', output='sos')
        road_vib = sosfilt(sos, road_vib)
        
        # Wind vibration (speed-dependent)
        wind_amp = self.wind_vibration_g * (speed_kmh / 100) * 9.81
        wind_vib = wind_amp * np.random.randn(n_samples)
        
        # Combine all vibrations
        vibration = np.zeros((n_samples, 3))
        vibration[:, 0] = engine_vib + road_vib  # x-axis (longitudinal)
        vibration[:, 1] = wind_vib * 0.5          # y-axis (lateral)
        vibration[:, 2] = road_vib * 0.3          # z-axis (vertical)
        
        timestamps = t
        return vibration, timestamps


# =============================================================================
# COMPLETE SIMULATION CHAIN
# =============================================================================

@dataclass
class CrashScenario:
    """Complete crash scenario specification."""
    # Impact parameters
    speed_kmh: float              # Vehicle speed at impact
    impact_angle_deg: float       # Impact angle (0=full frontal)
    overlap_percent: float        # Barrier overlap (100=full width)
    barrier_type: str             # 'rigid', 'deformable', 'pole'
    
    # Vehicle parameters
    vehicle_class: str            # 'sedan', 'suv', 'truck', 'motorcycle'
    vehicle_mass_kg: float        # Vehicle mass
    
    # Sensor parameters
    sensor_mounting: str          # 'floor_structural', 'dashboard', 'acm_location'
    sensor_name: str              # 'mpu6050', 'h3lis331dl', 'iam20680hp'
    
    # Environmental parameters
    temperature_c: float = 25.0
    road_roughness: float = 0.5    # 0=smooth, 1=rough
    engine_rpm: float = 3000
    
    # Pre-crash duration
    pre_crash_duration_s: float = 2.0


class RealisticCrashSimulator:
    """Complete crash simulation chain: Impact → Vehicle → Sensor → VISTA.
    
    This is the VIRTUAL CRASH TEST LAB. It models the complete physical
    chain from barrier impact to sensor output, enabling realistic testing
    of VISTA algorithms without physical hardware.
    
    CHAIN:
    1. Impact Event → Parametric crash pulse
    2. Vehicle Transfer Function → Structural filtering
    3. Pre-Crash Vibration → Realistic noise environment
    4. Sensor Mounting → Attachment point effects
    5. MEMS Simulator → Realistic sensor output
    6. VISTA Algorithm → Detection and reconstruction
    """
    
    def __init__(self):
        from vista_hil import HILSimulation, load_sensor
        self.hil = HILSimulation()
    
    def simulate_crash(self, scenario: CrashScenario) -> dict:
        """Run complete crash simulation chain.
        
        Returns:
            Dictionary with:
            - 'true_crash_pulse': Original crash acceleration
            - 'vehicle_response': After vehicle transfer function
            - 'sensor_output': After MEMS simulation
            - 'pre_crash_vibration': Pre-crash vibration environment
            - 'vista_result': VISTA algorithm output
            - 'scenario': Input parameters
        """
        sampling_rate = 1000  # 1kHz
        
        # --- STEP 1: Generate crash pulse ---
        crash_pulse = self._generate_crash_pulse(scenario, sampling_rate)
        
        # --- STEP 2: Apply vehicle transfer function ---
        vtf = VehicleTransferConfig(
            natural_freq_hz=self._get_vehicle_freq(scenario.vehicle_class),
            damping_ratio=self._get_vehicle_damping(scenario.vehicle_class)
        )
        vehicle_response = self._apply_transfer_function(crash_pulse, vtf, sampling_rate)
        
        # --- STEP 3: Add pre-crash vibration ---
        vibration, vib_timestamps = self._generate_vibration(scenario, sampling_rate)
        
        # --- STEP 4: Simulate MEMS sensor ---
        sensor_output = self._simulate_sensor(vehicle_response, scenario, sampling_rate)
        
        # --- STEP 5: Run VISTA algorithm ---
        vista_result = self._run_vista(sensor_output, scenario)
        
        return {
            'true_crash_pulse': crash_pulse,
            'vehicle_response': vehicle_response,
            'sensor_output': sensor_output,
            'pre_crash_vibration': vibration,
            'vista_result': vista_result,
            'scenario': scenario,
            'sampling_rate': sampling_rate,
        }
    
    def _generate_crash_pulse(self, scenario: CrashScenario, fs: int) -> np.ndarray:
        """Generate parametric crash pulse based on scenario."""
        # Estimate peak acceleration from speed and mass
        # Simplified: E = 0.5 * m * v², F = m*a, assuming 50ms crush time
        v_ms = scenario.speed_kmh / 3.6
        kinetic_energy = 0.5 * scenario.vehicle_mass_kg * v_ms**2
        # Assume 50% energy absorption in 50ms (typical for frontal)
        crush_time_s = 0.05
        avg_force = kinetic_energy / (0.5 * v_ms * crush_time_s)
        peak_accel_g = avg_force / (scenario.vehicle_mass_kg * 9.81) * 1.5  # 1.5x peak factor
        
        # Overlap adjustment
        overlap_factor = scenario.overlap_percent / 100.0
        peak_accel_g *= overlap_factor
        
        # Generate haversine pulse
        n_samples = int(crush_time_s * 1000)
        t = np.arange(n_samples) / 1000.0
        pulse_g = peak_accel_g * np.sin(np.pi * t / crush_time_s)**2
        
        # Convert to m/s² (3-axis) — rotated by impact angle
        # 0° (frontal) → X-axis acceleration
        # 90° (side)   → Y-axis acceleration
        # 45° (oblique)→ Both X and Y components
        pulse_ms2 = np.zeros((n_samples, 3))
        angle_rad = np.radians(scenario.impact_angle_deg)
        pulse_ms2[:, 0] = pulse_g * 9.81 * np.cos(angle_rad)  # x-component (longitudinal)
        pulse_ms2[:, 1] = pulse_g * 9.81 * np.sin(angle_rad)  # y-component (lateral)
        pulse_ms2[:, 2] = 9.81  # gravity always present
        
        return pulse_ms2
    
    def _apply_transfer_function(self, pulse_ms2: np.ndarray, 
                                  vtf: VehicleTransferConfig, fs: int) -> np.ndarray:
        """Apply vehicle structural transfer function."""
        # Vehicle body dynamics (2nd-order low-pass)
        nyquist = fs / 2
        body_cutoff = min(vtf.natural_freq_hz / nyquist, 0.99)
        body_sos = butter(2, body_cutoff, btype='low', output='sos')
        
        # Apply to each axis
        filtered = np.zeros_like(pulse_ms2)
        for axis in range(3):
            filtered[:, axis] = sosfilt(body_sos, pulse_ms2[:, axis])
        
        return filtered
    
    def _generate_vibration(self, scenario: CrashScenario, fs: int) -> Tuple[np.ndarray, np.ndarray]:
        """Generate pre-crash vibration environment."""
        vib_gen = PreCrashVibration(scenario.vehicle_class)
        duration = scenario.pre_crash_duration_s
        vib, timestamps = vib_gen.generate(
            duration_s=duration,
            speed_kmh=scenario.speed_kmh,
            rpm=scenario.engine_rpm,
            road_roughness=scenario.road_roughness,
            sampling_rate=fs
        )
        return vib, timestamps
    
    def _simulate_sensor(self, vehicle_response_ms2: np.ndarray, 
                         scenario: CrashScenario, fs: int) -> dict:
        """Simulate MEMS sensor response to crash pulse."""
        from vista_hil import load_sensor
        
        sensor = load_sensor(scenario.sensor_name, sampling_rate=fs)
        
        # Add pre-crash vibration to crash pulse
        vib, vib_ts = self._generate_vibration(scenario, fs)
        
        # Combine vibration + crash (vibration is pre-crash, crash is the event)
        # For simplicity, add vibration amplitude to crash pulse baseline
        # In reality, vibration continues through the crash
        n_crash = len(vehicle_response_ms2)
        combined = vehicle_response_ms2.copy()
        
        # Add vibration noise floor to the crash pulse
        if len(vib) > 0:
            vib_rms = np.sqrt(np.mean(vib**2))
            noise = np.random.randn(n_crash, 3) * vib_rms * 0.1  # 10% of vibration
            combined += noise
        
        # Simulate sensor
        gyro = np.zeros((n_crash, 3))
        result = sensor.simulate(combined, gyro, temperature=scenario.temperature_c)
        
        return result
    
    def _run_vista(self, sensor_output: dict, scenario: CrashScenario) -> dict:
        """Run VISTA algorithm on simulated sensor data."""
        from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass
        
        accel_ms2 = sensor_output['accel']  # Already in m/s²
        timestamps = sensor_output['timestamp']
        
        vehicle_class_map = {
            'sedan': VehicleClass.SEDAN,
            'suv': VehicleClass.SUV,
            'truck': VehicleClass.TRUCK,
            'motorcycle': VehicleClass.MOTORCYCLE,
        }
        
        config = PDTSAConfig(
            vehicle_class=vehicle_class_map.get(scenario.vehicle_class, VehicleClass.UNKNOWN)
        )
        pdtsa = PDTSAv2(config)
        result = pdtsa.detect(accel_ms2, timestamps)
        
        return {
            'detected': result.features.detected,
            'confidence': result.features.confidence,
            'delta_v_kmh': result.delta_v_kmh,
            'ci_lower': result.ci_lower,
            'ci_upper': result.ci_upper,
            'pdof_degrees': result.pdof_degrees,
            'peak_accel_g': result.features.peak_accel_g,
            'pulse_duration_ms': result.features.sustain_duration_ms,
        }
    
    def _get_vehicle_freq(self, vehicle_class: str) -> float:
        """Get natural frequency for vehicle class."""
        return {
            'sedan': 30, 'suv': 25, 'truck': 15, 'motorcycle': 45
        }.get(vehicle_class, 30)
    
    def _get_vehicle_damping(self, vehicle_class: str) -> float:
        """Get damping ratio for vehicle class."""
        return {
            'sedan': 0.20, 'suv': 0.25, 'truck': 0.30, 'motorcycle': 0.15
        }.get(vehicle_class, 0.20)


# =============================================================================
# TEST SCENARIOS
# =============================================================================

def create_test_scenarios():
    """Create a comprehensive set of realistic test scenarios."""
    scenarios = []
    
    # Scenario 1: Typical frontal crash
    scenarios.append(CrashScenario(
        speed_kmh=50, impact_angle_deg=0, overlap_percent=100,
        barrier_type='rigid', vehicle_class='sedan', vehicle_mass_kg=1400,
        sensor_mounting='floor_structural', sensor_name='mpu6050',
        temperature_c=25, road_roughness=0.3, engine_rpm=2000
    ))
    
    # Scenario 2: Low-speed rear-end
    scenarios.append(CrashScenario(
        speed_kmh=20, impact_angle_deg=180, overlap_percent=80,
        barrier_type='deformable', vehicle_class='sedan', vehicle_mass_kg=1400,
        sensor_mounting='floor_structural', sensor_name='mpu6050',
        temperature_c=20, road_roughness=0.2, engine_rpm=1500
    ))
    
    # Scenario 3: High-speed frontal
    scenarios.append(CrashScenario(
        speed_kmh=80, impact_angle_deg=5, overlap_percent=40,
        barrier_type='deformable', vehicle_class='sedan', vehicle_mass_kg=1400,
        sensor_mounting='floor_structural', sensor_name='h3lis331dl',
        temperature_c=35, road_roughness=0.1, engine_rpm=3000
    ))
    
    # Scenario 4: Side impact
    scenarios.append(CrashScenario(
        speed_kmh=50, impact_angle_deg=90, overlap_percent=50,
        barrier_type='pole', vehicle_class='sedan', vehicle_mass_kg=1400,
        sensor_mounting='floor_structural', sensor_name='mpu6050',
        temperature_c=25, road_roughness=0.2, engine_rpm=2500
    ))
    
    # Scenario 5: Truck crash
    scenarios.append(CrashScenario(
        speed_kmh=40, impact_angle_deg=0, overlap_percent=100,
        barrier_type='rigid', vehicle_class='truck', vehicle_mass_kg=8000,
        sensor_mounting='floor_structural', sensor_name='h3lis331dl',
        temperature_c=15, road_roughness=0.4, engine_rpm=1800
    ))
    
    return scenarios


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("VISTA 2.0 — REALISTIC CRASH SIMULATION CHAIN")
    print("=" * 70)
    
    sim = RealisticCrashSimulator()
    scenarios = create_test_scenarios()
    
    for i, scenario in enumerate(scenarios):
        print(f"\n--- Scenario {i+1}: {scenario.vehicle_class} at {scenario.speed_kmh} km/h ---")
        result = sim.simulate_crash(scenario)
        
        vr = result['vista_result']
        print(f"  True peak accel: {np.max(np.abs(result['true_crash_pulse']))/9.81:.1f} g")
        print(f"  Vehicle response: {np.max(np.abs(result['vehicle_response']))/9.81:.1f} g")
        print(f"  Sensor output: {np.max(np.abs(result['sensor_output']['accel']))/9.81:.1f} g")
        print(f"  VISTA detected: {vr['detected']}")
        print(f"  Confidence: {vr['confidence']:.3f}")
        print(f"  Delta-V: {vr['delta_v_kmh']:.1f} km/h")
        print(f"  CI: [{vr['ci_lower']:.1f}, {vr['ci_upper']:.1f}] km/h")
        print(f"  PDOF: {vr['pdof_degrees']:.1f} deg")
    
    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE — VISTA tested against realistic crash physics")
    print("=" * 70)
