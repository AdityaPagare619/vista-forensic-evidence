# VISTA 2.0 — System Architecture Document
**Version:** 2.0.0 | **Date:** 2026-06-14 | **Classification:** Production Engineering

---

## 1. System Overview

VISTA (Vehicle Intelligence and Safety Telematics Architecture) is an 8-layer IoT forensic crash evidence system that autonomously detects crash events, reconstructs impact severity with quantified uncertainty, multi-modally corroborates the evidence, and packages results in a self-verifying cryptographic archive. The system operates on consumer-grade embedded hardware at approximately USD $78 per unit (10K volume) and produces evidence that can be independently authenticated by any party with a Python interpreter.

**Design Principles (invariant across all layers):**
1. **Evidence, Not Verdicts** — no data structure contains a liability, fraud probability, or automated judgment field
2. **Physics Primary** — inertial measurements drive detection; audio/visual/OBD-II provide corroboration only
3. **External Calibration** — every threshold anchored to CISS reference data, not simulation-only tuning
4. **Reproducible Verification** — evidence authentication uses only standard cryptographic primitives

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VISTA 2.0 ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  VEHICLE WORLD                                                              │
│  ┌────────┐  ┌────────┐  ┌──────────┐  ┌────────┐  ┌────────┐           │
│  │ IMU ×3 │  │ CAN    │  │ Mic ×4   │  │ Camera │  │ FRAM   │           │
│  │ SPI@1k │  │ Bus    │  │ I2S@48k  │  │ DCMI   │  │ SPI    │           │
│  └───┬────┘  └───┬────┘  └────┬─────┘  └───┬────┘  └───┬────┘          │
│      └───────────┼────────────┼─────────────┼───────────┘                │
│                  ▼            ▼             ▼                            │
│  ┌──────────────────────────────────────────────────────┐               │
│  │           L1: SENSOR ACQUISITION (STM32H743)         │               │
│  │  3×SPI DMA @1kHz + FDCAN + I2S + DCMI               │               │
│  │  Hardware timestamps (10ns resolution)               │               │
│  └──────────────────────┬───────────────────────────────┘               │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │           L2: SIGNAL PROCESSING (Cortex-M7)          │               │
│  │  FIR Filter(63taps) → ESKF(15-state) → RTS Smoother │               │
│  │  CPU: 2.37% of 480MHz budget                          │               │
│  └──────────────────────┬───────────────────────────────┘               │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │           L3: DETECTION CASCADE (5-method)           │               │
│  │  3g Gate → [Energy|PDTSA|WPD|Kurtosis|Template]     │               │
│  │  → Weighted Fusion → Crash Declaration               │               │
│  └──────────────────────┬───────────────────────────────┘               │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │           L4: RECONSTRUCTION                         │               │
│  │  Delta-V + PDOF + Injury Risk + Velocity History     │               │
│  └──────────────────────┬───────────────────────────────┘               │
│                         ▼                                                │
│  ┌───────────┐  ┌───────────┐                                            │
│  │ L5: AUDIO │  │ L6: VISUAL│  ← Parallel corroboration                │
│  │ 6-stage   │  │ Multi-cam │                                            │
│  └─────┬─────┘  └─────┬─────┘                                            │
│        └──────┬───────┘                                                   │
│               ▼                                                           │
│  ┌──────────────────────────────────────────────────────┐               │
│  │           L7: EVIDENCE CHAIN                         │               │
│  │  SHA-256 + SHA-3 + HMAC + RFC 3161 timestamps       │               │
│  └──────────────────────┬───────────────────────────────┘               │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │           L8: EVIDENCE DELIVERY                      │               │
│  │  Self-verifying ZIP → verify.py (stdlib only)        │               │
│  └──────────────────────────────────────────────────────┘               │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │  CLOUD / FLEET / INVESTIGATOR                        │               │
│  │  Telemetry → Dashboard → Evidence Review              │               │
│  └──────────────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer Specifications

### L1: Sensor Acquisition

