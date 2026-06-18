"""
VISTA 2.0 — Layer 3: 5-Method Detection Cascade
Multi-method crash detection with weighted fusion.

Architecture:
  3g acceleration gate → 5 parallel detectors → weighted fusion → crash declaration

Detectors:
  1. PDTSA Threshold  (jerk + sustain + asymmetry) — wraps pdtsa_v2.py
  2. Energy Flux      — d(½mv²)/dt rate-of-change monitor
  3. Wavelet Packet   — frequency-band energy discrimination
  4. Kurtosis         — statistical peakiness of jerk signal
  5. Template Matching — cross-correlation against reference crash pulses

Each detector outputs a confidence ∈ [0, 1].
Fusion uses configurable weights and a threshold to declare crash.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
from enum import Enum

# ---------------------------------------------------------------------------
# PDTSA import (wraps existing Layer 3 detector)
# ---------------------------------------------------------------------------
from vista_hil.pdtsa_v2 import PDTSAv2, PDTSAConfig, VehicleClass


# ===================================================================
# Configuration
# ===================================================================

@dataclass
class CascadeConfig:
    """Configuration for the 5-method detection cascade."""

    # Acceleration gate (pre-filter before any detector)
    accel_gate_g: float = 3.0            # minimum |a| in g to proceed

    # --- Detector weights for fusion ---
    weight_pdtsa: float = 0.30
    weight_energy_flux: float = 0.20
    weight_wavelet: float = 0.20
    weight_kurtosis: float = 0.15
    weight_template: float = 0.15

    # --- Fusion threshold ---
    fusion_threshold: float = 0.50       # weighted score above which = crash

    # --- Energy Flux parameters ---
    # For a 40 km/h crash (11.1 m/s), peak flux ≈ m·v·a ≈ 1500·11·490 ≈ 8 MW
    # Threshold set conservatively at 0.5 MW for a 20 km/h crash
    energy_flux_threshold_w: float = 500_000.0   # Watts (J/s)
    energy_mass_kg: float = 1500.0               # vehicle mass

    # --- Wavelet Packet parameters ---
    wavelet_level: int = 3                 # decomposition depth
    # Low-frequency bands (indices 0,1,2) contain crash pulse energy
    wavelet_crash_bands: List[int] = field(default_factory=lambda: [0, 1, 2])
    wavelet_energy_threshold: float = 0.40 # fraction of total energy in crash bands

    # --- Kurtosis parameters ---
    # We compute kurtosis of the JERK signal (da/dt), not acceleration.
    # Crash jerk has heavy tails → excess kurtosis >> 0.
    # Normal driving jerk: excess kurtosis ≈ 0 (Gaussian)
    kurtosis_threshold: float = 3.0        # excess kurtosis threshold

    # --- Template Matching parameters ---
    template_match_threshold: float = 0.50  # normalised cross-correlation peak

    # --- Vehicle class (for PDTSA) ---
    vehicle_class: VehicleClass = VehicleClass.UNKNOWN

    # --- Sampling rate ---
    sampling_rate: int = 1000               # Hz


# ===================================================================
# Detector Results
# ===================================================================

@dataclass
class DetectorResult:
    """Result from a single detector."""
    name: str
    confidence: float          # [0, 1]
    triggered: bool
    detail: Optional[Dict] = None


@dataclass
class CascadeResult:
    """Aggregated result from the full cascade."""
    detected: bool
    fused_score: float
    gate_passed: bool
    detectors: List[DetectorResult]
    n_detectors_triggered: int
    fusion_threshold: float
    accel_peak_g: float


# ===================================================================
# Helper: Acceleration Gate
# ===================================================================

def _accel_gate(accel_ms2: np.ndarray) -> Tuple[float, float]:
    """Return (peak_g, peak_g)."""
    accel_mag = np.sqrt(np.sum(accel_ms2 ** 2, axis=1))
    peak_g = float(np.max(accel_mag) / 9.80665)
    return peak_g, peak_g


# ===================================================================
# Detector 1: PDTSA Wrapper
# ===================================================================

def _detect_pdtsa(accel_ms2: np.ndarray, timestamps_s: np.ndarray,
                  cfg: CascadeConfig) -> DetectorResult:
    """Run PDTSA v2 and return normalised confidence."""
    pdtsa_config = PDTSAConfig(
        accel_gate_g=cfg.accel_gate_g,
        vehicle_class=cfg.vehicle_class,
    )
    pdtsa = PDTSAv2(pdtsa_config)
    result = pdtsa.detect(accel_ms2, timestamps_s)
    return DetectorResult(
        name="PDTSA",
        confidence=float(result.features.confidence),
        triggered=bool(result.features.detected),
        detail={
            "jerk_magnitude": result.features.jerk_magnitude,
            "sustain_ms": result.features.sustain_duration_ms,
            "asymmetry_ratio": result.features.asymmetry_ratio,
            "peak_accel_g": result.features.peak_accel_g,
            "delta_v_kmh": result.delta_v_kmh,
        },
    )


# ===================================================================
# Detector 2: Energy Flux
# ===================================================================

def _detect_energy_flux(accel_ms2: np.ndarray, timestamps_s: np.ndarray,
                        cfg: CascadeConfig) -> DetectorResult:
    """
    Monitor rate of kinetic energy change:  d(½mv²)/dt = m·|a|·|v|.

    During a crash, the vehicle rapidly decelerates, so the instantaneous
    power dissipation (energy flux) spikes dramatically.

    We approximate velocity from the accelerometer by integrating the
    acceleration magnitude (starting from 0 — conservative, since actual
    pre-crash velocity > 0).  The peak flux is compared against a
    threshold calibrated to detect crashes ≥ 20 km/h.
    """
    dt = np.mean(np.diff(timestamps_s)) if len(timestamps_s) > 1 else 0.001
    accel_mag = np.sqrt(np.sum(accel_ms2 ** 2, axis=1))

    # Approximate velocity (cumulative trapezoid, starting at 0)
    vel_approx = np.zeros(len(accel_mag))
    for i in range(1, len(accel_mag)):
        vel_approx[i] = vel_approx[i-1] + 0.5 * (accel_mag[i] + accel_mag[i-1]) * dt

    # Instantaneous energy flux:  dE/dt = m · |a| · |v|
    flux = cfg.energy_mass_kg * accel_mag * np.abs(vel_approx)

    peak_flux = float(np.max(flux))

    # Confidence: linear ramp from 0 to 1 between 20% and 100% of threshold
    lo = cfg.energy_flux_threshold_w * 0.2
    hi = cfg.energy_flux_threshold_w
    if hi <= lo:
        hi = lo + 1.0
    confidence = float(np.clip((peak_flux - lo) / (hi - lo), 0.0, 1.0))
    triggered = peak_flux >= cfg.energy_flux_threshold_w

    return DetectorResult(
        name="EnergyFlux",
        confidence=confidence,
        triggered=triggered,
        detail={"peak_flux_w": peak_flux},
    )


# ===================================================================
# Detector 3: Wavelet Packet Decomposition
# ===================================================================

def _haar_decompose(signal: np.ndarray, level: int) -> List[np.ndarray]:
    """
    Simple Haar wavelet decomposition (no scipy dependency).

    Returns list of detail coefficients [cD_level, ..., cD_1] and final
    approximation cA_level.
    """
    coeffs = []
    current = signal.copy()
    for _ in range(level):
        n = len(current)
        if n < 2:
            break
        if n % 2 != 0:
            current = np.append(current, current[-1])
            n += 1
        approx = 0.5 * (current[0::2] + current[1::2])
        detail = 0.5 * (current[0::2] - current[1::2])
        coeffs.append(detail)
        current = approx
    coeffs.append(current)  # final approximation
    return coeffs


def _detect_wavelet(accel_ms2: np.ndarray, timestamps_s: np.ndarray,
                    cfg: CascadeConfig) -> DetectorResult:
    """
    Wavelet Packet Decomposition: extract frequency-band energy.

    We decompose the accel magnitude signal with Haar wavelets and measure
    what fraction of total energy falls in the "crash-relevant" bands.
    Typical crash pulses concentrate energy in low-to-mid frequency bands.
    """
    accel_mag = np.sqrt(np.sum(accel_ms2 ** 2, axis=1))

    # Normalize to [0, 1]
    sig = accel_mag - np.min(accel_mag)
    sig_range = np.max(sig)
    if sig_range > 0:
        sig = sig / sig_range

    coeffs = _haar_decompose(sig, cfg.wavelet_level)

    # Energy in each band
    band_energies = [float(np.sum(c ** 2)) for c in coeffs]
    total_energy = sum(band_energies) + 1e-12

    # Energy in crash-relevant bands (low-frequency detail + approximation)
    crash_energy = sum(band_energies[i] for i in cfg.wavelet_crash_bands
                       if i < len(band_energies))
    fraction = crash_energy / total_energy

    # Confidence: linear ramp
    lo = cfg.wavelet_energy_threshold * 0.5
    hi = cfg.wavelet_energy_threshold
    if hi <= lo:
        hi = lo + 0.01
    confidence = float(np.clip((fraction - lo) / (hi - lo), 0.0, 1.0))
    triggered = fraction >= cfg.wavelet_energy_threshold

    return DetectorResult(
        name="Wavelet",
        confidence=confidence,
        triggered=triggered,
        detail={"crash_band_fraction": fraction,
                "band_energies": band_energies},
    )


# ===================================================================
# Detector 4: Kurtosis
# ===================================================================

def _detect_kurtosis(accel_ms2: np.ndarray, timestamps_s: np.ndarray,
                     cfg: CascadeConfig) -> DetectorResult:
    """
    Kurtosis of the JERK signal (da/dt).

    During a crash, the jerk signal has heavy tails (sharp peaks) which
    produce high excess kurtosis.  Normal driving jerk is approximately
    Gaussian (excess kurtosis ≈ 0).
    """
    dt = np.mean(np.diff(timestamps_s)) if len(timestamps_s) > 1 else 0.001
    accel_mag = np.sqrt(np.sum(accel_ms2 ** 2, axis=1))

    # Compute jerk (finite difference of accel magnitude)
    jerk = np.diff(accel_mag) / max(dt, 1e-6)

    mu = np.mean(jerk)
    sigma = np.std(jerk)
    if sigma < 1e-12:
        return DetectorResult("Kurtosis", 0.0, False, {"excess_kurtosis": 0.0})

    excess_kurtosis = float(np.mean(((jerk - mu) / sigma) ** 4) - 3.0)

    # Confidence: linear ramp from 0 (at kurtosis=0) to 1 (at threshold)
    lo = 1.0  # below this, not interesting
    hi = cfg.kurtosis_threshold
    if hi <= lo:
        hi = lo + 1.0
    confidence = float(np.clip((excess_kurtosis - lo) / (hi - lo), 0.0, 1.0))
    triggered = excess_kurtosis >= cfg.kurtosis_threshold

    return DetectorResult(
        name="Kurtosis",
        confidence=confidence,
        triggered=triggered,
        detail={"excess_kurtosis": excess_kurtosis},
    )


# ===================================================================
# Detector 5: Template Matching
# ===================================================================

def _generate_templates(duration_samples: int) -> List[np.ndarray]:
    """Generate reference crash pulse templates (haversine, half-sine, triangle)."""
    t = np.linspace(0, 1, duration_samples)
    templates = [
        np.sin(np.pi * t) ** 2,          # haversine
        np.sin(np.pi * t),                # half-sine
        1.0 - np.abs(2 * t - 1),          # triangular
    ]
    for i, tmpl in enumerate(templates):
        templates[i] = tmpl / (np.sqrt(np.sum(tmpl ** 2)) + 1e-12)
    return templates


def _detect_template(accel_ms2: np.ndarray, timestamps_s: np.ndarray,
                     cfg: CascadeConfig) -> DetectorResult:
    """
    Cross-correlate accel magnitude against reference crash pulse templates.
    Returns the maximum normalised cross-correlation across all templates.
    """
    accel_mag = np.sqrt(np.sum(accel_ms2 ** 2, axis=1))

    sig = accel_mag - np.mean(accel_mag)
    sig_norm = np.sqrt(np.sum(sig ** 2) + 1e-12)
    sig_normed = sig / sig_norm

    # Template length: typical crash is 30-150 ms → use 100 samples
    tmpl_len = min(100, len(sig) // 2)
    if tmpl_len < 10:
        return DetectorResult("TemplateMatch", 0.0, False, {"max_ncc": 0.0})

    templates = _generate_templates(tmpl_len)

    max_ncc = 0.0
    for tmpl in templates:
        ncc = np.correlate(sig_normed, tmpl, mode='valid')
        local_max = float(np.max(np.abs(ncc)))
        if local_max > max_ncc:
            max_ncc = local_max

    # Confidence: linear ramp
    lo = 0.2   # noise floor
    hi = cfg.template_match_threshold
    if hi <= lo:
        hi = lo + 0.1
    confidence = float(np.clip((max_ncc - lo) / (hi - lo), 0.0, 1.0))
    triggered = max_ncc >= cfg.template_match_threshold

    return DetectorResult(
        name="TemplateMatch",
        confidence=confidence,
        triggered=triggered,
        detail={"max_ncc": max_ncc},
    )


# ===================================================================
# Detection Cascade (main entry point)
# ===================================================================

class DetectionCascade:
    """
    5-Method Detection Cascade for VISTA 2.0 Layer 3.

    Usage:
        cascade = DetectionCascade(config)
        result  = cascade.detect(accel_ms2, timestamps_s)
        if result.detected:
            print("CRASH DECLARED", result.fused_score)
    """

    def __init__(self, config: Optional[CascadeConfig] = None):
        self.config = config or CascadeConfig()

    def detect(self, accel_ms2: np.ndarray,
               timestamps_s: np.ndarray) -> CascadeResult:
        """
        Run the full cascade on a single acceleration record.

        Args:
            accel_ms2:    (N, 3) acceleration in m/s²
            timestamps_s: (N,)   timestamps in seconds

        Returns:
            CascadeResult with fused detection decision
        """
        cfg = self.config

        # ---- Acceleration gate ----
        peak_g, _ = _accel_gate(accel_ms2)
        gate_passed = peak_g >= cfg.accel_gate_g

        if not gate_passed:
            return CascadeResult(
                detected=False,
                fused_score=0.0,
                gate_passed=False,
                detectors=[],
                n_detectors_triggered=0,
                fusion_threshold=cfg.fusion_threshold,
                accel_peak_g=peak_g,
            )

        # ---- Run all 5 detectors ----
        detectors = [
            _detect_pdtsa(accel_ms2, timestamps_s, cfg),
            _detect_energy_flux(accel_ms2, timestamps_s, cfg),
            _detect_wavelet(accel_ms2, timestamps_s, cfg),
            _detect_kurtosis(accel_ms2, timestamps_s, cfg),
            _detect_template(accel_ms2, timestamps_s, cfg),
        ]

        # ---- Weighted fusion ----
        weights = np.array([
            cfg.weight_pdtsa,
            cfg.weight_energy_flux,
            cfg.weight_wavelet,
            cfg.weight_kurtosis,
            cfg.weight_template,
        ])
        confidences = np.array([d.confidence for d in detectors])

        fused_score = float(np.dot(weights, confidences) / np.sum(weights))
        n_triggered = sum(1 for d in detectors if d.triggered)

        detected = fused_score >= cfg.fusion_threshold

        return CascadeResult(
            detected=detected,
            fused_score=fused_score,
            gate_passed=True,
            detectors=detectors,
            n_detectors_triggered=n_triggered,
            fusion_threshold=cfg.fusion_threshold,
            accel_peak_g=peak_g,
        )

    def detect_streaming(self, accel_sample: np.ndarray, timestamp_s: float,
                         state: Optional[Dict] = None) -> Tuple[bool, Dict]:
        """
        Streaming (sample-by-sample) interface for real-time use.

        Maintains a sliding window of accel samples internally.
        Returns (crash_declared, state_dict).
        """
        if state is None:
            state = {
                "buffer": [],
                "timestamps": [],
                "window_ms": 200,
                "detect_interval": 10,
                "sample_count": 0,
                "last_detected": False,
            }

        state["buffer"].append(accel_sample.copy())
        state["timestamps"].append(timestamp_s)
        state["sample_count"] += 1

        max_samples = int(state["window_ms"] / 1000 * self.config.sampling_rate) + 1
        if len(state["buffer"]) > max_samples:
            state["buffer"] = state["buffer"][-max_samples:]
            state["timestamps"] = state["timestamps"][-max_samples:]

        if state["sample_count"] % state["detect_interval"] != 0:
            return state["last_detected"], state

        accel_arr = np.array(state["buffer"])
        ts_arr = np.array(state["timestamps"])
        result = self.detect(accel_arr, ts_arr)
        state["last_detected"] = result.detected
        return result.detected, state


# ===================================================================
# Self-Test
# ===================================================================

def _self_test():
    """Quick self-test with synthetic data."""
    import time

    print("=" * 70)
    print("DETECTION CASCADE — SELF-TEST")
    print("=" * 70)

    cfg = CascadeConfig()
    cascade = DetectionCascade(cfg)
    fs = cfg.sampling_rate

    # --- Test 1: Strong crash pulse (should detect) ---
    dur = 0.08  # 80 ms
    n = int(dur * fs)
    t = np.arange(n) / fs
    pulse_g = 50.0 * np.sin(np.pi * t / dur) ** 2
    accel = np.zeros((n, 3))
    accel[:, 0] = pulse_g * 9.80665
    accel[:, 2] = 9.80665  # gravity

    t0 = time.perf_counter()
    res = cascade.detect(accel, t)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"\n[TEST 1] 50g haversine crash pulse")
    print(f"  Gate passed:   {res.gate_passed}")
    print(f"  Detected:      {res.detected}")
    print(f"  Fused score:   {res.fused_score:.3f}")
    print(f"  Detectors:     {res.n_detectors_triggered}/5 triggered")
    for d in res.detectors:
        trig = "TRIG" if d.triggered else "    "
        print(f"    [{trig}] {d.name:12s}  conf={d.confidence:.3f}  detail={d.detail}")
    print(f"  Time: {elapsed_ms:.2f} ms")
    assert res.detected, "FAIL: 50g crash should be detected"

    # --- Test 2: Normal driving (should NOT detect) ---
    dur2 = 1.0
    n2 = int(dur2 * fs)
    t2 = np.arange(n2) / fs
    accel2 = np.zeros((n2, 3))
    accel2[:, 0] = np.sin(2 * np.pi * 3 * t2) * 0.3 * 9.80665  # 0.3g
    accel2[:, 2] = 9.80665

    res2 = cascade.detect(accel2, t2)
    print(f"\n[TEST 2] 0.3g sinusoidal (normal driving)")
    print(f"  Gate passed:   {res2.gate_passed}")
    print(f"  Detected:      {res2.detected}")
    print(f"  Fused score:   {res2.fused_score:.3f}")
    if res2.gate_passed:
        for d in res2.detectors:
            trig = "TRIG" if d.triggered else "    "
            print(f"    [{trig}] {d.name:12s}  conf={d.confidence:.3f}")
    assert not res2.detected, "FAIL: normal driving should NOT be detected"

    # --- Test 3: Below gate (should NOT detect, gate fails) ---
    accel3 = np.zeros((100, 3))
    accel3[:, 0] = 0.1 * 9.80665  # 0.1g
    accel3[:, 2] = 9.80665
    t3 = np.arange(100) / fs
    res3 = cascade.detect(accel3, t3)
    print(f"\n[TEST 3] 0.1g (below 3g gate)")
    print(f"  Gate passed:   {res3.gate_passed}")
    print(f"  Detected:      {res3.detected}")
    assert not res3.gate_passed, "FAIL: should not pass gate"

    print(f"\n{'='*70}")
    print("ALL SELF-TESTS PASSED")
    print(f"{'='*70}")


if __name__ == "__main__":
    _self_test()
