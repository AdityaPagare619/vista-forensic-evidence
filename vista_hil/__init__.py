"""
VISTA 2.0 Hardware-in-the-Loop Simulation Package

This package provides tools for simulating MEMS sensor behavior during
crash events, enabling Hardware-in-the-Loop testing of the VISTA 2.0
forensic crash evidence framework.

Components:
- MEMS Sensor Simulation Engine (mems_simulator.py)
- Crash Pulse Generator (crash_pulse.py)
- HIL Simulation Loop (hil_simulation.py)
- Hardware Interfaces (hardware_interface.py)

Usage:
    from vista_hil import HILSimulation, load_sensor
    
    # Load sensor
    sensor = load_sensor("mpu6050", sampling_rate=1000)
    
    # Run simulation
    hil = HILSimulation()
    result = hil.run_single_crash({
        'type': 'haversine',
        'peak_g': 50,
        'duration_ms': 100,
        'delta_v_kmh': 40,
        'direction': 'frontal'
    })
"""

__version__ = "2.0.0"
__author__ = "VISTA Research Team"

from vista_hil.mems_simulator import MEMSSensorSimulator, SensorConfig, load_sensor
from vista_hil.crash_pulse import CrashPulseGenerator, CrashPulseConfig
from vista_hil.hil_simulation import HILSimulation, HILConfig, SimulationResult

__all__ = [
    'MEMSSensorSimulator',
    'SensorConfig',
    'load_sensor',
    'CrashPulseGenerator',
    'CrashPulseConfig',
    'HILSimulation',
    'HILConfig',
    'SimulationResult',
]