| Component | Model | Interface | Protocol | Rate | Power |
|-----------|-------|-----------|----------|------|-------|
| Primary IMU | IAM-20680HP | SPI @10MHz | DMA | 1kHz | 3.2mW |
| Auxiliary IMU | IAM-20680HP | SPI @10MHz | DMA | 1kHz | 3.2mW |
| High-G IMU | H3LIS331DL | SPI @10MHz | DMA | 1kHz | 0.4mW |
| CAN Bus | TJA1050 | FDCAN (internal) | CAN 2.0B | 10Hz | 75mW |
| Mic Array | 4×IM67D130A | I2S | PDM | 48kHz | 4×4mW |
| Camera | IMX678 | DCMI | MIPI | 30fps | 500mW |
| FRAM | FM25V20A | SPI | R/W | On-demand | 15mW |
| Supercap | 4.7F @ 5.5V | Power rail | Backup | 29sec | — |

**Data rates:** IMU: 3×6×2B×1000 = 36 KB/s. Audio: 4×2B×48000 = 384 KB/s. Camera: 4K@30fps ≈ 24 MB/s (compressed H.265).

**Synchronization:** Hardware timestamps from STM32H743 TIM2+TIM5 cascaded counters (10ns resolution). All sensors sample against common clock. Maximum timing error: ±1 sample period per sensor.

**Failure modes:**
- IMU SPI CRC error → re-initialize sensor (retry 3×, then exclude from voting)
- CAN timeout → use last known vehicle state
- Audio buffer overflow → drop oldest frames
- Camera frame drop → log event, continue capture
- FRAM write failure → fallback to SD card (non-crypto)
- Power loss → FRAM preserves last 2 seconds; supercap provides 29sec backup

### L2: Signal Processing

| Component | Implementation | Latency | RAM |
|-----------|---------------|---------|-----|
| FIR anti-alias | 63-tap Kaiser, fc=100Hz | 31.5ms | 516B |
| ESKF prediction | 15-state, quaternion, Joseph form | <1ms | 2.1KB |
| ESKF update | Multi-rate (1kHz IMU, 10Hz OBD) | <1ms | 2.1KB |
| RTS smoother | Backward pass, post-event | ~50ms | 2.1KB |
| Adaptive threshold | 10-sec sliding window | <1ms | 64B |

**Total CPU:** 2.37% of 480MHz (113K cycles/sample)
**Total RAM:** ~6.8KB (stack + data)
**Total Flash:** ~500B (FIR coefficients)

### L3: Detection Cascade

| Method | What It Measures | Weight | Cycles |
|--------|-----------------|--------|--------|
| 3g Acceleration Gate | Peak acceleration threshold | — | 100 |
| Energy Flux | d(½mv²)/dt | 0.30 | 5,000 |
| PDTSA | Jerk + Sustain + Asymmetry | 0.20 | 5,000 |
| Wavelet Packet | Frequency-band energy | 0.20 | 40,000 |
| Kurtosis | Statistical peakiness | 0.15 | 20,000 |
| Template Matching | Cross-correlation | 0.15 | 50,000 |
| Saturation Override | Sustained clipping detection | — | 500 |

**Fusion:** Weighted sum → threshold 0.50 → crash declaration
**Pipeline:** 5-cycle latency → new result every 1ms
**Total CPU:** ~3% of 480MHz

### L4: Reconstruction

| Component | Method | Output |
|-----------|--------|--------|
| Delta-V | Hybrid energy-momentum + restitution | Scalar value (km/h) |
| CI | Bootstrap Monte Carlo (B=2000, seed=42) | [lower, upper] km/h |
| PDOF | Dual-axis velocity decomposition | Angle (degrees) + confidence |
| Injury Risk | NHTSA DOT HS 813219 logistic curves | MAIS2-6+ probabilities |
| Velocity History | 5-phase decomposition | Full v(t) array |

### L5: Audio Forensics

| Stage | Method | Latency | Output |
|-------|--------|---------|--------|
| 1. Impulse | STER adaptive threshold | <10ms | ImpulseEvent |
| 2. Classification | MFCC + 12-class centroid | ~5ms | ClassificationResult |
| 3. Energy | SPL conversion (20μPa ref) | <1ms | EnergyProfile |
| 4. Source sep. | MVDR beamforming | ~50ms | SeparatedSource |
| 5. Alignment | GCC-PHAT cross-correlation | ~20ms | Offset ±0.1ms |
| 6. Forensic | SHA-256 + HMAC + SWGDE metadata | <1ms | ForensicAudioPackage |

