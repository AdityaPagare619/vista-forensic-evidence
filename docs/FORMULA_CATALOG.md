# VISTA 2.0 Formula Catalog

**Version:** 2.0.0  
**Date:** 2026-06-14  
**Status:** Production Reference  

---

## Table of Contents

1. [MEMS Sensor Simulation](#1-mems-sensor-simulation)
2. [Crash Pulse Generation](#2-crash-pulse-generation)
3. [Vehicle Transfer Function](#3-vehicle-transfer-function)
4. [Error-State Kalman Filter](#4-error-state-kalman-filter)
5. [Detection Cascade](#5-detection-cascade)
6. [Crash Reconstruction](#6-crash-reconstruction)
7. [Audio Pipeline](#7-audio-pipeline)
8. [Visual Pipeline](#8-visual-pipeline)
9. [Evidence Chain](#9-evidence-chain)

---

## 1. MEMS Sensor Simulation

### 1.1 Bandwidth Limiting (Low-Pass Filter)

**Formula:**
```
H(s) = 1 / (1 + s/ωc)²
```

**Discrete (SOS):**
```
b = [b0, b1, b2],  a = [1, a1, a2]
y[n] = b0·x[n] + b1·x[n-1] + b2·x[n-2] - a1·y[n-1] - a2·y[n-2]
```

**Physical Interpretation:** The MEMS analog front-end has a low-pass filter (typically 2nd-order Butterworth) that limits bandwidth. Signals above the cutoff frequency are attenuated.

**Implementation:**
```python
nyquist = sampling_rate / 2
sos = butter(2, cutoff_hz / nyquist, btype='low', output='sos')
filtered = sosfilt(sos, signal, axis=0)
```

**Validity Range:** cutoff_hz < sampling_rate / 2 (Nyquist)

**Source:** Butterworth filter design; sensor datasheet bandwidth specification.

---

### 1.2 White Noise Injection

**Formula:**
```
σ_noise = noise_density × g × √(sampling_rate)
```

where:
- `noise_density` = sensor noise density (g/√Hz)
- `g` = 9.80665 m/s² (conversion factor)
- `sampling_rate` = sampling rate (Hz)

**Physical Interpretation:** MEMS sensors have white noise characterized by noise density (also called velocity random walk for gyros). The standard deviation of the noise in the sampled signal scales with the square root of bandwidth.

**Implementation:**
```python
noise_std = noise_density * 9.80665 * np.sqrt(sampling_rate)
noise = np.random.normal(0, noise_std, signal.shape)
```

**Validity Range:** Valid for sampling rates where noise density is specified (typically 1–1000 Hz).

**Source:** Allan variance characterization; IEEE 529-2001.

---

### 1.3 Bias Random Walk

**Formula:**
```
bias[n+1] = bias[n] + N(0, σ_drift × √(dt))
```

where:
- `σ_drift` = `bias_drift_rate` (g/s for accel, °/s/s for gyro)
- `dt` = time step (seconds)

**Physical Interpretation:** MEMS bias drifts over time as a random walk process. The bias at the next sample is the current bias plus a random increment.

**Implementation:**
```python
accel_noise = np.random.normal(0, bias_drift_rate * 9.80665 * np.sqrt(dt), 3)
accel_bias += accel_noise
```

**Validity Range:** Valid for time scales shorter than the bias instability correlation time (typically 1–100 seconds).

---

### 1.4 Temperature Drift

**Formula:**
```
S(T) = S₀ × (1 + α × ΔT)
O(T) = O₀ + γ × ΔT
```

where:
- `S₀` = nominal sensitivity
- `α` = `temp_sensitivity_coeff` (/°C)
- `γ` = `temp_offset_coeff` (g/°C)
- `ΔT` = `T - T_ref` (°C)

**Physical Interpretation:** MEMS sensitivity and offset change with temperature due to material properties and packaging stress.

**Implementation:**
```python
delta_t = temperature - reference_temp
sensitivity_factor = 1.0 + temp_sensitivity_coeff * delta_t
offset_change = temp_offset_coeff * delta_t * 9.80665
output = input * sensitivity_factor + offset_change
```

**Validity Range:** ±50°C from reference temperature (typical sensor operating range).

---

### 1.5 Cross-Axis Sensitivity

**Formula:**
```
a_measured = M × a_true
```

where `M` is the 3×3 cross-axis sensitivity matrix:
```
M = | m11  m12  m13 |
    | m21  m22  m23 |
    | m31  m32  m33 |
```

**Physical Interpretation:** MEMS axes are not perfectly orthogonal. Force on one axis leaks into other axes through the off-diagonal elements of M.

**Implementation:**
```python
a_measured = cross_axis_matrix @ a_true
```

**Validity Range:** Valid for accelerations within the sensor's dynamic range.

---

### 1.6 Range Clipping (Saturation)

**Formula:**
```
a_clipped = clip(a_true, -range × g, +range × g)
saturated = |a_true| > range × g
```

**Physical Interpretation:** The ADC clips at the maximum representable value. For MPU6050, this is ±16g; for H3LIS331DL, ±400g.

---

### 1.7 Sampling Jitter

**Formula:**
```
t_actual[i] = t_ideal[i] + U(-jitter_pct × dt, +jitter_pct × dt) + drift_rate × t²
```

**Physical Interpretation:** Real sampling instants deviate from ideal due to clock jitter (random) and clock drift (cumulative).

---

## 2. Crash Pulse Generation

### 2.1 Haversine Pulse

**Formula:**
```
a(t) = P × sin²(πt/T)    for 0 ≤ t ≤ T
```

where:
- `P` = peak acceleration (g)
- `T` = crash duration (seconds)

**Physical Interpretation:** Most realistic for frontal barrier crashes per NHTSA research. The sin² shape produces a smooth, symmetric pulse with zero derivatives at onset and offset.

**Delta-V Relationship:**
```
ΔV = ∫₀ᵀ a(t) dt = P × T/2
```

**Validity Range:** 20–150 ms duration, 10–200g peak.

**Source:** NHTSA "Crash Pulse Modeling for Vehicle Safety Research" (2018).

---

### 2.2 Half-Sine Pulse

**Formula:**
```
a(t) = P × sin(πt/T)    for 0 ≤ t ≤ T
```

**Delta-V:**
```
ΔV = P × 2T/π
```

**Physical Interpretation:** Good general approximation for various crash types.

---

### 2.3 Square Pulse

**Formula:**
```
a(t) = P    for 0 ≤ t ≤ T
```

**Delta-V:**
```
ΔV = P × T
```

**Physical Interpretation:** Worst-case scenario for crash detection algorithms. All energy delivered at constant rate.

---

### 2.4 Triangular Pulse

**Formula:**
```
a(t) = P × (1 - |2t/T - 1|)    for 0 ≤ t ≤ T
```

**Delta-V:**
```
ΔV = P × T/2
```

**Physical Interpretation:** Simple baseline for comparison. Symmetric linear ramp-up and ramp-down.

---

### 2.5 Peak Acceleration from Delta-V

**Rule of Thumb:**
```
P ≈ ΔV_kmh / (T_ms × 0.0036)
```

**Validity Range:** 20–150 ms duration, reasonable for parametric generation.

---

## 3. Vehicle Transfer Function

### 3.1 2nd-Order Low-Pass (Vehicle Body)

**Formula:**
```
H(s) = ωn² / (s² + 2ζωn·s + ωn²)
```

where:
- `ωn` = 2π × natural_freq_hz (rad/s)
- `ζ` = damping_ratio

**Frequency Response:**
```
|H(jω)| = ωn² / √((ωn² - ω²)² + (2ζωn·ω)²)
```

**Physical Interpretation:** The vehicle body acts as a mass-spring-damper between the impact point and the sensor mounting location. High-frequency crash content is attenuated.

**Vehicle Presets:**

| Class | ωn (Hz) | ζ | -3dB Frequency |
|-------|---------|---|----------------|
| Sedan | 30 | 0.20 | ~30 Hz |
| SUV | 25 | 0.25 | ~25 Hz |
| Truck | 15 | 0.30 | ~15 Hz |
| Motorcycle | 45 | 0.15 | ~45 Hz |

---

### 3.2 Mounting Attenuation

**Formula:**
```
A_linear = 10^(-A_dB / 20)
```

**Physical Interpretation:** Flexible mounting locations (dashboard, seat rail) attenuate the signal due to mechanical compliance.

---

## 4. Error-State Kalman Filter

### 4.1 State Vector

```
δx = [δp(3), δv(3), δθ(3), δbg(3), δba(3)] ∈ ℝ¹⁵
```

- `δp`: Position error (3 DOF)
- `δv`: Velocity error (3 DOF)
- `δθ`: Attitude error (rotation vector, 3 DOF — minimal parameterization)
- `δbg`: Gyroscope bias error (3 DOF)
- `δba`: Accelerometer bias error (3 DOF)

---

### 4.2 Nominal State Propagation

**Quaternion Update:**
```
q[n+1] = q[n] ⊗ q{ω·Δt}
```

where:
```
q{ω·Δt} = [cos(θ/2), sin(θ/2) × ω̂]
θ = ||ω|| × Δt
ω̂ = ω / ||ω||
```

**Velocity Update:**
```
v[n+1] = v[n] + (R(q) × (a_meas - b_a) - g) × Δt
```

**Position Update:**
```
p[n+1] = p[n] + v[n] × Δt + 0.5 × a_nav × Δt²
```

where `a_nav = R(q) × (a_meas - b_a) - g`

---

### 4.3 Error-State Transition Matrix (F)

```
F = I₁₅ + F_cont × Δt
```

**Continuous F structure:**
```
F_cont = [ I₃   Δt·I₃  -½R·[a]×·Δt²   0      -½R·Δt²  ]
         [ 0    I₃     -R·[a]×·Δt       0      -R·Δt    ]
         [ 0    0       I₃-[ω]×·Δt      -Δt·I₃  0       ]
         [ 0    0       0                I₃      0       ]
         [ 0    0       0                0       I₃      ]
```

where `[v]×` is the skew-symmetric matrix of vector v.

---

### 4.4 Process Noise Covariance (Q)

```
Q = diag([
    σ²_p·Δt,      (position)
    σ²_v·Δt,      (velocity)
    σ²_θ·Δt,      (attitude)
    σ²_bg·Δt,     (gyro bias random walk)
    σ²_ba·Δt      (accel bias random walk)
])
```

**Crash Mode Inflation:**
- CRASH_ONSET: Q[θ] ×= 100, Q[bg] ×= 0.01, Q[ba] ×= 0.01
- POST_CRASH: Q[v] ×= inflation, Q[θ] ×= inflation

---

### 4.5 Measurement Models

**Accelerometer (gravity reference):**
```
z_pred = R(q)ᵀ × g_nav + b_a
H = [ [Rᵀg]×  |  0  |  0  |  0  |  I₃ ]   (3×15)
```

**Gyroscope (zero-rate assumption):**
```
z_pred = 0  (at rest)
H = [ 0 | 0 | 0 | I₃ | 0 ]   (3×15)
```

**GPS (position + velocity):**
```
z_pred = [0, 0, 0, 0, 0, 0]ᵀ
H = [ I₃ | 0 | 0 | 0 | 0 ]   (6×15)
    [ 0   | I₃ | 0 | 0 | 0 ]
```

---

### 4.6 Kalman Gain and Update

**Innovation Covariance:**
```
S = H × P × Hᵀ + R
```

**Kalman Gain:**
```
K = P × Hᵀ × S⁻¹
```

**Error-State Update (Joseph form for numerical stability):**
```
I_KH = I - K × H
P = I_KH × P × I_KHᵀ + K × R × Kᵀ
```

---

### 4.7 Quaternion Renormalization

After attitude update:
```
q = q / ||q||
```

Threshold: `||q|| - 1| > 1e-6` triggers renormalization.

---

### 4.8 RTS Smoother

**Backward Pass:**
```
C_k = P_k × F_kᵀ × P_{k+1}⁻¹
x_smooth[k] = x[k] + C_k × (x_smooth[k+1] - x_pred[k+1])
P_smooth[k] = P[k] + C_k × (P_smooth[k+1] - P[k+1]) × C_kᵀ
```

---

## 5. Detection Cascade

### 5.1 Acceleration Gate

```
peak_g = max(||a[i]||) / g    for i = 1..N
gate_passed = peak_g ≥ accel_gate_g
```

---

### 5.2 Energy Flux

**Formula:**
```
dE/dt = m × |a(t)| × |v(t)|
```

where velocity is approximated by cumulative integration:
```
v[i] = v[i-1] + 0.5 × (|a[i]| + |a[i-1]|) × Δt
```

**Threshold:** 500,000 W (conservative for 20 km/h crash)

---

### 5.3 Wavelet Packet Decomposition

**Haar Wavelet:**
```
approx[k] = 0.5 × (x[2k] + x[2k+1])
detail[k] = 0.5 × (x[2k] - x[2k+1])
```

**Crash Band Fraction:**
```
fraction = Σ(crash_band_energies) / Σ(all_band_energies)
```

where crash bands are indices [0, 1, 2] (low-frequency components).

---

### 5.4 Kurtosis of Jerk

**Jerk:**
```
jerk[i] = (|a[i+1]| - |a[i]|) / Δt
```

**Excess Kurtosis:**
```
κ = E[((jerk - μ) / σ)⁴] - 3
```

**Threshold:** κ ≥ 3.0 (Gaussian has κ = 0)

---

### 5.5 Template Matching (Normalized Cross-Correlation)

**Formula:**
```
NCC[k] = Σ_i (x[i+k] × tmpl[i]) / (||x|| × ||tmpl||)
```

**Templates:** Haversine (sin²), half-sine (sin), triangular

**Threshold:** max(|NCC|) ≥ 0.50

---

### 5.6 Weighted Fusion

**Formula:**
```
fused_score = Σ(w_i × confidence_i) / Σ(w_i)
```

**Detection:** `fused_score ≥ fusion_threshold`

**Default Weights:**
- PDTSA: 0.30
- Energy Flux: 0.20
- Wavelet: 0.20
- Kurtosis: 0.15
- Template: 0.15

---

## 6. Crash Reconstruction

### 6.1 Delta-V (Momentum Method)

**Formula:**
```
ΔV = |∫₀ᵀ a(t) dt|
```

**Discrete:**
```
ΔV = |Σᵢ a[i] × Δt|
```

---

### 6.2 Delta-V (Energy Method)

**Formula:**
```
ΔV_e = √(v_i² + 2 × ∫₀ᵀ a(t) × v(t) dt)
```

For v_i = 0:
```
ΔV_e = √(2 × ∫₀ᵀ a(t) × v(t) dt)
```

---

### 6.3 Restitution Correction

**Formula:**
```
ΔV_total = ΔV_compression × (1 + e)
```

where `e` = coefficient of restitution (0.05–0.30 for vehicles)

---

### 6.4 Bootstrap Confidence Interval

**Procedure:**
1. Resample acceleration data B = 2000 times with replacement
2. Compute ΔV for each resample
3. Take α/2 and (1-α/2) percentiles

```
CI = [percentile(ΔV_boot, α/2 × 100), percentile(ΔV_boot, (1-α/2) × 100)]
```

---

### 6.5 Principal Direction of Force (PDOF)

**Formula:**
```
PDOF = atan2(Δv_y, Δv_x)
```

where:
```
Δv_x = ∫[t-w, t] a_x(t') dt'
Δv_y = ∫[t-w, t] a_y(t') dt'
```

and `w` = integration window (10 ms typical)

---

### 6.6 Injury Risk (Logistic Regression)

**Formula:**
```
P(injury) = 1 / (1 + exp(-β₀ - β₁ × ΔV_kmh))
```

**Coefficients (NHTSA DOT HS 813219):**

| MAIS Level | β₀ (All) | β₁ (All) | β₀ (Frontal) | β₁ (Frontal) |
|-----------|----------|----------|--------------|--------------|
| MAIS 2+ | -4.410 | 0.089 | -4.802 | 0.098 |
| MAIS 3+ | -5.127 | 0.095 | -5.521 | 0.103 |
| MAIS 4+ | -6.229 | 0.104 | -6.415 | 0.110 |
| MAIS 5+ | -7.005 | 0.108 | -7.148 | 0.115 |
| MAIS 6 | -7.843 | 0.112 | -7.931 | 0.118 |

---

### 6.7 Baseline Correction

**Formula:**
```
a_corrected[i] = a[i] - bias
```

where:
```
bias = mean(a[0:N_pre])  or  median(a[0:N_pre])
```

`N_pre` = samples in pre-crash window (20 ms typical)

---

### 6.8 Phase Decomposition

**Onset Detection:**
```
onset_idx = first i where |a[i]| ≥ 0.1 × peak_accel
```

**Compression End:**
```
compression_end = first i > peak_idx where |a[i]| < 0.1 × peak_accel
```

---

## 7. Audio Pipeline

### 7.1 Short-Term Energy Ratio (STER)

**Frame Energy:**
```
E_frame[k] = mean(x²[n])    for n in frame k
```

**Background Estimate (Exponential Moving Average):**
```
B[k] = α × E_frame[k] + (1-α) × B[k-1]    if E_frame < B[k-1]
B[k] = B[k-1]                                otherwise
```

**STER:**
```
STER[k] = E_frame[k] / B[k]
```

**Impulse Declaration:** STER > threshold (default: 6.0)

---

### 7.2 MFCC Computation

**Mel Filterbank:**
```
mel(f) = 2595 × log₁₀(1 + f/700)
```

**Triangular Filter:**
```
H_m(f) = { (f - f_left) / (f_center - f_left)   for f_left ≤ f ≤ f_center
          { (f_right - f) / (f_right - f_center)  for f_center ≤ f ≤ f_right
```

**DCT-II:**
```
C[n] = Σ_m log(E_m) × cos(πn(2m+1) / (2M))
```

---

### 7.3 SPL Conversion

**Formula:**
```
SPL_dB = 20 × log₁₀(p / p_ref)
```

where `p_ref = 20 μPa`

---

### 7.4 MVDR Beamforming

**Formula:**
```
w = R⁻¹ × a / (aᴴ × R⁻¹ × a)
```

where:
- `R` = spatial covariance matrix
- `a` = steering vector
- `w` = beamformer weights

**Steering Vector:**
```
a_i = exp(j × 2π × d_i × sin(θ) / λ)
```

where `d_i` = microphone position, `λ` = wavelength

---

### 7.5 GCC-PHAT Alignment

**Formula:**
```
GCC(τ) = IFFT(X(f) × Y*(f) / |X(f) × Y*(f)|)
```

**Sub-sample Refinement (Parabolic Interpolation):**
```
τ_sub = 0.5 × (R[τ-1] - R[τ+1]) / (R[τ-1] - 2R[τ] + R[τ+1])
```

---

## 8. Visual Pipeline

### 8.1 Blur Detection (Laplacian Variance)

**Laplacian:**
```
L(i,j) = I(i-1,j) + I(i+1,j) + I(i,j-1) + I(i,j+1) - 4×I(i,j)
```

**Blur Score:**
```
blur_score = var(L)
```

Higher = sharper image.

---

### 8.2 Exposure Analysis

**Mean Brightness:**
```
μ = mean(I)
```

**Underexposed Percentage:**
```
under_pct = count(I < 25) / total_pixels × 100
```

**Overexposed Percentage:**
```
over_pct = count(I > 230) / total_pixels × 100
```

---

### 8.3 Noise Estimation (MAD)

**Formula:**
```
noise = 1.4826 × median(|residual - median(residual)|)
```

where `residual = I - median_filter(I, size=3)`

The factor 1.4826 converts MAD to standard deviation for Gaussian noise.

---

## 9. Evidence Chain

### 9.1 Deterministic Serialization

```python
json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
```

Sorted keys + no whitespace ensures the same payload always produces the same hash.

---

### 9.2 SHA-256 Hash

```
hash = SHA256(serialized_payload)
```

256-bit (64 hex character) digest.

---

### 9.3 SHA-3 (Keccak) Hash

```
hash = SHA3-256(serialized_payload)
```

256-bit (64 hex character) digest. Different construction (sponge) than SHA-256 (Merkle-Damgård).

---

### 9.4 HMAC-SHA256

```
hmac = HMAC-SHA256(key, payload + "|" + timestamp + "|" + sequence)
```

Covers payload + timestamp + sequence for authenticity and ordering.

---

### 9.5 Fleet Evidence Chain (Hash Chain)

```
record[i].hash = SHA256(record_data + record[i-1].hash)
```

Each record's hash includes the previous record's hash, creating a tamper-evident chain (similar to blockchain).
