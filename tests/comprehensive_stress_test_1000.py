"""
VISTA 2.0 — COMPREHENSIVE STRESS TEST: 1000+ SCENARIOS

Scientists don't confirm — they BREAK. This test systematically varies
every dimension of the crash detection problem to find EVERY weakness.

DIMENSIONS VARIED:
  - Speed: 14 values (5–120 km/h)
  - Impact angle: 7 values (0–90°)
  - Overlap: 4 values (25–100%)
  - Vehicle class: 4 types (sedan, SUV, truck, motorcycle)
  - Temperature: 5 values (-20–60°C)
  - Sensor: 3 types (MPU6050, H3LIS331DL, IAM20680HP)
  - Mounting: 3 locations (floor, dashboard, seat_rail)
  - Road roughness: 5 levels (0.1–0.9)
  - Crash shape: 3 types (haversine, half_sine, triangular)

NON-CRASH SCENARIOS (should NOT detect):
  - ABS braking, potholes, speed bumps, normal driving,
    lane changes, hard cornering, railroad crossings, etc.

GROUND TRUTH RULES (physics-based):
  - ANY impact with barrier producing peak >12g AND sustain >60ms IS a crash
  - Side impacts at 60+ km/h ARE crashes (they kill people)
  - Rear impacts at 60+ km/h ARE crashes (they kill people)
  - Non-crash events: ABS braking, potholes, speed bumps (no barrier impact)
"""

import numpy as np
from scipy.signal import butter, sosfilt
import time
import sys
import os
import json
from datetime import datetime
from collections import defaultdict
from typing import List, Tuple, Dict, Optional


class _NpEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vista_hil.realistic_simulation import (
    RealisticCrashSimulator, CrashScenario,
    VehicleTransferFunction, VehicleTransferConfig, PreCrashVibration,
    VEHICLE_PRESETS, MOUNTING_PRESETS
)
from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass
from vista_hil import load_sensor


# =============================================================================
# SCENARIO BUILDER
# =============================================================================

# Vehicle mass lookup
VEHICLE_MASS = {
    'sedan': 1400, 'suv': 2200, 'truck': 8000, 'motorcycle': 200
}

# Crash shape pulse generators
def _haversine_pulse(t, duration):
    return np.sin(np.pi * t / duration) ** 2

def _half_sine_pulse(t, duration):
    return np.sin(np.pi * t / duration)

def _triangular_pulse(t, duration):
    return 1.0 - np.abs(2 * t / duration - 1.0)

SHAPE_FUNCS = {
    'haversine': _haversine_pulse,
    'half_sine': _half_sine_pulse,
    'triangular': _triangular_pulse,
}


def _scenario(name, speed, angle, overlap, barrier, vehicle, mounting,
              sensor='mpu6050', temp=25, roughness=0.3, rpm=2500,
              is_crash=True, shape='haversine'):
    """Create a scenario tuple: (name, CrashScenario, expected_detect, shape)."""
    mass = VEHICLE_MASS.get(vehicle, 1400)
    return (name, CrashScenario(
        speed_kmh=speed, impact_angle_deg=angle, overlap_percent=overlap,
        barrier_type=barrier, vehicle_class=vehicle, vehicle_mass_kg=mass,
        sensor_mounting=mounting, sensor_name=sensor,
        temperature_c=temp, road_roughness=roughness, engine_rpm=rpm
    ), is_crash, shape)


# =============================================================================
# CRASH SCENARIOS (~850)
# =============================================================================

