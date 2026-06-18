# VISTA 2.0 — Formula Catalog
**Version:** 2.0.0 | **Date:** 2026-06-14

---

## Signal Processing

### FIR Anti-Alias Filter (Kaiser Window)
```
h(n) = w(n) × sinc(π(n-M)/f_s)
w(n) = I₀(β√(1-(n-M)²/M²)) / I₀(β)
M = (N-1)/2 = 31 for 63-tap filter
β = 0.1102(A - 8.7), A = stopband attenuation (dB)
```
**Physical meaning:** Removes frequency content above 100Hz to prevent aliasing. Linear phase preserves crash pulse timing.

### ESKF Error-State Transition Matrix
```
F = ∂f/∂δx = [I₃, Δt·I₃, 0₃, -Δt·R, 0₃;
              0₃, I₃, -Δt·R[a_m-b_a]×, 0₃, I₃·Δt;
              0₃, 0₃, I₃-Δt·[ω-b_ω]×, -Δt·I₃, 0₃;
              0₃, 0₃, 0₃, I₃, 0₃;
              0₃, 0₃, 0₃, 0₃, I₃]
```
**Physical meaning:** Propagates position, velocity, orientation, and bias errors forward in time.

### ESKF Joseph Form Update
```
P = (I-KH)P(I-KH)ᵀ + KRKᵀ
K = PHᵀ(HPHᵀ + R)⁻¹
```
**Physical meaning:** Ensures covariance matrix stays positive definite during numerical updates.

---

## Detection

### Acceleration Gate (Tier 0)
```
peak_g = max(|a|) / 9.81
PASS if peak_g ≥ 3.0
```
**Physical meaning:** Non-crash events (vibration, braking) produce <3g. Real crashes always exceed 3g.

### Jerk Magnitude (Tier 1)
```
J_i = |a_i - a_{i-1}| / Δt
```
**Physical meaning:** Jerk amplifies discontinuous onset; insensitive to steady-state offsets. Threshold: 200 g/s (15× separation from non-crash).

### Sustain Duration (Tier 2)
```
T_s = N_s × Δt ≥ T_min = 30 ms
```
**Physical meaning:** Structural plastic deformation exceeds 30ms; road disturbances resolve within 5-15ms.

### Asymmetry with Soft Gating (Tier 3)
```
R_a = N_decay / N_rise
s_a(R_a) = min(1, R_a / 2)
```
**Physical meaning:** Crash pulses are asymmetric (plastic deformation); non-crash events are symmetric (elastic rebound). Soft scoring preserves low-asymmetry side impacts.

### Multi-Sensor Confidence (Tier 4)
```
C = 0.4·s_j + 0.3·s_a + 0.3·s_s + b_OBD + b_audio
Crash if C ≥ 0.65
```
**Physical meaning:** Weighted fusion of physics-based scores with corroboration bonuses from independent sensor channels.

### Energy Flux
```
E_flux = d(½mv²)/dt = m·v·a
```
**Physical meaning:** Rate of kinetic energy change. Crashes dissipate energy rapidly; normal driving maintains near-constant KE.

### Kurtosis
```
K = E[(X-μ)⁴]/σ⁴ - 3
```
**Physical meaning:** Measures departure from Gaussian. Crash pulses are non-Gaussian (K>3); normal driving is approximately Gaussian (K≈0).

### Weighted Fusion
```
S_final = 0.30·S_energy + 0.20·S_pdtsa + 0.20·S_wpd + 0.15·S_kurtosis + 0.15·S_template
Crash if S_final ≥ 0.50
```
**Physical meaning:** Combines evidence from 5 independent detection methods into a single decision score.

---

## Reconstruction

### Delta-V (Hybrid Energy-Momentum)
```
δV_momentum = ∫a·dt (trapezoidal)
δV_energy = √(2·∫a·v·dt) (energy cross-check)
δV_corrected = δV_momentum × (1 + e_combined)
δV_fused = w_edr·δV_edr + w_damage·δV_corrected (if EDR available)
```
**Physical meaning:** Two independent estimates (momentum and energy) combined with restitution correction for velocity rebound.

### Bootstrap CI
```
For i = 1 to B: δV* = trapezoidal(accel[bootstrapped])
CI₉₅ = [Q₀.₀₂₅(δV*), Q₀.₉₇₅(δV*)]
B = 2000, seed = 42
```
**Physical meaning:** Non-parametric confidence interval that makes no assumptions about error distribution.

### PDOF Estimation
```
PDOF = atan2(v_y[peak], v_x[peak])
v_x = ∫a_x·dt, v_y = ∫a_y·dt
```
**Physical meaning:** Direction of force at peak velocity change. Validated to ±10° accuracy (Kusano & Gabler 2013).

### Injury Risk (NHTSA DOT HS 813219)
```
P(MAISi+) = 1 / (1 + exp(-(α + β·δV)))
```
**Physical meaning:** Probability of injury at or above severity level i, derived from NHTSA crash victim database.

---

## Audio Processing

### Short-Term Energy Ratio (Impulse Detection)
```
STER = E_current / E_background
Threshold: STER > 10 for impulse detection
```
**Physical meaning:** Crash impulse produces sudden energy spike relative to background noise.

### GCC-PHAT Cross-Correlation (Temporal Alignment)
```
R_xτ(τ) = IFFT{X(f)·Y*(f)/|X(f)·Y*(f)|}
τ_peak = argmax(R_xτ)
```
**Physical meaning:** Estimates time offset between audio and IMU signals using generalized cross-correlation with phase transform.

### SPL Conversion
```
SPL(dB) = 20·log₁₀(p/p_ref)
p_ref = 20 μPa (standard reference)
```
**Physical meaning:** Converts microphone voltage to sound pressure level in dB SPL.

---

## Cryptographic

### SHA-256 Hash
```
H(m) = SHA256(m)
Output: 32 bytes (256 bits)
Collision resistance: 2¹²⁸ operations
```
**Physical meaning:** Computes a unique fingerprint of the data. Any change to the data changes the hash.

### HMAC-SHA256
```
HMAC(K, m) = SHA256((K' ⊕ opad) || SHA256((K' ⊕ ipad) || m))
```
**Physical meaning:** Produces a keyed message authentication code that verifies both integrity and authenticity.

### SHA-3 (Keccak-256)
```
H(m) = Keccak-256(m)
Output: 32 bytes (256 bits)
Different algorithm than SHA-256
```
**Physical meaning:** Defense-in-depth: if SHA-256 is broken, SHA-3 still protects the evidence.

---

## Sensor Models

### Allan Variance Noise Model
```
σ_total² = σ_white² + σ_bias_walk² + σ_scale_factor²
σ_white = noise_density × √(sampling_rate)
```
**Physical meaning:** Total sensor noise is the sum of white noise, random walk drift, and scale factor uncertainty.

### Temperature Drift
```
S(T) = S₀ × (1 + α·ΔT + β·ΔT²)
O(T) = O₀ + γ·ΔT
```
**Physical meaning:** Sensor sensitivity and offset change with temperature. μ-scale factor changes are typical for MEMS devices.

### Cross-Axis Sensitivity
```
a_measured = M × a_true + offset
M = [[1.0, 0.01, -0.005], [-0.008, 1.0, 0.012], [0.003, -0.007, 1.0]]
```
**Physical meaning:** Each axis has slight coupling to other axes due to MEMS manufacturing tolerances.

---

*All formulas in VISTA 2.0 with physical interpretation and implementation notes.*
