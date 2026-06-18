"""
VISTA 2.0 — PDTSA v2 Detection Algorithm
Physics-Derived Temporal Signature Analysis with Vehicle-Class Priors
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
from enum import Enum


class CrashDirection(Enum):
    FRONTAL = "frontal"
    REAR = "rear"
    LEFT_SIDE = "left_side"
    RIGHT_SIDE = "right_side"
    OFFSET = "offset"
    OBLIQUE = "oblique"


class VehicleClass(Enum):
    SEDAN = "sedan"
    SUV = "suv"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    UNKNOWN = "unknown"


# Vehicle-class jerk threshold priors (research-informed, unvalidated)
VEHICLE_CLASS_JERK_PRIORS = {
    VehicleClass.SEDAN: 200.0,
    VehicleClass.SUV: 180.0,
    VehicleClass.TRUCK: 100.0,
    VehicleClass.MOTORCYCLE: 300.0,
    VehicleClass.UNKNOWN: 200.0,
}


@dataclass
class PDTSAConfig:
    jerk_threshold: float = 200.0
    accel_gate_g: float = 3.0  # Minimum acceleration before jerk check
    sustain_min_ms: float = 30.0
    asymmetry_soft_gate: float = 0.8
    confidence_threshold: float = 0.65
    weight_jerk: float = 0.4
    weight_asymmetry: float = 0.3
    weight_sustain: float = 0.3
    obd_bonus_max: float = 0.10
    audio_bonus_max: float = 0.25
    vehicle_class: VehicleClass = VehicleClass.UNKNOWN
    bootstrap_n: int = 2000
    bootstrap_seed: int = 42
    # Saturation override parameters
    saturation_threshold_g: float = 15.5  # MPU6050 clips at ±16g
    saturation_min_ms: float = 30.0       # Minimum saturation duration for override
    saturation_override_enabled: bool = True  # Enable/disable saturation detection path


@dataclass
class PDTSAFeatures:
    jerk_magnitude: float
    sustain_duration_ms: float
    asymmetry_ratio: float
    asymmetry_score: float
    confidence: float
    detected: bool
    detection_time_ms: float
    peak_accel_g: float


@dataclass
class DeltaVResult:
    delta_v_ms: float
    delta_v_kmh: float
    ci_lower: float
    ci_upper: float
    saturated: bool
    saturation_fraction: float
    pdof_degrees: float
    pulse_duration_ms: float
    features: PDTSAFeatures


class PDTSAv2:
    """Physics-Derived Temporal Signature Analysis v2.
    Vehicle-class-aware crash detection with PDOF estimation.
    """

    def __init__(self, config=None):
        self.config = config or PDTSAConfig()
        jerk_priors = {
            VehicleClass.SEDAN: 200.0, VehicleClass.SUV: 180.0,
            VehicleClass.TRUCK: 100.0, VehicleClass.MOTORCYCLE: 300.0,
            VehicleClass.UNKNOWN: 200.0,
        }
        self.config.jerk_threshold = jerk_priors.get(self.config.vehicle_class, 200.0)

    def detect(self, accel_ms2, timestamps_s, pitch_rad=0.0):
        """Run full PDTSA pipeline on acceleration waveform.
        
        Two parallel detection paths:
          1. Jerk-based detection (original): analyzes rate-of-change signatures
          2. Saturation override (new): when sensor clips >15.5g for >30ms,
             this is itself evidence of a crash (failure mode as signal)
        
        If EITHER path detects, the event is classified as a crash.
        """
        dt = np.diff(timestamps_s)
        dt_avg = np.mean(dt) if len(dt) > 0 else 0.001

        # --- Pre-check: Acceleration gate ---
        # Minimum acceleration must exceed gate before any analysis
        accel_magnitude = np.sqrt(np.sum(accel_ms2**2, axis=1))
        peak_accel_g = np.max(accel_magnitude) / 9.81
        if peak_accel_g < self.config.accel_gate_g:
            return self._empty_result(timestamps_s, pitch_rad)

        # =============================================================
        # PATH 2: SATURATION OVERRIDE (runs in parallel with jerk path)
        # "Failure mode as signal" — when the sensor clips, the crash
        # was so severe that the clipping itself is evidence.
        # =============================================================
        saturation_detected = False
        saturation_duration_ms = 0.0
        saturation_confidence = 0.0
        sat_start_idx = 0
        sat_end_idx = 0

        if self.config.saturation_override_enabled:
            sat_mask = accel_magnitude / 9.81 > self.config.saturation_threshold_g
            sat_indices = np.where(sat_mask)[0]

            if len(sat_indices) > 0:
                # Find contiguous saturation blocks
                gaps = np.diff(sat_indices)
                block_starts = [sat_indices[0]]
                block_ends = []

                for i, gap in enumerate(gaps):
                    if gap > 1:  # Gap between saturation blocks
                        block_ends.append(sat_indices[i])
                        block_starts.append(sat_indices[i + 1])
                block_ends.append(sat_indices[-1])

                # Find the longest contiguous saturation block
                max_block_len = 0
                max_block_start = block_starts[0]
                max_block_end = block_ends[0]
                for bs, be in zip(block_starts, block_ends):
                    block_len = be - bs + 1
                    if block_len > max_block_len:
                        max_block_len = block_len
                        max_block_start = bs
                        max_block_end = be

                saturation_duration_ms = max_block_len * dt_avg * 1000

                if saturation_duration_ms >= self.config.saturation_min_ms:
                    saturation_detected = True
                    sat_start_idx = max_block_start
                    sat_end_idx = max_block_end
                    # Confidence based on how far above threshold and duration
                    excess_ratio = peak_accel_g / self.config.saturation_threshold_g
                    duration_ratio = saturation_duration_ms / self.config.saturation_min_ms
                    saturation_confidence = min(1.0, 0.5 * min(excess_ratio - 1.0, 1.0) +
                                                0.5 * min(duration_ratio - 1.0, 1.0))
                    saturation_confidence = max(0.65, saturation_confidence)  # Floor at threshold

        # =============================================================
        # PATH 1: JERK-BASED DETECTION (original algorithm)
        # =============================================================

        # --- Tier 1: Jerk detection ---
        accel_diff = np.diff(accel_ms2, axis=0)
        jerk = accel_diff / max(dt_avg, 1e-6)
        jerk_mag = np.sqrt(np.sum(jerk**2, axis=1))
        jerk_exceed = jerk_mag >= self.config.jerk_threshold

        # --- Tier 2: Sustain duration ---
        exceed_indices = np.where(jerk_exceed)[0]
        jerk_sustain_ms = 0.0
        jerk_detected = False
        crash_start = 0
        crash_end = 0

        if len(exceed_indices) > 0:
            jerk_sustain_ms = len(exceed_indices) * dt_avg * 1000
            jerk_detected = jerk_sustain_ms >= self.config.sustain_min_ms
            crash_start = exceed_indices[0]
            crash_end = exceed_indices[-1]

        # =============================================================
        # COMBINE BOTH PATHS: OR logic
        # =============================================================
        detected = jerk_detected or saturation_detected

        if not detected:
            return self._empty_result(timestamps_s, pitch_rad)

        # Use the wider window from both detection paths
        if jerk_detected and saturation_detected:
            crash_start = min(crash_start, sat_start_idx)
            crash_end = max(crash_end, sat_end_idx)
        elif saturation_detected:
            crash_start = sat_start_idx
            crash_end = sat_end_idx

        sustain_ms = max(jerk_sustain_ms, saturation_duration_ms)

        # --- Tier 3: Asymmetry (only if jerk path contributed) ---
        if jerk_detected:
            pulse = accel_magnitude[crash_start:crash_end+1]
            peak_idx = np.argmax(pulse)
            rise_samples = max(peak_idx, 1)
            decay_samples = max(len(pulse) - peak_idx - 1, 1)
            ra = decay_samples / rise_samples
            sa = min(1.0, ra / 2.0)
        else:
            # Saturation-only path: assume symmetric pulse
            sa = 0.5
            ra = 1.0

        # --- Tier 4: Confidence scoring ---
        if jerk_detected:
            sj = min(1.0, jerk_mag[exceed_indices[0]] / (self.config.jerk_threshold * 2))
            ss = min(1.0, jerk_sustain_ms / (self.config.sustain_min_ms * 2))
            jerk_confidence = (self.config.weight_jerk * sj +
                              self.config.weight_asymmetry * sa +
                              self.config.weight_sustain * ss)
        else:
            jerk_confidence = 0.0

        # Final confidence: max of both paths (OR logic)
        obd_bonus = 0.0
        audio_bonus = 0.0
        confidence = max(jerk_confidence, saturation_confidence) + obd_bonus + audio_bonus

        peak_g = np.max(accel_magnitude) / 9.81
        features = PDTSAFeatures(
            jerk_magnitude=float(jerk_mag[exceed_indices[0]]) if len(exceed_indices) > 0 else 0.0,
            sustain_duration_ms=float(sustain_ms),
            asymmetry_ratio=float(ra),
            asymmetry_score=float(sa),
            confidence=float(confidence),
            detected=detected,
            detection_time_ms=float(timestamps_s[crash_start] * 1000),
            peak_accel_g=float(peak_g),
        )

        if not detected:
            return DeltaVResult(
                delta_v_ms=0.0, delta_v_kmh=0.0,
                ci_lower=0.0, ci_upper=0.0, saturated=False,
                saturation_fraction=0.0, pdof_degrees=0.0,
                pulse_duration_ms=float(sustain_ms), features=features
            )

        # --- Delta-V Reconstruction ---
        dt_v = np.diff(timestamps_s)
        ax_crash = accel_ms2[crash_start:crash_end+1, 0]
        ax_comp = ax_crash - 9.81 * np.sin(pitch_rad)
        delta_v_raw = np.trapz(ax_comp, dx=dt_avg)

        # Saturation check
        accel_g = accel_magnitude[crash_start:crash_end+1] / 9.81
        sat_mask = accel_g > 15.5
        sat_frac = np.sum(sat_mask) / max(len(sat_mask), 1)
        saturated = sat_frac > 0.05

        delta_v_ms = float(delta_v_raw)
        delta_v_kmh = delta_v_ms * 3.6

        # Bootstrap CI
        rng = np.random.RandomState(self.config.bootstrap_seed)
        boot_dvs = []
        for _ in range(self.config.bootstrap_n):
            idx = rng.randint(0, len(ax_comp), size=len(ax_comp))
            boot_dv = np.trapz(ax_comp[idx], dx=dt_avg)
            boot_dvs.append(boot_dv * 3.6)
        boot_dvs = np.array(boot_dvs)
        ci_lower = float(np.percentile(boot_dvs, 2.5))
        ci_upper = float(np.percentile(boot_dvs, 97.5))

        # PDOF estimation from velocity vector
        vy_crash = accel_ms2[crash_start:crash_end+1, 1]
        vx_crash = accel_ms2[crash_start:crash_end+1, 0]
        vx_int = np.trapz(vx_crash, dx=dt_avg)
        vy_int = np.trapz(vy_crash, dx=dt_avg)
        pdof = float(np.degrees(np.arctan2(vy_int, vx_int)))

        return DeltaVResult(
            delta_v_ms=delta_v_ms,
            delta_v_kmh=delta_v_kmh,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            saturated=saturated,
            saturation_fraction=float(sat_frac),
            pdof_degrees=pdof,
            pulse_duration_ms=float(sustain_ms),
            features=features,
        )

    def _empty_result(self, timestamps_s, pitch_rad):
        return DeltaVResult(
            delta_v_ms=0.0, delta_v_kmh=0.0, ci_lower=0.0, ci_upper=0.0,
            saturated=False, saturation_fraction=0.0, pdof_degrees=0.0,
            pulse_duration_ms=0.0,
            features=PDTSAFeatures(0.0, 0.0, 0.0, 0.0, 0.0, False, 0.0, 0.0)
        )


# =============================================================================
# TESTS
# =============================================================================

def test_sedan_frontal_50g():
    """Test: 50g frontal haversine pulse should be detected."""
    from vista_hil import HILSimulation
    sim = HILSimulation()
    result = sim.run_single_crash({
        'type': 'haversine', 'peak_g': 50, 'duration_ms': 80,
        'delta_v_kmh': 40, 'direction': 'frontal'
    })
    accel_ms2 = result.accel  # Already in m/s² from sensor simulator
    timestamps = result.timestamp

    pdtsa = PDTSAv2(PDTSAConfig(vehicle_class=VehicleClass.SEDAN))
    det = pdtsa.detect(accel_ms2, timestamps)
    assert det.features.detected, "50g frontal should be detected"
    print("PASS: 50g frontal detected")

def test_no_crash_normal_driving():
    """Test: Normal driving acceleration should NOT be detected."""
    t = np.linspace(0, 1, 1000)
    accel = np.zeros((1000, 3))
    accel[:, 0] = np.sin(2 * np.pi * 2 * t) * 0.5 * 9.81  # 0.5g oscillation
    accel[:, 2] = np.ones(1000) * 9.81  # gravity

    pdtsa = PDTSAv2()
    det = pdtsa.detect(accel, t)
    assert not det.features.detected, "Normal driving should not trigger"
    print("PASS: Normal driving not detected")

def test_low_speed_20g():
    """Test: 20g low-speed crash detection."""
    from vista_hil import HILSimulation
    sim = HILSimulation()
    result = sim.run_single_crash({
        'type': 'half_sine', 'peak_g': 20, 'duration_ms': 100,
        'delta_v_kmh': 15, 'direction': 'frontal'
    })
    accel_ms2 = result.accel  # Already in m/s² from sensor simulator
    timestamps = result.timestamp

    pdtsa = PDTSAv2()
    det = pdtsa.detect(accel_ms2, timestamps)
    assert det.features.detected, "20g half-sine should be detected"
    print(f"PASS: 20g detected, delta-V={det.delta_v_kmh:.1f} km/h")


if __name__ == "__main__":
    print("Running PDTSA v2 tests...")
    test_no_crash_normal_driving()
    test_sedan_frontal_50g()
    test_low_speed_20g()
    print("All tests passed!")
