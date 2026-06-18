# ADR-001: Why ESKF over Madgwick for Crash Detection

**Date:** 2026-06-14  
**Status:** Accepted  
**Deciders:** VISTA 2.0 Architecture Team  
**Supersedes:** None

---

## Context

VISTA 2.0 requires a state estimator (Layer 2) that provides:
- 6DOF vehicle state (position, velocity, attitude) from MEMS IMU
- Bias estimation for gyroscope and accelerometer
- Graceful degradation during crash events (50–200g transients)
- Compatibility with STM32H743 (ARM Cortex-M7, 480MHz)
- Real-time operation at 1kHz

Two primary candidates were evaluated:
1. **Error-State Kalman Filter (ESKF)** — 15-state, quaternion-based
2. **Madgwick AHRS Filter** — Gradient-descent complementary filter

## Decision

**Use ESKF (15-state) over Madgwick.**

## Rationale

### 1. Crash-State Adaptability

The ESKF has a **structurally natural crash-mode**:
- **Pre-crash:** Full ESKF with gravity convergence
- **Crash-onset:** Freeze bias estimation, inflate attitude process noise ×100
- **Post-crash:** Resume with inflated measurement covariance ×10

Madgwick's gradient-descent gain is a single tuning parameter (β). During a crash, the accelerometer reads 50–200g instead of 1g, which corrupts the gravity reference. Madgwick has no mechanism to gracefully reject or weight measurements differently during transients — the filter simply gets wrong answers during the crash.

### 2. Bias Estimation

The ESKF explicitly estimates 6 bias states (3 gyro + 3 accel) as part of its state vector. This is critical because:
- MEMS bias instability (e.g., MPU6050: 0.005°/s gyro, 0.0005g accel) accumulates over time
- Crash detection requires accurate baseline to distinguish crash from drift
- The ESKF's bias states converge during pre-crash driving and are frozen during crash

Madgwick does **not** estimate bias. It assumes zero-rate and zero-acceleration at rest, which drifts over time. This makes it unsuitable for extended pre-crash monitoring.

### 3. Covariance-Based Confidence

The ESKF maintains a 15×15 covariance matrix that provides:
- **Uncertainty quantification** for each state estimate
- **Automatic weighting** of measurements (Kalman gain adapts to noise)
- **Crash confidence metrics** from covariance inflation

Madgwick provides point estimates only — no uncertainty information. For a forensic system, knowing "I'm 95% confident the delta-V is 40±3 km/h" is essential for legal admissibility.

### 4. GPS Fusion Capability

The ESKF's measurement model naturally supports GPS position and velocity updates. VISTA 2.0's OBD-II CAN bus provides vehicle speed (10Hz), which can be fused as a velocity constraint.

Madgwick cannot incorporate GPS/OBD data without fundamental redesign.

### 5. RTS Smoother for Forensic Post-Processing

The ESKF supports Rauch-Tung-Striebel (RTS) backward smoothing for offline forensic analysis:
- Forward pass: real-time filtering during the event
- Backward pass: optimal smoothing using future observations
- Produces minimally-variance state estimates for the entire crash record

This is essential for post-crash forensic reconstruction but impossible with Madgwick (which is inherently causal).

### 6. Computational Cost

| Metric | ESKF | Madgwick |
|--------|------|----------|
| State dimension | 15 | 4 (quaternion) |
| Matrix operations | 15×15 (225 elements) | Vector only |
| FLOPs per update | ~5,000 | ~500 |
| STM32H743 time | ~50μs at 1kHz | ~5μs at 1kHz |
| Memory | ~8 KB (P matrix) | ~200 bytes |

The ESKF is ~10× more expensive, but at 1kHz on a 480MHz Cortex-M7, 50μs is well within the 1ms budget. The computational cost is negligible compared to the algorithmic benefits.

## Alternatives Considered

### Madgwick AHRS
- **Pros:** Simple, fast, no matrix math
- **Cons:** No bias estimation, no covariance, no crash-mode, no GPS fusion
- **Verdict:** Rejected — insufficient for forensic-grade estimation

### Extended Kalman Filter (EKF)
- **Pros:** Well-understood, similar to ESKF
- **Cons:** Quaternions in state vector require 4D attitude error (redundant), singularities possible
- **Verdict:** Rejected — ESKF's minimal 3D attitude error is cleaner

### Unscented Kalman Filter (UKF)
- **Pros:** Better handling of nonlinearities
- **Cons:** 2× computational cost of EKF, marginal benefit for this application
- **Verdict:** Rejected — ESKF sufficient for the dynamics involved

## Consequences

### Positive
- Forensic-grade state estimation with uncertainty bounds
- Graceful crash-mode adaptation
- GPS/OBD velocity fusion capability
- Offline RTS smoothing for post-crash analysis
- Well-established theory with extensive literature

### Negative
- Higher computational cost (~50μs vs ~5μs)
- More complex implementation (~900 lines vs ~200 lines)
- Requires tuning of 15+ noise parameters (vs 1 for Madgwick)
- Needs careful P-matrix initialization

### Mitigations
- 50μs is within 1ms budget — no real-time concern
- Complexity is managed with dataclasses and clear method separation
- Default ESKFConfig provides reasonable starting parameters
- P-matrix initialized from datasheet specifications

## References

1. Solà, J. (2017). "Quaternion kinematics for the error-state Kalman filter." arXiv:1711.02508.
2. Markley, F.L. & Crassidis, J.L. (2014). "Fundamentals of Spacecraft Attitude Determination and Control." Springer.
3. Madgwick, S.O.H. (2010). "An efficient orientation filter for inertial and inertial/magnetic sensor arrays." University of Bristol.
4. STM32H743 Reference Manual (RM0433). STMicroelectronics.
