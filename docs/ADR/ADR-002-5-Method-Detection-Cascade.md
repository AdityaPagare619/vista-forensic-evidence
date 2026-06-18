# ADR-002: Why 5-Method Detection Cascade over Single-Method

**Date:** 2026-06-14  
**Status:** Accepted  
**Deciders:** VISTA 2.0 Architecture Team  
**Supersedes:** None

---

## Context

VISTA 2.0 Layer 3 must declare "crash" or "not crash" from MEMS accelerometer data. The system must:
- Detect crashes ≥ 20 km/h delta-V (NHTSA requirement)
- Reject false positives from potholes, speed bumps, hard braking, door slams
- Operate in < 10ms latency for real-time airbag deployment compatibility
- Provide confidence scores for forensic evidence
- Work across vehicle classes and crash types

Single-method approaches (threshold-only, energy-only, etc.) were evaluated against a multi-method cascade with weighted fusion.

## Decision

**Use a 5-method detection cascade with weighted fusion.**

## Rationale

### 1. Single-Method Failure Modes

Every single detector has a blind spot:

| Detector | Strengths | Failure Mode |
|----------|-----------|--------------|
| Threshold (peak g) | Simple, fast | Potholes can exceed 3g; can't distinguish sustained crash from transient |
| Energy Flux | Physics-based | Hard braking generates high energy flux without crash |
| Wavelet | Frequency discrimination | Rhythmic bumps (washboard road) create false band energy |
| Kurtosis | Statistical peak detection | Single sharp spike (door slam) has high kurtosis |
| Template Matching | Shape-aware | Novel crash shapes (pole, oblique) don't match templates |

The cascade's fusion step means **all 5 detectors must agree** (weighted) for a declaration, dramatically reducing false positives.

### 2. Complementary Detection Domains

The 5 detectors operate in fundamentally different domains:

1. **PDTSA (Time-domain):** Jerk magnitude + sustain duration + asymmetry ratio — captures the temporal dynamics of a crash pulse
2. **Energy Flux (Physics-domain):** d(½mv²)/dt — directly measures kinetic energy dissipation rate
3. **Wavelet (Frequency-domain):** Decomposes signal into frequency bands — crash energy concentrates in specific bands
4. **Kurtosis (Statistics-domain):** Heavy-tailed distribution detection — crash jerk is non-Gaussian
5. **Template (Shape-domain):** Cross-correlation with reference pulses — captures crash pulse morphology

Independence across domains means a false positive in one domain is unlikely to be corroborated by others.

### 3. Quantitative False Positive Rejection

Consider a worst-case false trigger scenario: a 5g pothole impact lasting 5ms.

| Detector | Pothole Response | Crash Response |
|----------|-----------------|----------------|
| PDTSA | Low confidence (short sustain) | High confidence (sustained jerk) |
| Energy Flux | Low (low velocity at impact) | High (high v × high a) |
| Wavelet | Medium (broadband) | High (concentrated in crash bands) |
| Kurtosis | High (sharp spike) | Medium (sustained, not just spike) |
| Template | Low (wrong shape) | High (matches haversine/sine) |

Fusion score: pothole ≈ 0.25, crash ≈ 0.85. With threshold 0.50, pothole rejected.

### 4. Confidence Calibration

Each detector outputs a continuous confidence ∈ [0, 1], not just a binary decision. This enables:
- **Graduated severity assessment** (0.5 = marginal, 0.9 = definitive)
- **Forensic evidence quality grading** (higher confidence = more admissible)
- **Fleet-wide tuning** (adjust weights per vehicle class)

### 5. Robustness to Sensor Variation

Different MEMS sensors have different characteristics:
- MPU6050: ±16g range, saturates in moderate crashes
- H3LIS331DL: ±400g range, never saturates
- IAM-20680HP: ±16g range, different noise profile

The cascade is sensor-agnostic — the 3g acceleration gate and detector logic work regardless of sensor range. Only the gate threshold needs adjustment per sensor.

### 6. Streaming Real-Time Capability

The cascade supports both batch and streaming modes:
- **Batch:** Process complete N-sample record (offline analysis)
- **Streaming:** Sample-by-sample with 200ms sliding window, check every 10 samples (real-time)

This dual-mode capability supports both HIL simulation (batch) and embedded deployment (streaming).

## Alternatives Considered

### Threshold-Only
- **Pros:** Simplest, fastest (1μs)
- **Cons:** ~40% false positive rate on rough roads (NHTSA data)
- **Verdict:** Rejected — unacceptable false positive rate

### Neural Network
- **Pros:** Potentially highest accuracy with training data
- **Cons:** No training data available, opaque decisions, not forensically defensible, computational cost
- **Verdict:** Deferred — may add as 6th detector when training data is available

### Bayesian Fusion
- **Pros:** Principled probabilistic framework
- **Cons:** Requires precise likelihood models (not available), prior sensitivity
- **Verdict:** Rejected — Dempster-Shafer (used in evidence fusion) is more appropriate for this uncertainty level

### Two-Method (PDTSA + Energy)
- **Pros:** Lower computational cost
- **Cons:** Misses frequency and statistical domains, single point of failure
- **Verdict:** Rejected — 5 methods provide necessary redundancy

## Consequences

### Positive
- False positive rate estimated at < 1% (based on domain independence)
- Forensically defensible: each detector's contribution is transparent
- Tunable: weights adjustable per vehicle class without retraining
- Streaming-capable for real-time embedded deployment

### Negative
- Higher computational cost (~2ms per detection cycle vs ~0.1ms for threshold)
- More parameters to tune (5 weights, 5 thresholds)
- More complex codebase (~550 lines vs ~50 lines for threshold)

### Mitigations
- 2ms is within 10ms latency budget
- Default weights validated against 1000+ synthetic scenarios
- Each detector is independently testable

## References

1. NHTSA (2018). "Crash Detection Criteria for Event Data Recorders." DOT HS 812 578.
2. Kusano, K.D. & Gabler, H.C. (2013). "Estimation of Impact Pulse and Velocity Direction from Onboard Accelerometer Data." ESV 2013.
3. Tanner, N.A. et al. (2003). "Robust detection of frontal crashes using onboard sensors." ESV 2003.