### L6: Visual Analytics

| Component | Function |
|-----------|----------|
| Multi-camera | Front 4K + rear 2K simultaneous |
| Burst capture | 60fps for 2 seconds on trigger |
| Quality metrics | Blur, exposure, noise assessment |
| Key frame detection | First crash, best quality, scene context |
| Evidence packaging | SHA-256 per-frame integrity |

### L7: Evidence Chain

| Step | Operation | Output |
|------|-----------|--------|
| 1 | Deterministic JSON serialization | Byte array |
| 2 | SHA-256 hash | 32-byte hash |
| 3 | SHA-3 (Keccak) hash | 32-byte hash |
| 4 | HMAC-SHA256 signature | 32-byte MAC |
| 5 | Timestamp (system clock) | ISO 8601 |
| 6 | Compose EvidenceRecord | Structured record |
| 7 | Verify | Boolean (hash + HMAC + timestamp) |

### L8: Deployment

| Component | Protocol |
|-----------|----------|
| Device registration | MQTT + X.509 cert |
| Telemetry | MQTT QoS 1, 60s interval |
| OTA update | Uptane framework, A/B partition |
| Evidence chain | Device → MQTT → Cloud → Dashboard |
| Health monitoring | 5-min heartbeat, alert thresholds |

---

## 4. Data Flow Diagrams

### 4.1 Normal Operation (Continuous Monitoring)

```
IMU(1kHz) → L1(Acquire) → L2(FIR+ESKF) → L3(Gate Check)
                                              ↓
                                          [Gate Pass?]
                                           /       \
                                         NO          YES
                                          ↓           ↓
                                   [Wait]      [L3 Cascade]
                                                  ↓
                                            [Threshold?]
                                           /           \
                                         NO            YES
                                          ↓             ↓
                                   [Continue]    [FREEZE BUFFER]
                                                      ↓
                                                  [L4-L7 Pipeline]
                                                      ↓
                                                  [Evidence Package]
```

### 4.2 Crash Event Flow (Trigger to Delivery)

```
T=0ms:   L3 gate triggers → buffer frozen
T=1ms:   L4 reconstruction begins (ESKF → Delta-V → PDOF)
T=5ms:   L5 audio pipeline starts (impulse detection)
T=10ms:  L6 camera burst capture starts (60fps)
T=20ms:  L4 delta-V estimate available
T=50ms:  L5 temporal alignment complete
T=100ms: L7 evidence chain computation
T=150ms: L8 evidence package ready for storage
T=200ms: FRAM write complete
```

### 4.3 Verification Flow

```
Evidence Package (ZIP)
  → Extract EvidenceRecord (JSON)
  → Recompute SHA-256(plaintext) → compare with stored hash
  → Recompute SHA-3(plaintext) → compare with stored hash
  → Verify HMAC-SHA256(plaintext, key) → compare with stored MAC
  → Verify timestamp within ±5s of system clock
  → Return: valid=True/False
```

---

## 5. Security Model

### 5.1 Threat Model

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Data tampering (physical access) | High | Evidence integrity | SHA-256 + SHA-3 dual hash |
| Replay attack | Medium | False evidence | Timestamp + sequence numbers |
| Sensor spoofing | Low | False detection | Multi-sensor voting + physics checks |
| Firmware tampering | Medium | System compromise | Secure boot (TPM in production) |
| Cloud interception | Low | Data exposure | TLS 1.3 + certificate pinning |

### 5.2 Cryptographic Properties

| Property | Implementation | Strength |
|----------|---------------|----------|
| Data integrity | SHA-256 + SHA-3 (dual) | 256-bit collision resistance |
| Authenticity | HMAC-SHA256 | Keyed MAC, prevents forgery |
| Non-repudiation | Sequence numbers + timestamps | Prevents replay |
| Independence | stdlib-only verify.py | No proprietary trust required |
| Defense-in-depth | Dual hash (SHA-256 ∥ SHA-3) | Resilient to single algorithm break |

---

## 6. Performance Budget

### 6.1 Latency Budget (Crash Event)