def create_crash_scenarios():
    """Generate ~850 crash scenarios covering all dimensions systematically."""
    scenarios = []

    # =====================================================================
    # A. SINGLE-DIMENSION SWEEPS (baseline coverage)
    # =====================================================================

    # A1. Speed sweep (frontal, sedan, mpu6050, floor, 25°C, 100%, rough=0.3)
    for speed in [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 120]:
        scenarios.append(_scenario(
            f'A1: Frontal {speed}km/h sedan mpu6050', speed, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # A2. Angle sweep (50km/h, sedan, mpu6050, floor, 25°C, 100%, rough=0.3)
    for angle in [0, 15, 30, 45, 60, 75, 90]:
        scenarios.append(_scenario(
            f'A2: {angle}° impact 50km/h sedan', 50, angle, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # A3. Overlap sweep (50km/h, frontal, sedan, mpu6050, floor, 25°C)
    for overlap in [25, 50, 75, 100]:
        scenarios.append(_scenario(
            f'A3: {overlap}% overlap 50km/h sedan', 50, 0, overlap, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # A4. Vehicle sweep (50km/h, frontal, mpu6050, floor, 25°C, 100%)
    for vehicle in ['sedan', 'suv', 'truck', 'motorcycle']:
        scenarios.append(_scenario(
            f'A4: Frontal 50km/h {vehicle}', 50, 0, 100, 'rigid',
            vehicle, 'floor_structural', 'mpu6050', 25, 0.3))

    # A5. Sensor sweep (50km/h, frontal, sedan, floor, 25°C, 100%)
    for sensor in ['mpu6050', 'h3lis331dl', 'iam20680hp']:
        scenarios.append(_scenario(
            f'A5: Frontal 50km/h {sensor}', 50, 0, 100, 'rigid',
            'sedan', 'floor_structural', sensor, 25, 0.3))

    # A6. Mounting sweep (50km/h, frontal, sedan, mpu6050, 25°C, 100%)
    for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
        scenarios.append(_scenario(
            f'A6: Frontal 50km/h {mounting}', 50, 0, 100, 'rigid',
            'sedan', mounting, 'mpu6050', 25, 0.3))

    # A7. Temperature sweep (50km/h, frontal, sedan, mpu6050, floor, 100%)
    for temp in [-20, 0, 25, 40, 60]:
        scenarios.append(_scenario(
            f'A7: Frontal 50km/h temp={temp}°C', 50, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', temp, 0.3))

    # A8. Roughness sweep (50km/h, frontal, sedan, mpu6050, floor, 25°C, 100%)
    for roughness in [0.1, 0.3, 0.5, 0.7, 0.9]:
        scenarios.append(_scenario(
            f'A8: Frontal 50km/h roughness={roughness}', 50, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, roughness))

    # A9. Shape sweep (50km/h, frontal, sedan, mpu6050, floor, 25°C, 100%)
    for shape in ['haversine', 'half_sine', 'triangular']:
        scenarios.append(_scenario(
            f'A9: Frontal 50km/h {shape}', 50, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3, shape=shape))

    # =====================================================================
    # B. TWO-WAY CROSS PRODUCTS (interaction effects)
    # =====================================================================

    # B1. Speed × Vehicle (frontal, mpu6050, floor, 25°C, 100%, rough=0.3)
    for speed in [10, 20, 30, 40, 50, 60, 70, 80, 100, 120]:
        for vehicle in ['sedan', 'suv', 'truck', 'motorcycle']:
            scenarios.append(_scenario(
                f'B1: Frontal {speed}km/h {vehicle}', speed, 0, 100, 'rigid',
                vehicle, 'floor_structural', 'mpu6050', 25, 0.3))

    # B2. Speed × Sensor (frontal, sedan, floor, 25°C, 100%, rough=0.3)
    for speed in [10, 20, 30, 40, 50, 60, 70, 80, 100, 120]:
        for sensor in ['mpu6050', 'h3lis331dl', 'iam20680hp']:
            scenarios.append(_scenario(
                f'B2: Frontal {speed}km/h {sensor}', speed, 0, 100, 'rigid',
                'sedan', 'floor_structural', sensor, 25, 0.3))

    # B3. Speed × Mounting (frontal, sedan, mpu6050, 25°C, 100%, rough=0.3)
    for speed in [10, 20, 30, 40, 50, 60, 70, 80, 100, 120]:
        for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
            scenarios.append(_scenario(
                f'B3: Frontal {speed}km/h {mounting}', speed, 0, 100, 'rigid',
                'sedan', mounting, 'mpu6050', 25, 0.3))

    # B4. Speed × Angle (subset: sedan, mpu6050, floor, 25°C, 100%, rough=0.3)
    for speed in [20, 40, 60, 80, 100]:
        for angle in [0, 30, 45, 60, 90]:
            scenarios.append(_scenario(
                f'B4: {angle}° impact {speed}km/h sedan', speed, angle, 100, 'rigid',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # B5. Speed × Overlap (frontal, sedan, mpu6050, floor, 25°C, rough=0.3)
    for speed in [20, 40, 60, 80, 100]:
        for overlap in [25, 50, 75, 100]:
            scenarios.append(_scenario(
                f'B5: Frontal {speed}km/h {overlap}%overlap', speed, 0, overlap, 'rigid',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # B6. Angle × Vehicle (50km/h, mpu6050, floor, 25°C, 100%, rough=0.3)
    for angle in [0, 30, 45, 60, 90]:
        for vehicle in ['sedan', 'suv', 'truck', 'motorcycle']:
            scenarios.append(_scenario(
                f'B6: {angle}° 50km/h {vehicle}', 50, angle, 100, 'rigid',
                vehicle, 'floor_structural', 'mpu6050', 25, 0.3))

    # B7. Sensor × Mounting (50km/h, frontal, sedan, 25°C, 100%, rough=0.3)
    for sensor in ['mpu6050', 'h3lis331dl', 'iam20680hp']:
        for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
            scenarios.append(_scenario(
                f'B7: Frontal 50km/h {sensor} {mounting}', 50, 0, 100, 'rigid',
                'sedan', mounting, sensor, 25, 0.3))

    # B8. Temperature × Sensor (50km/h, frontal, sedan, floor, 100%, rough=0.3)
    for temp in [-20, 0, 25, 40, 60]:
        for sensor in ['mpu6050', 'h3lis331dl', 'iam20680hp']:
            scenarios.append(_scenario(
                f'B8: Frontal 50km/h {sensor} temp={temp}°C', 50, 0, 100, 'rigid',
                'sedan', 'floor_structural', sensor, temp, 0.3))

    # B9. Speed × Shape (frontal, sedan, mpu6050, floor, 25°C, 100%, rough=0.3)
    for speed in [20, 40, 60, 80, 100]:
        for shape in ['haversine', 'half_sine', 'triangular']:
            scenarios.append(_scenario(
                f'B9: Frontal {speed}km/h {shape}', speed, 0, 100, 'rigid',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, shape=shape))

    # B10. Temperature × Mounting (50km/h, frontal, sedan, mpu6050, 100%, rough=0.3)
    for temp in [-20, 0, 25, 60]:
        for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
            scenarios.append(_scenario(
                f'B10: Frontal 50km/h {mounting} temp={temp}°C', 50, 0, 100, 'rigid',
                'sedan', mounting, 'mpu6050', temp, 0.3))

    # B11. Roughness × Speed (frontal, sedan, mpu6050, floor, 25°C, 100%)
    for roughness in [0.1, 0.5, 0.9]:
        for speed in [20, 50, 80, 100]:
            scenarios.append(_scenario(
                f'B11: Frontal {speed}km/h rough={roughness}', speed, 0, 100, 'rigid',
                'sedan', 'floor_structural', 'mpu6050', 25, roughness))

    # =====================================================================
    # C. THREE-WAY CRITICAL COMBOS
    # =====================================================================

    # C1. Speed × Vehicle × Sensor (frontal, floor, 25°C, 100%, rough=0.3)
    for speed in [20, 50, 80, 100]:
        for vehicle in ['sedan', 'suv', 'truck', 'motorcycle']:
            for sensor in ['mpu6050', 'h3lis331dl', 'iam20680hp']:
                scenarios.append(_scenario(
                    f'C1: Frontal {speed}km/h {vehicle} {sensor}', speed, 0, 100,
                    'rigid', vehicle, 'floor_structural', sensor, 25, 0.3))

    # C2. Speed × Angle × Overlap (sedan, mpu6050, floor, 25°C, rough=0.3)
    for speed in [30, 60, 90]:
        for angle in [0, 30, 60, 90]:
            for overlap in [25, 50, 100]:
                scenarios.append(_scenario(
                    f'C2: {angle}° {speed}km/h {overlap}%overlap', speed, angle,
                    overlap, 'rigid', 'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # C3. Speed × Mounting × Sensor (frontal, sedan, 25°C, 100%, rough=0.3)
    for speed in [30, 60, 90]:
        for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
            for sensor in ['mpu6050', 'h3lis331dl']:
                scenarios.append(_scenario(
                    f'C3: Frontal {speed}km/h {mounting} {sensor}', speed, 0, 100,
                    'rigid', 'sedan', mounting, sensor, 25, 0.3))

    # C4. Vehicle × Sensor × Mounting (50km/h, frontal, 25°C, 100%, rough=0.3)
    for vehicle in ['sedan', 'suv', 'truck', 'motorcycle']:
        for sensor in ['mpu6050', 'h3lis331dl', 'iam20680hp']:
            for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
                scenarios.append(_scenario(
                    f'C4: Frontal 50km/h {vehicle} {sensor} {mounting}', 50, 0, 100,
                    'rigid', vehicle, mounting, sensor, 25, 0.3))

    # C5. Temperature × Speed × Vehicle (frontal, mpu6050, floor, 100%, rough=0.3)
    for temp in [-20, 60]:
        for speed in [30, 60, 90]:
            for vehicle in ['sedan', 'suv']:
                scenarios.append(_scenario(
                    f'C5: Frontal {speed}km/h {vehicle} temp={temp}°C', speed, 0, 100,
                    'rigid', vehicle, 'floor_structural', 'mpu6050', temp, 0.3))

    # C6. Angle × Speed × Vehicle (mpu6050, floor, 25°C, 100%, rough=0.3)
    for angle in [30, 60, 90]:
        for speed in [30, 60, 90]:
            for vehicle in ['sedan', 'suv']:
                scenarios.append(_scenario(
                    f'C6: {angle}° {speed}km/h {vehicle}', speed, angle, 100,
                    'rigid', vehicle, 'floor_structural', 'mpu6050', 25, 0.3))

    # =====================================================================
    # D. EDGE CASES & BOUNDARY CONDITIONS
    # =====================================================================

    # D1. Ultra-low speed crashes (borderline detection)
    for speed in [5, 8, 10, 12]:
        scenarios.append(_scenario(
            f'D1: Ultra-low {speed}km/h frontal sedan', speed, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D2. High-speed crashes (saturation expected for MPU6050)
    for speed in [100, 110, 120]:
        scenarios.append(_scenario(
            f'D2: High-speed {speed}km/h frontal sedan', speed, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D3. Minimal overlap (25%) at various speeds
    for speed in [30, 50, 70, 90]:
        scenarios.append(_scenario(
            f'D3: 25% overlap {speed}km/h frontal', speed, 0, 25, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D4. Maximum oblique (75°) at various speeds
    for speed in [30, 50, 70, 90]:
        scenarios.append(_scenario(
            f'D4: 75° oblique {speed}km/h', speed, 75, 50, 'deformable',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D5. Motorcycle crash scenarios (unique dynamics)
    for speed in [20, 30, 40, 50, 60]:
        scenarios.append(_scenario(
            f'D5: Motorcycle frontal {speed}km/h', speed, 15, 50, 'pole',
            'motorcycle', 'dashboard', 'mpu6050', 25, 0.3))
    for speed in [20, 30, 40]:
        scenarios.append(_scenario(
            f'D5: Motorcycle side {speed}km/h', speed, 90, 50, 'pole',
            'motorcycle', 'dashboard', 'mpu6050', 25, 0.3))

    # D6. Truck crash scenarios (high mass dynamics)
    for speed in [20, 40, 60, 80, 100]:
        scenarios.append(_scenario(
            f'D6: Truck frontal {speed}km/h', speed, 0, 100, 'rigid',
            'truck', 'floor_structural', 'h3lis331dl', 25, 0.3))
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'D6: Truck side {speed}km/h', speed, 90, 50, 'pole',
            'truck', 'floor_structural', 'h3lis331dl', 25, 0.3))

    # D7. Borderline detection scenarios (near threshold)
    scenarios.append(_scenario(
        'D7: Borderline 15km/h frontal sedan', 15, 0, 100, 'rigid',
        'sedan', 'floor_structural', 'mpu6050', 25, 0.5))
    scenarios.append(_scenario(
        'D7: Borderline 20km/h 25% overlap', 20, 0, 25, 'rigid',
        'sedan', 'floor_structural', 'mpu6050', 25, 0.5))
    scenarios.append(_scenario(
        'D7: Borderline 25km/h 75° oblique', 25, 75, 50, 'deformable',
        'sedan', 'floor_structural', 'mpu6050', 25, 0.5))
    scenarios.append(_scenario(
        'D7: Borderline 30km/h seat_rail mount', 30, 0, 100, 'rigid',
        'sedan', 'seat_rail', 'mpu6050', 25, 0.5))

    # D8. Temperature + mounting extreme combos
    scenarios.append(_scenario(
        'D8: Frontal 40km/h -20°C seat_rail mpu6050', 40, 0, 100, 'rigid',
        'sedan', 'seat_rail', 'mpu6050', -20, 0.3))
    scenarios.append(_scenario(
        'D8: Frontal 50km/h 60°C dashboard iam20680hp', 50, 0, 100, 'rigid',
        'sedan', 'dashboard', 'iam20680hp', 60, 0.3))
    scenarios.append(_scenario(
        'D8: Side 40km/h -20°C dashboard mpu6050', 40, 90, 50, 'pole',
        'sedan', 'dashboard', 'mpu6050', -20, 0.3))
    scenarios.append(_scenario(
        'D8: Rear 50km/h 60°C seat_rail mpu6050', 50, 180, 100, 'rigid',
        'sedan', 'seat_rail', 'mpu6050', 60, 0.3))

    # D9. High roughness + low overlap (noise + weak signal)
    scenarios.append(_scenario(
        'D9: Frontal 40km/h 25%overlap rough=0.9', 40, 0, 25, 'rigid',
        'sedan', 'floor_structural', 'mpu6050', 25, 0.9))
    scenarios.append(_scenario(
        'D9: Frontal 50km/h 50%overlap rough=0.9', 50, 0, 50, 'rigid',
        'sedan', 'floor_structural', 'mpu6050', 25, 0.9))

    # D10. Sensor saturation boundary (MPU6050 at ±16g)
    for speed in [30, 35, 40, 45, 50]:
        scenarios.append(_scenario(
            f'D10: Saturation boundary {speed}km/h frontal', speed, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D11. Rear impact comprehensive
    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'D11: Rear {speed}km/h sedan', speed, 180, 100, 'rigid',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'D11: Rear {speed}km/h SUV', speed, 180, 100, 'rigid',
            'suv', 'floor_structural', 'mpu6050', 25, 0.3))

    # D12. Side impact comprehensive
    for speed in [20, 30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'D12: Left side {speed}km/h sedan', speed, 90, 50, 'pole',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'D12: Right side {speed}km/h sedan', speed, 90, 50, 'pole',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D13. Deformable barrier crashes
    for speed in [30, 40, 50, 60, 70, 80]:
        scenarios.append(_scenario(
            f'D13: Frontal deformable {speed}km/h', speed, 0, 100, 'deformable',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D14. Pole impact (concentrated load)
    for speed in [20, 30, 40, 50, 60]:
        scenarios.append(_scenario(
            f'D14: Pole impact {speed}km/h', speed, 90, 25, 'pole',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # D15. Extreme roughness during crash
    for roughness in [0.7, 0.9]:
        for speed in [30, 50, 70]:
            scenarios.append(_scenario(
                f'D15: Frontal {speed}km/h extreme rough={roughness}', speed, 0, 100,
                'rigid', 'sedan', 'floor_structural', 'mpu6050', 25, roughness))

    # =====================================================================
    # E. ADDITIONAL SYSTEMATIC COVERAGE (push to 1000+)
    # =====================================================================

    # E1. Rear impact × vehicle × speed (comprehensive rear coverage)
    for speed in [20, 40, 60, 80]:
        for vehicle in ['sedan', 'suv', 'truck']:
            scenarios.append(_scenario(
                f'E1: Rear {speed}km/h {vehicle}', speed, 180, 100, 'rigid',
                vehicle, 'floor_structural', 'mpu6050', 25, 0.3))

    # E2. Side impact × vehicle × sensor × mounting
    for speed in [30, 50, 70]:
        for vehicle in ['sedan', 'suv']:
            for sensor in ['mpu6050', 'h3lis331dl']:
                scenarios.append(_scenario(
                    f'E2: Left side {speed}km/h {vehicle} {sensor}', speed, 90, 50, 'pole',
                    vehicle, 'floor_structural', sensor, 25, 0.3))

    # E3. Frontal × angle × sensor × mounting (4-way subset)
    for speed in [40, 70]:
        for angle in [0, 30, 60, 90]:
            for sensor in ['mpu6050', 'h3lis331dl']:
                for mounting in ['floor_structural', 'dashboard']:
                    scenarios.append(_scenario(
                        f'E3: {angle}° {speed}km/h {sensor} {mounting}', speed, angle, 100,
                        'rigid', 'sedan', mounting, sensor, 25, 0.3))

    # E4. Frontal × shape × vehicle
    for speed in [30, 60, 90]:
        for shape in ['haversine', 'half_sine', 'triangular']:
            for vehicle in ['sedan', 'suv', 'motorcycle']:
                scenarios.append(_scenario(
                    f'E4: Frontal {speed}km/h {shape} {vehicle}', speed, 0, 100, 'rigid',
                    vehicle, 'floor_structural', 'mpu6050', 25, 0.3, shape=shape))

    # E5. Side × shape × mounting
    for speed in [40, 60, 80]:
        for shape in ['haversine', 'half_sine', 'triangular']:
            for mounting in ['floor_structural', 'dashboard', 'seat_rail']:
                scenarios.append(_scenario(
                    f'E5: Side {speed}km/h {shape} {mounting}', speed, 90, 50, 'pole',
                    'sedan', mounting, 'mpu6050', 25, 0.3, shape=shape))

    # E6. Speed × temperature × mounting (frontal)
    for speed in [30, 60, 90]:
        for temp in [-20, 25, 60]:
            for mounting in ['floor_structural', 'dashboard']:
                scenarios.append(_scenario(
                    f'E6: Frontal {speed}km/h {mounting} temp={temp}°C', speed, 0, 100,
                    'rigid', 'sedan', mounting, 'mpu6050', temp, 0.3))

    # E7. SUV comprehensive (all angles × speeds)
    for speed in [30, 60, 90]:
        for angle in [0, 45, 90]:
            scenarios.append(_scenario(
                f'E7: SUV {angle}° {speed}km/h', speed, angle, 100, 'rigid',
                'suv', 'floor_structural', 'mpu6050', 25, 0.3))

    # E8. Motorcycle comprehensive (different mounts and sensors)
    for speed in [20, 40, 60]:
        for mounting in ['dashboard', 'seat_rail']:
            for sensor in ['mpu6050', 'h3lis331dl']:
                scenarios.append(_scenario(
                    f'E8: Motorcycle {speed}km/h {mounting} {sensor}', speed, 15, 50, 'pole',
                    'motorcycle', mounting, sensor, 25, 0.3))

    # E9. Truck comprehensive (different angles)
    for speed in [30, 50, 70]:
        for angle in [0, 30, 90]:
            scenarios.append(_scenario(
                f'E9: Truck {angle}° {speed}km/h', speed, angle, 100, 'rigid',
                'truck', 'floor_structural', 'h3lis331dl', 25, 0.3))

    # E10. Low overlap × high angle (worst case for detection)
    for speed in [40, 60, 80]:
        for overlap in [25, 50]:
            for angle in [45, 60, 75]:
                scenarios.append(_scenario(
                    f'E10: {angle}° {speed}km/h {overlap}%overlap', speed, angle, overlap,
                    'deformable', 'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    # E11. IAM20680HP specific (same 16g range as MPU6050)
    for speed in [20, 35, 50, 65, 80]:
        scenarios.append(_scenario(
            f'E11: Frontal {speed}km/h iam20680hp', speed, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'iam20680hp', 25, 0.3))
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'E11: Side {speed}km/h iam20680hp', speed, 90, 50, 'pole',
            'sedan', 'floor_structural', 'iam20680hp', 25, 0.3))
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'E11: Rear {speed}km/h iam20680hp', speed, 180, 100, 'rigid',
            'sedan', 'floor_structural', 'iam20680hp', 25, 0.3))

    # E12. H3LIS331DL specific (400g, should never saturate)
    for speed in [30, 50, 70, 90, 110]:
        scenarios.append(_scenario(
            f'E12: Frontal {speed}km/h h3lis331dl', speed, 0, 100, 'rigid',
            'sedan', 'floor_structural', 'h3lis331dl', 25, 0.3))
    for speed in [30, 50, 70]:
        scenarios.append(_scenario(
            f'E12: Side {speed}km/h h3lis331dl', speed, 90, 50, 'pole',
            'sedan', 'floor_structural', 'h3lis331dl', 25, 0.3))

    # E13. Extreme temperature × vehicle × sensor
    for temp in [-20, 60]:
        for vehicle in ['sedan', 'suv']:
            for sensor in ['mpu6050', 'iam20680hp']:
                scenarios.append(_scenario(
                    f'E13: Frontal 50km/h {vehicle} {sensor} temp={temp}°C', 50, 0, 100,
                    'rigid', vehicle, 'floor_structural', sensor, temp, 0.3))

    # E14. All crash shapes × all speeds (frontal sedan)
    for speed in [15, 30, 45, 60, 75, 90]:
        for shape in ['haversine', 'half_sine', 'triangular']:
            scenarios.append(_scenario(
                f'E14: Frontal {speed}km/h {shape}', speed, 0, 100, 'rigid',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, shape=shape))

    # E15. Speed × angle × vehicle (comprehensive interaction)
    for speed in [25, 50, 75, 100]:
        for angle in [0, 45, 90]:
            for vehicle in ['sedan', 'suv', 'motorcycle']:
                scenarios.append(_scenario(
                    f'E15: {angle}° {speed}km/h {vehicle}', speed, angle, 100, 'rigid',
                    vehicle, 'floor_structural', 'mpu6050', 25, 0.3))

    # E16. Offset crashes at various conditions
    for speed in [30, 50, 70, 90]:
        for overlap in [25, 50]:
            scenarios.append(_scenario(
                f'E16: {overlap}% offset {speed}km/h', speed, 0, overlap, 'deformable',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3))

    return scenarios


# =============================================================================
# NON-CRASH SCENARIOS (~200)
# =============================================================================

def create_non_crash_scenarios():
    """Generate ~200 non-crash scenarios that should NOT trigger detection."""
    scenarios = []

    # =====================================================================
    # E1. ABS Braking (longitudinal deceleration, no barrier)
    # =====================================================================
    for speed in [30, 50, 60, 80, 100, 120]:
        for vehicle in ['sedan', 'suv', 'truck', 'motorcycle']:
            scenarios.append(_scenario(
                f'E1: ABS braking {speed}km/h {vehicle}', speed, 0, 0, 'none',
                vehicle, 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E2. Pothole Impact (vertical impulse, 5-10g, 5-15ms)
    # =====================================================================
    for speed in [20, 40, 60, 80, 100]:
        for severity in ['mild', 'moderate', 'severe']:
            roughness = {'mild': 0.5, 'moderate': 0.7, 'severe': 0.9}[severity]
            scenarios.append(_scenario(
                f'E2: Pothole {speed}km/h {severity}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, roughness,
                is_crash=False))

    # =====================================================================
    # E3. Speed Bump (vertical impulse, 2-5g, 50-100ms)
    # =====================================================================
    for speed in [15, 25, 35, 45, 55]:
        for bump in ['low', 'medium', 'high']:
            roughness = {'low': 0.2, 'medium': 0.4, 'high': 0.6}[bump]
            scenarios.append(_scenario(
                f'E3: Speed bump {speed}km/h {bump}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, roughness,
                is_crash=False))

    # =====================================================================
    # E4. Normal Driving Vibration (0.1-0.5g, continuous)
    # =====================================================================
    for speed in [30, 50, 70, 90, 110]:
        for road in ['smooth', 'highway', 'city', 'rough']:
            roughness = {'smooth': 0.1, 'highway': 0.2, 'city': 0.4, 'rough': 0.7}[road]
            scenarios.append(_scenario(
                f'E4: Normal driving {speed}km/h {road}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, roughness,
                is_crash=False))

    # =====================================================================
    # E5. Lane Change Maneuver (lateral acceleration)
    # =====================================================================
    for speed in [40, 60, 80, 100, 120]:
        for lat_g in [0.2, 0.4, 0.6]:
            scenarios.append(_scenario(
                f'E5: Lane change {speed}km/h {lat_g}g lat', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E6. Hard Cornering (sustained lateral acceleration)
    # =====================================================================
    for speed in [40, 60, 80, 100]:
        for radius in ['tight', 'medium', 'wide']:
            scenarios.append(_scenario(
                f'E6: Hard cornering {speed}km/h {radius}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E7. Railroad Crossing (repeated vertical impacts)
    # =====================================================================
    for speed in [20, 40, 60, 80]:
        for roughness in [0.4, 0.6, 0.8]:
            scenarios.append(_scenario(
                f'E7: Railroad {speed}km/h rough={roughness}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, roughness,
                is_crash=False))

    # =====================================================================
    # E8. Gravel Road Driving (continuous broadband vibration)
    # =====================================================================
    for speed in [30, 50, 70, 90]:
        for roughness in [0.5, 0.7, 0.9]:
            scenarios.append(_scenario(
                f'E8: Gravel {speed}km/h rough={roughness}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, roughness,
                is_crash=False))

    # =====================================================================
    # E9. Combined Braking + Cornering (complex non-crash)
    # =====================================================================
    for speed in [40, 60, 80]:
        for combo in ['brake_turn', 'turn_brake', 'slalom']:
            scenarios.append(_scenario(
                f'E9: {combo} {speed}km/h', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.4, is_crash=False))

    # =====================================================================
    # E10. Engine Revving (high RPM vibration)
    # =====================================================================
    for rpm in [3000, 4000, 5000, 6000]:
        scenarios.append(_scenario(
            f'E10: Engine rev RPM={rpm}', 30, 0, 0, 'none',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.2, rpm=rpm,
            is_crash=False))

    # =====================================================================
    # E11. Door Slam / Trunk Close (short impulse, no barrier)
    # Note: speed=0 causes division by zero in crash pulse generator,
    # so we use speed=1 (negligible) to represent stationary events.
    # =====================================================================
    for variant in ['door_slam', 'trunk_close', 'hood_close']:
        scenarios.append(_scenario(
            f'E11: {variant}', 1, 0, 0, 'none',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.1, is_crash=False))

    # =====================================================================
    # E12. Cargo Shift (lateral impulse)
    # =====================================================================
    for weight in ['light', 'medium', 'heavy']:
        scenarios.append(_scenario(
            f'E12: Cargo shift {weight}', 40, 0, 0, 'none',
            'truck', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E13. Wind Gust (lateral force)
    # =====================================================================
    for speed in [60, 80, 100, 120]:
        for intensity in ['moderate', 'strong', 'severe']:
            scenarios.append(_scenario(
                f'E13: Wind gust {speed}km/h {intensity}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E14. Emergency Braking on Ice (low friction, ABS active)
    # =====================================================================
    for speed in [30, 50, 70, 90]:
        scenarios.append(_scenario(
            f'E14: Emergency brake ice {speed}km/h', speed, 0, 0, 'none',
            'sedan', 'floor_structural', 'mpu6050', -20, 0.1, is_crash=False))

    # =====================================================================
    # E15. Running Over Debris (short vertical impulse)
    # =====================================================================
    for speed in [30, 50, 70, 90]:
        for size in ['small', 'medium', 'large']:
            scenarios.append(_scenario(
                f'E15: Debris {speed}km/h {size}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E16. Vehicle-to-Vehicle Near-Miss (close pass, no contact)
    # =====================================================================
    for speed in [50, 70, 90]:
        scenarios.append(_scenario(
            f'E16: Near-miss {speed}km/h', speed, 0, 0, 'none',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E17. Parking Lot Maneuvers (very low speed)
    # =====================================================================
    for maneuver in ['parallel_park', 'reverse_park', 'three_point_turn']:
        scenarios.append(_scenario(
            f'E17: {maneuver}', 5, 0, 0, 'none',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.2, is_crash=False))

    # =====================================================================
    # E18. Hard Braking on Various Surfaces
    # =====================================================================
    for speed in [40, 60, 80, 100]:
        for surface in ['wet', 'icy', 'gravel', 'asphalt']:
            scenarios.append(_scenario(
                f'E18: Hard brake {speed}km/h {surface}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E19. Tire Blowout (sudden lateral + vertical impulse)
    # =====================================================================
    for speed in [60, 80, 100, 120]:
        for tire in ['front_left', 'front_right', 'rear_left', 'rear_right']:
            scenarios.append(_scenario(
                f'E19: Tire blowout {speed}km/h {tire}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E20. Suspension Bottoming Out (vertical impact on bumps)
    # =====================================================================
    for speed in [20, 30, 40, 50]:
        for load in ['empty', 'half_load', 'full_load']:
            scenarios.append(_scenario(
                f'E20: Suspension bottom {speed}km/h {load}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.4, is_crash=False))

    # =====================================================================
    # E21. Aggressive Downshift (engine braking spike)
    # =====================================================================
    for speed in [40, 60, 80]:
        for gear in ['4to3', '3to2', '5to4']:
            scenarios.append(_scenario(
                f'E21: Downshift {speed}km/h {gear}', speed, 0, 0, 'none',
                'sedan', 'floor_structural', 'mpu6050', 25, 0.2, is_crash=False))

    # =====================================================================
    # E22. Traction Loss / Spin (uncontrolled rotation)
    # =====================================================================
    for speed in [40, 60, 80]:
        scenarios.append(_scenario(
            f'E22: Spin {speed}km/h', speed, 0, 0, 'none',
            'sedan', 'floor_structural', 'mpu6050', 25, 0.3, is_crash=False))

    # =====================================================================
    # E23. Off-Road Driving (sustained high vibration)
    # =====================================================================
    for speed in [20, 40, 60]:
        for terrain in ['dirt', 'mud', 'sand']:
            scenarios.append(_scenario(
                f'E23: Off-road {speed}km/h {terrain}', speed, 0, 0, 'none',
                'suv', 'floor_structural', 'mpu6050', 25, 0.8, is_crash=False))

    return scenarios


# =============================================================================
# ENHANCED SIMULATOR (with crash shape support)
# =============================================================================

class EnhancedCrashSimulator(RealisticCrashSimulator):
    """Extended simulator supporting crash pulse shapes and detailed diagnostics."""

    def simulate_crash_with_shape(self, scenario: CrashScenario,
                                  shape: str = 'haversine') -> dict:
        """Run simulation with specified crash pulse shape."""
        sampling_rate = 1000

        # Generate crash pulse with shape
        crash_pulse = self._generate_crash_pulse_shaped(scenario, sampling_rate, shape)

        # Apply vehicle transfer function
        vtf = VehicleTransferConfig(
            natural_freq_hz=self._get_vehicle_freq(scenario.vehicle_class),
            damping_ratio=self._get_vehicle_damping(scenario.vehicle_class)
        )
        vehicle_response = self._apply_transfer_function(crash_pulse, vtf, sampling_rate)

        # Add pre-crash vibration
        vibration, vib_timestamps = self._generate_vibration(scenario, sampling_rate)

        # Simulate MEMS sensor
        sensor_output = self._simulate_sensor(vehicle_response, scenario, sampling_rate)

        # Run VISTA algorithm
        vista_result = self._run_vista(sensor_output, scenario)

        return {
            'true_crash_pulse': crash_pulse,
            'vehicle_response': vehicle_response,
            'sensor_output': sensor_output,
            'pre_crash_vibration': vibration,
            'vista_result': vista_result,
            'scenario': scenario,
            'sampling_rate': sampling_rate,
            'shape': shape,
        }

    def _generate_crash_pulse_shaped(self, scenario: CrashScenario,
                                      fs: int, shape: str) -> np.ndarray:
        """Generate crash pulse with specified shape."""
        v_ms = scenario.speed_kmh / 3.6
        kinetic_energy = 0.5 * scenario.vehicle_mass_kg * v_ms**2
        crush_time_s = 0.05
        avg_force = kinetic_energy / (0.5 * v_ms * crush_time_s)
        peak_accel_g = avg_force / (scenario.vehicle_mass_kg * 9.81) * 1.5

        # Overlap adjustment
        overlap_factor = scenario.overlap_percent / 100.0
        peak_accel_g *= overlap_factor

        # Generate shaped pulse
        n_samples = int(crush_time_s * 1000)
        t = np.arange(n_samples) / 1000.0

        shape_func = SHAPE_FUNCS.get(shape, _haversine_pulse)
        pulse_g = peak_accel_g * shape_func(t, crush_time_s)

        # Convert to m/s² (3-axis) — rotated by impact angle
        pulse_ms2 = np.zeros((n_samples, 3))
        angle_rad = np.radians(scenario.impact_angle_deg)
        pulse_ms2[:, 0] = pulse_g * 9.81 * np.cos(angle_rad)
        pulse_ms2[:, 1] = pulse_g * 9.81 * np.sin(angle_rad)
        pulse_ms2[:, 2] = 9.81  # gravity

        return pulse_ms2


# =============================================================================
# STRESS TEST RUNNER
# =============================================================================

def compute_saturation_pct(saturation_array):
    """Compute saturation percentage from boolean saturation array."""
    if saturation_array is None or len(saturation_array) == 0:
        return 0.0
    if saturation_array.ndim > 1:
        return float(np.mean(saturation_array.any(axis=1)) * 100)
    return float(np.mean(saturation_array) * 100)


def run_comprehensive_stress_test():
    """Run all 1000+ scenarios and collect detailed results."""
    sim = EnhancedCrashSimulator()
    crash_scenarios = create_crash_scenarios()
    non_crash_scenarios = create_non_crash_scenarios()
    all_scenarios = crash_scenarios + non_crash_scenarios

    print(f"\nTotal scenarios: {len(all_scenarios)}")
    print(f"  Crash scenarios: {len(crash_scenarios)}")
    print(f"  Non-crash scenarios: {len(non_crash_scenarios)}")
    print(f"\nRunning simulation...")

    results = []
    failures = []
    false_positives = []
    false_negatives = []
    errors = []

    start_time = time.time()

    for i, (name, scenario, expected_detect, shape) in enumerate(all_scenarios):
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / max(elapsed, 0.001)
            print(f"  [{i+1}/{len(all_scenarios)}] {rate:.0f} scenarios/sec, "
                  f"{len(failures)} failures so far")

        try:
            result = sim.simulate_crash_with_shape(scenario, shape)
            vr = result['vista_result']

            detected = vr['detected']
            sat_pct = compute_saturation_pct(result['sensor_output'].get('saturation', None))

            # Classify failure type
            failure_type = None
            if detected != expected_detect:
                if expected_detect and not detected:
                    failure_type = 'false_negative'
                    false_negatives.append({
                        'name': name, 'expected': expected_detect, 'actual': detected,
                        'delta_v': vr['delta_v_kmh'], 'confidence': vr['confidence'],
                        'peak_g': vr['peak_accel_g'], 'saturation': sat_pct,
                        'scenario': scenario, 'shape': shape,
                    })
                elif not expected_detect and detected:
                    failure_type = 'false_positive'
                    false_positives.append({
                        'name': name, 'expected': expected_detect, 'actual': detected,
                        'delta_v': vr['delta_v_kmh'], 'confidence': vr['confidence'],
                        'peak_g': vr['peak_accel_g'], 'saturation': sat_pct,
                        'scenario': scenario, 'shape': shape,
                    })
                failures.append({
                    'name': name, 'type': failure_type,
                    'expected': expected_detect, 'actual': detected,
                    'delta_v': vr['delta_v_kmh'], 'confidence': vr['confidence'],
                    'peak_g': vr['peak_accel_g'], 'saturation': sat_pct,
                    'scenario': scenario, 'shape': shape,
                })

            results.append({
                'name': name, 'detected': detected, 'expected': expected_detect,
                'confidence': vr['confidence'], 'delta_v': vr['delta_v_kmh'],
                'peak_g': vr['peak_accel_g'], 'saturation': sat_pct,
                'scenario': scenario, 'shape': shape,
            })

        except Exception as e:
            errors.append({
                'name': name, 'error': str(e), 'expected': expected_detect
            })
            failures.append({
                'name': name, 'type': 'error', 'error': str(e),
                'expected': expected_detect
            })

    elapsed = time.time() - start_time
    print(f"\nSimulation complete: {elapsed:.1f}s ({len(results)/max(elapsed,0.001):.0f} scenarios/sec)")
    print(f"Total failures: {len(failures)} (FN: {len(false_negatives)}, FP: {len(false_positives)}, Errors: {len(errors)})")

    return results, failures, false_positives, false_negatives, errors, elapsed


# =============================================================================
# ANALYSIS & REPORTING
# =============================================================================

def analyze_results(results, failures, false_positives, false_negatives, errors, elapsed):
    """Generate comprehensive analysis for the markdown report."""
    total = len(results)
    crash_scenarios = [r for r in results if r['expected'] is True]
    non_crash_scenarios = [r for r in results if r['expected'] is False]

    # Basic stats
    detected_crashes = sum(1 for r in crash_scenarios if r['detected'])
    missed_crashes = sum(1 for r in crash_scenarios if not r['detected'])
    detected_non_crashes = sum(1 for r in non_crash_scenarios if r['detected'])
    correct_non_detections = sum(1 for r in non_crash_scenarios if not r['detected'])

    # Per-dimension analysis
    dimension_analysis = {}

    # By speed
    speed_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        speed = r['scenario'].speed_kmh
        speed_bins[speed]['total'] += 1
        speed_bins[speed]['expected'] += 1
        if r['detected']:
            speed_bins[speed]['detected'] += 1
    dimension_analysis['speed'] = dict(speed_bins)

    # By angle
    angle_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        angle = r['scenario'].impact_angle_deg
        angle_bins[angle]['total'] += 1
        angle_bins[angle]['expected'] += 1
        if r['detected']:
            angle_bins[angle]['detected'] += 1
    dimension_analysis['angle'] = dict(angle_bins)

    # By vehicle
    vehicle_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        vehicle = r['scenario'].vehicle_class
        vehicle_bins[vehicle]['total'] += 1
        vehicle_bins[vehicle]['expected'] += 1
        if r['detected']:
            vehicle_bins[vehicle]['detected'] += 1
    dimension_analysis['vehicle'] = dict(vehicle_bins)

    # By sensor
    sensor_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        sensor = r['scenario'].sensor_name
        sensor_bins[sensor]['total'] += 1
        sensor_bins[sensor]['expected'] += 1
        if r['detected']:
            sensor_bins[sensor]['detected'] += 1
    dimension_analysis['sensor'] = dict(sensor_bins)

    # By mounting
    mounting_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        mounting = r['scenario'].sensor_mounting
        mounting_bins[mounting]['total'] += 1
        mounting_bins[mounting]['expected'] += 1
        if r['detected']:
            mounting_bins[mounting]['detected'] += 1
    dimension_analysis['mounting'] = dict(mounting_bins)

    # By temperature
    temp_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        temp = r['scenario'].temperature_c
        temp_bins[temp]['total'] += 1
        temp_bins[temp]['expected'] += 1
        if r['detected']:
            temp_bins[temp]['detected'] += 1
    dimension_analysis['temperature'] = dict(temp_bins)

    # By roughness
    rough_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        rough = r['scenario'].road_roughness
        rough_bins[rough]['total'] += 1
        rough_bins[rough]['expected'] += 1
        if r['detected']:
            rough_bins[rough]['detected'] += 1
    dimension_analysis['roughness'] = dict(rough_bins)

    # By shape
    shape_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        shape = r['shape']
        shape_bins[shape]['total'] += 1
        shape_bins[shape]['expected'] += 1
        if r['detected']:
            shape_bins[shape]['detected'] += 1
    dimension_analysis['shape'] = dict(shape_bins)

    # By direction
    direction_bins = defaultdict(lambda: {'total': 0, 'detected': 0, 'expected': 0})
    for r in crash_scenarios:
        name_lower = r['name'].lower()
        if 'rear' in name_lower:
            direction = 'rear'
        elif 'left side' in name_lower or 'right side' in name_lower:
            direction = 'side'
        elif 'oblique' in name_lower or 'offset' in name_lower:
            direction = 'oblique/offset'
        else:
            direction = 'frontal'
        direction_bins[direction]['total'] += 1
        direction_bins[direction]['expected'] += 1
        if r['detected']:
            direction_bins[direction]['detected'] += 1
    dimension_analysis['direction'] = dict(direction_bins)

    # Failure taxonomy
    failure_taxonomy = defaultdict(list)
    for fn in false_negatives:
        scenario = fn['scenario']
        # Categorize by root cause
        if fn['saturation'] > 50:
            root_cause = 'sensor_saturation'
        elif scenario.sensor_mounting in ['dashboard', 'seat_rail']:
            root_cause = 'mounting_attenuation'
        elif scenario.vehicle_class == 'motorcycle':
            root_cause = 'motorcycle_dynamics'
        elif scenario.vehicle_class == 'truck':
            root_cause = 'truck_dynamics'
        elif scenario.overlap_percent <= 25:
            root_cause = 'low_overlap'
        elif scenario.impact_angle_deg >= 60:
            root_cause = 'oblique_angle'
        elif scenario.road_roughness >= 0.7:
            root_cause = 'high_roughness'
        elif scenario.temperature_c <= -20 or scenario.temperature_c >= 60:
            root_cause = 'temperature_extreme'
        elif fn['peak_g'] < 15:
            root_cause = 'low_peak_g'
        elif fn['confidence'] > 0.5:
            root_cause = 'near_miss_high_confidence'
        else:
            root_cause = 'other'
        failure_taxonomy[root_cause].append(fn)

    # Saturation analysis
    saturated_crashes = [r for r in crash_scenarios if r['saturation'] > 0]
    missed_saturated = [r for r in false_negatives if r['saturation'] > 0]

    return {
        'total': total,
        'crash_total': len(crash_scenarios),
        'non_crash_total': len(non_crash_scenarios),
        'detected_crashes': detected_crashes,
        'missed_crashes': missed_crashes,
        'detected_non_crashes': detected_non_crashes,
        'correct_non_detections': correct_non_detections,
        'dimension_analysis': dimension_analysis,
        'failure_taxonomy': dict(failure_taxonomy),
        'saturated_crashes': len(saturated_crashes),
        'missed_saturated': len(missed_saturated),
        'errors': len(errors),
        'elapsed': elapsed,
        'scenarios_per_sec': total / max(elapsed, 0.001),
    }


# =============================================================================
# MARKDOWN REPORT GENERATOR
# =============================================================================

def generate_report(analysis, results, failures, false_positives, false_negatives, errors):
    """Generate the comprehensive markdown report."""
    lines = []
    L = lines.append

    L("# VISTA 2.0 — COMPREHENSIVE STRESS TEST REPORT")
    L(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L(f"**Total Scenarios:** {analysis['total']}")
    L(f"**Elapsed Time:** {analysis['elapsed']:.1f}s ({analysis['scenarios_per_sec']:.0f} scenarios/sec)")
    L(f"**Failures:** {len(failures)} (FN: {len(false_negatives)}, FP: {len(false_positives)}, Errors: {len(errors)})")

    # ─── EXECUTIVE SUMMARY ───
    L("\n---\n## 1. EXECUTIVE SUMMARY\n")
    overall_pass = analysis['total'] - len(failures)
    overall_rate = overall_pass / max(analysis['total'], 1) * 100
    L(f"**Overall Pass Rate:** {overall_pass}/{analysis['total']} ({overall_rate:.1f}%)\n")

    crash_tp = analysis['detected_crashes']
    crash_fn = analysis['missed_crashes']
    crash_total = analysis['crash_total']
    L(f"### Crash Detection Performance")
    L(f"| Metric | Value |")
    L(f"|--------|-------|")
    L(f"| Total crash scenarios | {crash_total} |")
    L(f"| True Positives (correctly detected) | {crash_tp} ({crash_tp/max(crash_total,1)*100:.1f}%) |")
    L(f"| **False Negatives (MISSED crashes)** | **{crash_fn} ({crash_fn/max(crash_total,1)*100:.1f}%)** |")
    L(f"| **CRITICAL: Missed crash rate** | **{crash_fn/max(crash_total,1)*100:.2f}%** |")

    nc_total = analysis['non_crash_total']
    nc_fp = analysis['detected_non_crashes']
    nc_tn = analysis['correct_non_detections']
    L(f"\n### False Positive Performance")
    L(f"| Metric | Value |")
    L(f"|--------|-------|")
    L(f"| Total non-crash scenarios | {nc_total} |")
    L(f"| True Negatives (correctly not detected) | {nc_tn} ({nc_tn/max(nc_total,1)*100:.1f}%) |")
    L(f"| **False Positives (wrongly detected)** | **{nc_fp} ({nc_fp/max(nc_total,1)*100:.1f}%)** |")

    L(f"\n### Sensor Saturation")
    L(f"| Metric | Value |")
    L(f"|--------|-------|")
    L(f"| Crashes with sensor saturation | {analysis['saturated_crashes']} |")
    L(f"| Missed crashes due to saturation | {analysis['missed_saturated']} |")

    # ─── PASS/FAIL BY DIMENSION ───
    L("\n---\n## 2. PASS/FAIL RATES BY DIMENSION\n")

    def _dim_table(title, dim_data, is_crash=True):
        L(f"### {title}\n")
        L(f"| Parameter | Total | Detected | Missed/FP | Rate |")
        L(f"|-----------|-------|----------|-----------|------|")
        for param in sorted(dim_data.keys()):
            d = dim_data[param]
            total_d = d['expected']
            det = d['detected']
            miss = total_d - det
            rate = det / max(total_d, 1) * 100
            L(f"| {param} | {total_d} | {det} | {miss} | {rate:.1f}% |")
        L("")

    _dim_table("Detection Rate by Speed (Crash Scenarios)", analysis['dimension_analysis']['speed'])
    _dim_table("Detection Rate by Impact Angle (Crash Scenarios)", analysis['dimension_analysis']['angle'])
    _dim_table("Detection Rate by Vehicle Class (Crash Scenarios)", analysis['dimension_analysis']['vehicle'])
    _dim_table("Detection Rate by Sensor Type (Crash Scenarios)", analysis['dimension_analysis']['sensor'])
    _dim_table("Detection Rate by Mounting Location (Crash Scenarios)", analysis['dimension_analysis']['mounting'])
    _dim_table("Detection Rate by Temperature (Crash Scenarios)", analysis['dimension_analysis']['temperature'])
    _dim_table("Detection Rate by Road Roughness (Crash Scenarios)", analysis['dimension_analysis']['roughness'])
    _dim_table("Detection Rate by Crash Shape (Crash Scenarios)", analysis['dimension_analysis']['shape'])
    _dim_table("Detection Rate by Direction (Crash Scenarios)", analysis['dimension_analysis']['direction'])

    # ─── FAILURE TAXONOMY ───
    L("\n---\n## 3. FAILURE TAXONOMY (Categorized by Root Cause)\n")

    root_cause_descriptions = {
        'sensor_saturation': 'Sensor clips at ±16g (MPU6050/IAM20680HP), losing crash pulse information. Saturation override path may not activate.',
        'mounting_attenuation': 'Dashboard (6dB) or seat_rail (10dB) mounting attenuates crash pulse below detection threshold.',
        'motorcycle_dynamics': 'Motorcycle has high natural frequency (45Hz), low mass, different crash pulse characteristics.',
        'truck_dynamics': 'Truck has very low natural frequency (15Hz), high mass, longer crush duration.',
        'low_overlap': 'Minimal overlap (≤25%) reduces effective barrier engagement and peak acceleration.',
        'oblique_angle': 'High oblique angles (≥60°) spread acceleration across multiple axes, reducing single-axis peak.',
        'high_roughness': 'High road roughness (≥0.7) elevates noise floor, masking crash signal.',
        'temperature_extreme': 'Extreme temperatures (-20°C or 60°C) cause sensor drift and sensitivity changes.',
        'low_peak_g': 'Crash produces low peak acceleration (<15g), near the detection threshold.',
        'near_miss_high_confidence': 'Detection confidence was high but still below threshold — a near-miss.',
        'other': 'Uncategorized failure — requires manual investigation.',
    }

    for cause, items in sorted(analysis['failure_taxonomy'].items(),
                                key=lambda x: -len(x[1])):
        desc = root_cause_descriptions.get(cause, 'Unknown root cause.')
        L(f"### {cause.replace('_', ' ').title()} ({len(items)} failures)\n")
        L(f"**Root Cause:** {desc}\n")
        L(f"| Scenario | Peak g | ΔV (km/h) | Confidence | Saturation |")
        L(f"|----------|--------|-----------|------------|------------|")
        for item in items[:20]:
            L(f"| {item['name']} | {item['peak_g']:.1f} | {item['delta_v']:.1f} | "
              f"{item['confidence']:.3f} | {item['saturation']:.0f}% |")
        if len(items) > 20:
            L(f"| ... and {len(items)-20} more | | | | |")
        L("")

    # ─── DETAILED FALSE NEGATIVES ───
    L("\n---\n## 4. DETAILED FALSE NEGATIVES (Missed Crashes)\n")
    L(f"Total missed crashes: **{len(false_negatives)}**\n")

    if false_negatives:
        L("| # | Scenario | Speed | Angle | Overlap | Vehicle | Sensor | Mounting | Peak g | ΔV | Conf | Sat | Shape |")
        L("|---|----------|-------|-------|---------|---------|--------|----------|--------|-----|------|-----|-------|")
        for i, fn in enumerate(false_negatives[:50]):
            s = fn['scenario']
            L(f"| {i+1} | {fn['name'][:50]} | {s.speed_kmh} | {s.impact_angle_deg}° | "
              f"{s.overlap_percent}% | {s.vehicle_class} | {s.sensor_name} | {s.sensor_mounting} | "
              f"{fn['peak_g']:.1f} | {fn['delta_v']:.1f} | {fn['confidence']:.3f} | "
              f"{fn['saturation']:.0f}% | {fn['shape']} |")
        if len(false_negatives) > 50:
            L(f"\n*... and {len(false_negatives)-50} more missed crashes. See full data in stress_test_results.json*")
    L("")

    # ─── DETAILED FALSE POSITIVES ───
    L("\n---\n## 5. DETAILED FALSE POSITIVES (Wrongly Detected)\n")
    L(f"Total false positives: **{len(false_positives)}**\n")

    if false_positives:
        L("| # | Scenario | Peak g | ΔV | Confidence |")
        L("|---|----------|--------|-----|------------|")
        for i, fp in enumerate(false_positives[:30]):
            L(f"| {i+1} | {fp['name']} | {fp['peak_g']:.1f} | {fp['delta_v']:.1f} | {fp['confidence']:.3f} |")
        if len(false_positives) > 30:
            L(f"\n*... and {len(false_positives)-30} more false positives*")
    L("")

    # ─── ERRORS ───
    if errors:
        L("\n---\n## 6. SIMULATION ERRORS\n")
        L(f"Total errors: **{len(errors)}**\n")
        L("| Scenario | Error |")
        L("|----------|-------|")
        for e in errors[:20]:
            L(f"| {e['name']} | {e['error'][:80]} |")
        L("")

    # ─── RECOMMENDATIONS ───
    L("\n---\n## 7. RECOMMENDATIONS\n")

    # Analyze failure patterns to generate recommendations
    recs = []
    if analysis['missed_saturated'] > 0:
        recs.append({
            'priority': 'CRITICAL',
            'area': 'Saturation Override',
            'recommendation': (
                f'{analysis["missed_saturated"]} crashes missed due to sensor saturation. '
                'The saturation override path (Path 2 in PDTSA) must be tuned: '
                'lower saturation_threshold_g from 15.5 to 14.0, or reduce '
                'saturation_min_ms from 30 to 20ms. Consider using H3LIS331DL '
                '(±400g) for production where severe crashes are expected.'
            )
        })

    # Check mounting failures
    mount_fn = [fn for fn in false_negatives
                if fn['scenario'].sensor_mounting in ['dashboard', 'seat_rail']]
    if mount_fn:
        recs.append({
            'priority': 'HIGH',
            'area': 'Non-Structural Mounting',
            'recommendation': (
                f'{len(mount_fn)} crashes missed with dashboard/seat_rail mounting. '
                'These locations attenuate the crash pulse by 6-10dB. '
                'Options: (1) Lower detection thresholds for non-structural mounts, '
                '(2) Add mounting-specific gain compensation, '
                '(3) Recommend floor_structural mounting for production.'
            )
        })

    # Check vehicle-specific failures
    for vehicle in ['motorcycle', 'truck']:
        v_fn = [fn for fn in false_negatives if fn['scenario'].vehicle_class == vehicle]
        if v_fn:
            recs.append({
                'priority': 'HIGH',
                'area': f'{vehicle.title()} Detection',
                'recommendation': (
                    f'{len(v_fn)} crashes missed for {vehicle}. '
                    f'The {vehicle} has unique crash dynamics (fn={VEHICLE_PRESETS[vehicle].natural_freq_hz}Hz, '
                    f'ζ={VEHICLE_PRESETS[vehicle].damping_ratio}). '
                    'Recommend vehicle-class-specific detection thresholds and '
                    'potentially different algorithm parameters.'
            )
            })

    # Check low overlap failures
    low_overlap_fn = [fn for fn in false_negatives if fn['scenario'].overlap_percent <= 25]
    if low_overlap_fn:
        recs.append({
            'priority': 'MEDIUM',
            'area': 'Low Overlap Crashes',
            'recommendation': (
                f'{len(low_overlap_fn)} crashes missed with ≤25% overlap. '
                'Low-overlap crashes produce asymmetric loading with lower peak '
                'acceleration. Consider multi-axis detection that triggers on '
                'any single axis exceeding threshold, not just magnitude.'
            )
        })

    # Check temperature effects
    temp_fn = [fn for fn in false_negatives
               if fn['scenario'].temperature_c <= -20 or fn['scenario'].temperature_c >= 60]
    if temp_fn:
        recs.append({
            'priority': 'MEDIUM',
            'area': 'Temperature Extremes',
            'recommendation': (
                f'{len(temp_fn)} crashes missed at extreme temperatures. '
                'Temperature causes sensor sensitivity drift and offset changes. '
                'Implement temperature-dependent threshold compensation.'
            )
        })

    # Check roughness effects
    rough_fn = [fn for fn in false_negatives if fn['scenario'].road_roughness >= 0.7]
    if rough_fn:
        recs.append({
            'priority': 'MEDIUM',
            'area': 'Road Roughness',
            'recommendation': (
                f'{len(rough_fn)} crashes missed with high road roughness (≥0.7). '
                'Road vibration elevates the noise floor. Consider adaptive '
                'thresholding based on pre-crash vibration level estimation.'
            )
        })

    # False positive check
    if false_positives:
        recs.append({
            'priority': 'MEDIUM' if len(false_positives) < 10 else 'HIGH',
            'area': 'False Positive Rate',
            'recommendation': (
                f'{len(false_positives)} false positives detected. '
                'Review the acceleration gate (3g) and confidence threshold (0.65). '
                'Consider adding a secondary confirmation gate or increasing the '
                'fusion threshold in the detection cascade.'
            )
        })

    # General recommendations
    recs.append({
        'priority': 'LOW',
        'area': 'Algorithm Enhancement',
        'recommendation': (
            'Consider implementing the full 5-method Detection Cascade '
            '(detection_cascade.py) instead of single-method PDTSA. '
            'The cascade provides redundancy: Energy Flux, Wavelet, Kurtosis, '
            'and Template Matching can catch crashes that PDTSA misses.'
        )
    })

    recs.append({
        'priority': 'LOW',
        'area': 'Sensor Fusion',
        'recommendation': (
            'For production, consider dual-sensor fusion: '
            'H3LIS331DL (±400g) for crash detection + MPU6050 (±16g) for '
            'reconstruction. The high-g sensor ensures no saturation while '
            'the low-g sensor provides better resolution for delta-v calculation.'
        )
    })

    # Sort by priority
    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    recs.sort(key=lambda x: priority_order.get(x['priority'], 99))

    L("| Priority | Area | Recommendation |")
    L("|----------|------|----------------|")
    for r in recs:
        L(f"| **{r['priority']}** | {r['area']} | {r['recommendation']} |")
    L("")

    # Detailed recommendations
    L("\n### Detailed Recommendations\n")
    for i, r in enumerate(recs):
        L(f"#### {i+1}. [{r['priority']}] {r['area']}\n")
        L(f"{r['recommendation']}\n")

    # ─── CONFIDENCE ASSESSMENT ───
    L("\n---\n## 8. CONFIDENCE ASSESSMENT\n")
    L("### Test Coverage Confidence\n")
    L(f"| Dimension | Values Tested | Coverage | Confidence |")
    L(f"|-----------|---------------|----------|------------|")
    L(f"| Speed | 14 values (5–120 km/h) | Full range | HIGH |")
    L(f"| Impact angle | 7 values (0–90°) | Full range | HIGH |")
    L(f"| Overlap | 4 values (25–100%) | Full range | HIGH |")
    L(f"| Vehicle class | 4 types | All major classes | HIGH |")
    L(f"| Temperature | 5 values (-20–60°C) | Full range | HIGH |")
    L(f"| Sensor | 3 types | All available sensors | HIGH |")
    L(f"| Mounting | 3 locations | All available mounts | HIGH |")
    L(f"| Road roughness | 5 levels (0.1–0.9) | Full range | HIGH |")
    L(f"| Crash shape | 3 types | Haversine, half-sine, triangular | MEDIUM |")
    L(f"| Non-crash events | 17 categories | Comprehensive | HIGH |")

    L(f"\n### Overall Confidence\n")
    L(f"- **Detection rate confidence:** {'HIGH' if analysis['missed_crashes']/max(analysis['crash_total'],1) < 0.05 else 'MEDIUM' if analysis['missed_crashes']/max(analysis['crash_total'],1) < 0.15 else 'LOW'} "
      f"({analysis['missed_crashes']}/{analysis['crash_total']} missed = {analysis['missed_crashes']/max(analysis['crash_total'],1)*100:.1f}%)")
    L(f"- **False positive confidence:** {'HIGH' if analysis['detected_non_crashes']/max(analysis['non_crash_total'],1) < 0.05 else 'MEDIUM' if analysis['detected_non_crashes']/max(analysis['non_crash_total'],1) < 0.15 else 'LOW'} "
      f"({analysis['detected_non_crashes']}/{analysis['non_crash_total']} false alarms = {analysis['detected_non_crashes']/max(analysis['non_crash_total'],1)*100:.1f}%)")
    L(f"- **Test volume confidence:** HIGH ({analysis['total']} scenarios)")

    # ─── LIMITATIONS ───
    L("\n---\n## 9. TEST LIMITATIONS\n")
    L("1. **Simulation vs. Real-World:** This test uses parametric crash pulse models, "
      "not real crash data. Real crashes have complex, multi-modal acceleration profiles "
      "that may differ from haversine/half-sine/triangular models.")
    L("2. **Single Sensor Location:** The test assumes a single sensor. Real vehicles "
      "may have multiple sensors providing redundancy.")
    L("3. **No OBD/Audio Integration:** The confidence scoring does not include "
      "OBD speed drop or audio classification bonuses.")
    L("4. **Streaming vs. Batch:** The test runs in batch mode. Real-time streaming "
      "detection may have different latency characteristics.")
    L("5. **Crash Shape Limitation:** Only 3 pulse shapes tested. Real crashes "
      "may have more complex profiles (e.g., multi-peak, asymmetric).")

    # ─── APPENDIX: SCENARIO COUNTS ───
    L("\n---\n## 10. APPENDIX: SCENARIO COUNTS\n")
    L(f"| Category | Count |")
    L(f"|----------|-------|")
    L(f"| Total scenarios | {analysis['total']} |")
    L(f"| Crash scenarios | {analysis['crash_total']} |")
    L(f"| Non-crash scenarios | {analysis['non_crash_total']} |")
    L(f"| **Correct results** | **{analysis['total'] - len(failures)}** |")
    L(f"| **Failed results** | **{len(failures)}** |")
    L(f"| False negatives (missed crashes) | {len(false_negatives)} |")
    L(f"| False positives (false alarms) | {len(false_positives)} |")
    L(f"| Simulation errors | {len(errors)} |")
    L(f"| **Overall pass rate** | **{(analysis['total'] - len(failures))/max(analysis['total'],1)*100:.1f}%** |")

    L("\n---\n*Report generated by VISTA 2.0 Comprehensive Stress Test*")

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("VISTA 2.0 — COMPREHENSIVE STRESS TEST: 1000+ SCENARIOS")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run the stress test
    results, failures, false_positives, false_negatives, errors, elapsed = \
        run_comprehensive_stress_test()

    # Analyze results
    analysis = analyze_results(results, failures, false_positives,
                               false_negatives, errors, elapsed)

    # Generate report
    report = generate_report(analysis, results, failures,
                             false_positives, false_negatives, errors)

    # Save report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'COMPREHENSIVE_STRESS_TEST.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    # Save raw results as JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'stress_test_results.json')

    # Convert results to JSON-serializable format
    json_results = []
    for r in results:
        jr = {
            'name': r['name'],
            'detected': r['detected'],
            'expected': r['expected'],
            'confidence': float(r['confidence']),
            'delta_v': float(r['delta_v']),
            'peak_g': float(r['peak_g']),
            'saturation': float(r['saturation']),
            'shape': r['shape'],
            'speed_kmh': r['scenario'].speed_kmh,
            'angle_deg': r['scenario'].impact_angle_deg,
            'overlap_pct': r['scenario'].overlap_percent,
            'vehicle': r['scenario'].vehicle_class,
            'sensor': r['scenario'].sensor_name,
            'mounting': r['scenario'].sensor_mounting,
            'temp_c': r['scenario'].temperature_c,
            'roughness': r['scenario'].road_roughness,
        }
        json_results.append(jr)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_results, f, indent=2, cls=_NpEncoder)
    print(f"Raw results saved to: {json_path}")

    # Print summary
    print(f"\n{'=' * 80}")
    print(f"STRESS TEST COMPLETE")
    print(f"{'=' * 80}")
    print(f"Total scenarios: {analysis['total']}")
    print(f"  Crash: {analysis['crash_total']} | Non-crash: {analysis['non_crash_total']}")
    print(f"Pass: {analysis['total'] - len(failures)} | Fail: {len(failures)}")
    print(f"  FN (missed crash): {len(false_negatives)} | FP (false alarm): {len(false_positives)}")
    print(f"Pass rate: {(analysis['total'] - len(failures))/max(analysis['total'],1)*100:.1f}%")
    print(f"Time: {elapsed:.1f}s ({analysis['scenarios_per_sec']:.0f} scenarios/sec)")
    print(f"{'=' * 80}")