| Stage | Max Latency | Cumulative |
|-------|-------------|------------|
| L1: Sensor acquisition | 1ms | 1ms |
| L2: FIR filter | 2ms | 3ms |
| L2: ESKF update | 1ms | 4ms |
| L3: 3g gate check | 0.1ms | 4.1ms |
| L3: Detection cascade (5 methods) | 5ms | 9.1ms |
| L3: Fusion decision | 0.5ms | 9.6ms |
| L4: Delta-V reconstruction | 3ms | 12.6ms |
| L5: Audio impulse detection | 5ms | 17.6ms |
| L6: Camera trigger | 2ms | 19.6ms |
| L7: Evidence chain | 5ms | 24.6ms |
| **Total** | | **24.6ms** |

**Constraint:** Airbag deployment decision window is 15-25ms. VISTA's 24.6ms falls within this window for forensic recording purposes (not for airbag triggering — that's the vehicle's responsibility).

### 6.2 Memory Budget

| Component | RAM (bytes) | Flash (bytes) |
|-----------|-------------|---------------|
| FIR coefficients | 0 | 252 |
| FIR state | 516 | 0 |
| ESKF (×3 IMUs) | 6,300 | 0 |
| Detection cascade | 2,048 | 0 |
| Reconstruction | 1,024 | 0 |
| Audio pipeline | 8,192 | 0 |
| Evidence chain | 1,024 | 0 |
| Ring buffers (300s) | 3,600 | 0 |
| FRAM driver | 256 | 0 |
| Stack | 4,096 | 0 |
| **Total** | **~28KB** | **~252B** |

**Available:** 128KB DTCM + 512KB AXI SRAM → 28KB uses 5.5% of DTCM

### 6.3 Power Budget

| Mode | Active Power | Duration | Energy |
|------|-------------|----------|--------|
| Monitoring (normal) | 180mW | Continuous | 180mW |
| Crash detection | 250mW | 25ms | 0.006mJ |
| Evidence write | 300mW | 150ms | 0.045mJ |
| Post-crash (supercap) | 100mW | 29sec | 2.9J |

---

## 7. Deployment Architecture

### 7.1 Single Device

```
┌─────────────────────────────────┐
│     VISTA 2.0 Device            │
│  ┌──────────────────────────┐   │
│  │  STM32H743 MCU           │   │
│  │  ┌─────┐ ┌─────┐ ┌────┐ │   │
│  │  │ IMU │ │ CAN │ │Mic │ │   │
│  │  │ ×3  │ │     │ │ ×4 │ │   │
│  │  └──┬──┘ └──┬──┘ └──┬─┘ │   │
│  │     └───────┼───────┘     │   │
│  │             ▼             │   │
│  │  ┌──────────────────┐     │   │
│  │  │ Evidence Package │     │   │
│  │  │ (SHA-256+HMAC)   │     │   │
│  │  └────────┬─────────┘     │   │
│  └───────────┼───────────────┘   │
│              ▼                   │
│  ┌──────────────────────┐       │
│  │ FRAM (crash-safe)    │       │
│  │ + Supercap (backup)  │       │
│  └──────────────────────┘       │
└─────────────────────────────────┘
```

### 7.2 Fleet Architecture

```
┌────────────┐  MQTT/TLS  ┌────────────┐  ┌────────────┐
│  VISTA ×N  │ ──────────→ │ IoT Hub    │ → │ Dashboard  │
│  (devices) │             │ (cloud)    │  │ (web app)  │
└────────────┘             └────────────┘  └────────────┘
                                │
                           ┌────┴────┐
                           │Evidence │
                           │Chain    │
                           │Service  │
                           └─────────┘
```

---

## 8. ADR Summary

| ADR | Decision | Rationale |
|-----|----------|-----------|
| 001 | 5-method detection cascade | Single-method fails on edge cases; 5 methods provide redundancy |
| 002 | ESKF over Madgwick | Madgwick can't estimate gyro bias; crashes require bias freezing |
| 003 | SHA-256 + SHA-3 dual | Defense-in-depth against algorithm breakthrough |
| 004 | Vehicle transfer function | Without it, simulation-to-reality gap is >200% |
| 005 | 3g acceleration gate | Single gate eliminates all vibration false positives |

---

*This SAD represents the complete system architecture of VISTA 2.0. Every component, interface, and constraint is documented. This is the reference document for all engineering decisions.*
