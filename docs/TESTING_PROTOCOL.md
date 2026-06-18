# VISTA 2.0 Testing Protocol

**Version:** 2.0.0  
**Date:** 2026-06-14  
**Status:** Production Reference

---

## 1. Testing Strategy Overview

### Test Pyramid

```
         /-------------\
        |  E2E / HIL    |  5%
       /----------------\
      | Integration Tests |  15%
     /--------------------\
    |   Component Tests    |  30%
   /------------------------\
  |      Unit Tests          |  50%
 /----------------------------\
```

### Coverage Targets

| Module | Unit | Integration | Target |
|--------|------|-------------|--------|
| mems_simulator.py | 10 | 2 | 90%+ |
| crash_pulse.py | 12 | 2 | 90%+ |
| realistic_simulation.py | 6 | 3 | 85%+ |
| eskf.py | 12 | 3 | 90%+ |
| detection_cascade.py | 10 | 3 | 90%+ |
| reconstruction.py | 14 | 3 | 90%+ |
| audio_pipeline.py | 12 | 3 | 85%+ |
| visual_pipeline.py | 11 | 2 | 85%+ |
| evidence_chain.py | 8 | 2 | 95%+ |
| deployment.py | 10 | 3 | 90%+ |

---

## 2. Unit Test Strategy by Module

### 2.1 mems_simulator.py (10 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| MEMS-001 | Static reading: zero input, gravity on Z | Mean Z in [0.95, 1.05] g |
| MEMS-002 | Saturation detection: 50g on 16g sensor | Saturation flag = True |
| MEMS-003 | Saturation clipping: output bounded | Max output <= 16g |
| MEMS-004 | Noise floor: zero input, 10k samples | Std dev within 50% of expected |
| MEMS-005 | Bandwidth limiting: 500Hz on 260Hz BW | Output < 50% of input amplitude |
| MEMS-006 | Timestamps monotonically increasing | All diffs > 0 |
| MEMS-007 | Cross-axis coupling: force on X only | Y-axis shows coupling signal |
| MEMS-008 | Temperature drift: 25C to 50C | Sensitivity changes correctly |
| MEMS-009 | YAML loading: MPU6050 config | All fields populated |
| MEMS-010 | Gyro simulation with noise | Output has expected variance |

### 2.2 crash_pulse.py (12 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| CRP-001 | Haversine shape correctness | Peak at midpoint, zero at edges |
| CRP-002 | Half-sine amplitude | Peak equals peak_g |
| CRP-003 | Square pulse constant amplitude | Constant during pulse |
| CRP-004 | Triangular linear ramp | Symmetric linear shape |
| CRP-005 | Frontal direction: primary on X | X-axis dominant |
| CRP-006 | Side direction: primary on Y | Y-axis dominant |
| CRP-007 | Offset direction: mix of X and Y | Both axes non-zero |
| CRP-008 | Realistic features present | Vibration + ringing added |
| CRP-009 | Unit conversion: g to m/s2 | Factor of 9.80665 |
| CRP-010 | Random crash parameters valid | All fields in valid ranges |
| CRP-011 | Batch of 1000 scenarios | No exceptions |
| CRP-012 | Config validation: negative peak | ValueError raised |

### 2.3 realistic_simulation.py (6 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| RSC-001 | VTF attenuation of high frequencies | HF content reduced |
| RSC-002 | All 4 vehicle presets different | Different filtering per class |
| RSC-003 | PreCrash vibration components | Engine + road + wind present |
| RSC-004 | Complete chain: all output fields | All keys present and valid |
| RSC-005 | 5 scenario variants complete | No errors |
| RSC-006 | All 4 mounting presets different | Different attenuation levels |

### 2.4 eskf.py (12 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| ESKF-001 | Static gravity convergence | Attitude converges to identity |
| ESKF-002 | Quaternion norm preserved | Norm in [1-1e-6, 1+1e-6] |
| ESKF-003 | Bias convergence at rest | Bias tracks true bias |
| ESKF-004 | Velocity integration: constant accel | v = a * t |
| ESKF-005 | Crash onset detection at 50g | State transitions to CRASH_ONSET |
| ESKF-006 | Bias frozen during crash | Bias unchanged |
| ESKF-007 | Covariance positive definite | All eigenvalues > 0 |
| ESKF-008 | GPS update corrects position | Position moves toward GPS |
| ESKF-009 | Euler angle extraction | Matches quaternion |
| ESKF-010 | RTS smoother improves estimate | Smoothed variance < filtered |
| ESKF-011 | Zero dt produces no change | State unchanged |
| ESKF-012 | Multi-step consistency | State remains bounded |

### 2.5 detection_cascade.py (10 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| DET-001 | 50g crash detected | detected = True |
| DET-002 | 0.1g below gate | gate_passed = False |
| DET-003 | Normal driving not detected | detected = False |
| DET-004 | All 5 detectors run | len(detectors) == 5 |
| DET-005 | Fused score in [0,1] | 0 <= score <= 1 |
| DET-006 | Streaming mode works | State maintained |
| DET-007 | Custom weights applied | Fused score changes |
| DET-008 | Energy flux threshold | Triggered above threshold |
| DET-009 | Wavelet crash bands | Energy fraction correct |
| DET-010 | Kurtosis of crash jerk | Excess kurtosis > 0 |

### 2.6 reconstruction.py (14 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| REC-001 | Delta-V from known pulse | Within 5% of analytical |
| REC-002 | Bootstrap CI contains true value | CI covers mean |
| REC-003 | Saturation detection | Flag set when clipping |
| REC-004 | PDOF frontal: angle near 0 | abs(angle) < 15 deg |
| REC-005 | PDOF side: angle near 90 | abs(angle-90) < 15 |
| REC-006 | Injury risk: 0 km/h -> low | mais2 < 0.01 |
| REC-007 | Injury risk: 80 km/h -> high | mais3 > 0.1 |
| REC-008 | Risk curve monotonic | P increases with dV |
| REC-009 | Velocity history phases | 3+ phases detected |
| REC-010 | Baseline correction | Pre-crash mean ~ 0 |
| REC-011 | Full reconstruction completeness | All keys present |
| REC-012 | Edge case: single sample | No crash, defaults |
| REC-013 | Restitution coefficient effect | Higher e -> different dV |
| REC-014 | Crash mode selection | Frontal vs all coefficients |

### 2.7 audio_pipeline.py (12 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| AUD-001 | Impulse detection on burst | Events detected |
| AUD-002 | No impulse on silence | No events |
| AUD-003 | Classification: frontal vs rear | Different classes |
| AUD-004 | MFCC feature extraction | 13 coefficients returned |
| AUD-005 | SPL conversion accuracy | Within 1 dB |
| AUD-006 | Severity classification | Maps correctly |
| AUD-007 | Beamformer runs | Sources returned |
| AUD-008 | Temporal alignment precision | Offset < 1ms |
| AUD-009 | Forensic package integrity | SHA-256 valid |
| AUD-010 | HMAC verification | Valid with correct key |
| AUD-011 | SWGDE metadata present | Required fields exist |
| AUD-012 | Full pipeline end-to-end | PipelineResult.success |

### 2.8 visual_pipeline.py (11 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| VIS-001 | Start/stop recording | Flags toggle |
| VIS-002 | Pre-crash capture count | Correct frame count |
| VIS-003 | Burst: 120 frames per camera | Correct count |
| VIS-004 | Blur detection sharp vs blurry | Sharp > blurry |
| VIS-005 | Exposure analysis | Mean brightness computed |
| VIS-006 | Key frame detection | At least 1 key frame |
| VIS-007 | Evidence package generation | All fields populated |
| VIS-008 | Package verification valid | valid = True |
| VIS-009 | Tamper detection | Tampered -> invalid |
| VIS-010 | Dual hash different | SHA-256 != SHA-3 |
| VIS-011 | Performance: burst < 5s | Timing check |

### 2.9 evidence_chain.py (8 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| EVC-001 | Create and verify valid record | valid = True |
| EVC-002 | Tampered payload fails | valid = False |
| EVC-003 | Wrong HMAC key fails | valid = False |
| EVC-004 | JSON round-trip preserves | Verify passes |
| EVC-005 | Dual hash different | SHA-256 != SHA-3 |
| EVC-006 | Short key rejected | ValueError |
| EVC-007 | Sequential records valid | All verify |
| EVC-008 | Payload comparison | Match/mismatch cases |

### 2.10 deployment.py (10 tests)

| ID | Test | Pass Criteria |
|----|------|---------------|
| DEP-001 | Device registration | 2 devices registered |
| DEP-002 | TPM identity verification | Correct key passes |
| DEP-003 | Duplicate rejected | ValueError |
| DEP-004 | Device heartbeat | Last seen updated |
| DEP-005 | Telemetry aggregation | Min/max/mean correct |
| DEP-006 | OTA update simulation | Status -> COMPLETE |
| DEP-007 | OTA package verification | Checksum matches |
| DEP-008 | Fleet evidence chain | Chain verifies |
| DEP-009 | Health monitor alerts | Alerts generated |
| DEP-010 | Fleet manager integration | Full workflow |

---

## 3. Integration Test Strategy

### 3.1 MEMS + Crash Pulse (2 tests)

| ID | Test |
|----|------|
| INT-001 | Full chain: generate pulse -> simulate sensor -> verify output |
| INT-002 | Batch: 100 scenarios through sensor, all complete |

### 3.2 ESKF + MEMS (3 tests)

| ID | Test |
|----|------|
| INT-003 | ESKF processes simulated sensor, velocity converges to delta-V |
| INT-004 | ESKF crash mode handles sensor saturation gracefully |
| INT-005 | ESKF + GPS fusion improves position accuracy |

### 3.3 Detection + Reconstruction (3 tests)

| ID | Test |
|----|------|
| INT-006 | Cascade detects crash -> reconstruction runs |
| INT-007 | Reconstruction from cascade: delta-V and PDOF computed |
| INT-008 | Injury risk from reconstructed delta-V: probabilities valid |

### 3.4 Audio + Visual + Evidence (3 tests)

| ID | Test |
|----|------|
| INT-009 | Audio pipeline -> forensic package with valid HMAC |
| INT-010 | Visual pipeline -> evidence package with valid hashes |
| INT-011 | Both packages share evidence chain, integrity maintained |

### 3.5 Full HIL Simulation (3 tests)

| ID | Test |
|----|------|
| INT-012 | Complete: pulse -> sensor -> ESKF -> detection -> reconstruction |
| INT-013 | 10 scenarios through full pipeline, all complete in < 60s |
| INT-014 | RealisticCrashSimulator full chain: all output fields valid |

---

## 4. Stress Test Methodology

### 4.1 Batch Stress (1000 Scenarios)

| Metric | Target |
|--------|--------|
| Total completion | 100% (no failures) |
| Total time | < 300 seconds |
| Memory peak | < 2 GB |
| NaN/Inf values | 0 |
| Uncaught exceptions | 0 |

### 4.2 Memory Stress

| Test | Target |
|------|--------|
| 1000 consecutive simulations, no cleanup | Memory stable |
| 10,000-sample crash pulse | Completes without OOM |
| 4-channel audio, 10 seconds | Completes without OOM |

### 4.3 Edge Cases

| Test | Expected |
|------|----------|
| Single-sample input | Graceful handling |
| All-zero input | No NaN, valid output |
| All-max input | Clipped, no crash |
| Negative time step | Skipped |
| Extreme temperature (-40C) | Drift applied |
| Extreme temperature (+85C) | Drift applied |
| Zero sampling rate | Handled |
| Empty arrays | No crash, empty output |

---

## 5. Validation Against Real Data

### 5.1 Data Sources

| Source | Use |
|--------|-----|
| NHTSA EDR crash test data | Delta-V accuracy validation |
| NHTSA crash pulse library | Pulse shape validation |
| ISO 11452 test pulses | Sensor response validation |
| SAE J211 instrumentation | Reference standards |

### 5.2 Expected Accuracy

| Metric | Target |
|--------|--------|
| Delta-V error vs reference | < 10% |
| Peak acceleration error | < 15% |
| PDOF error | < 15 degrees |
| Injury risk calibration | Within NHTSA curves |

---

## 6. Performance Benchmarks

### 6.1 Per-Module Timing

| Module | Target (100 samples) |
|--------|---------------------|
| MEMS Simulator | < 1 ms |
| Crash Pulse Generator | < 0.5 ms |
| ESKF (1 step) | < 0.1 ms |
| Detection Cascade | < 5 ms |
| Delta-V Estimation | < 10 ms |
| Audio Pipeline (1s) | < 500 ms |
| Visual Pipeline (burst) | < 5000 ms |
| Evidence Chain (1 record) | < 1 ms |

### 6.2 Throughput

| Scenario | Target |
|----------|--------|
| 1000 crash scenarios | < 300s total |
| Streaming detection (1kHz) | < 1ms per sample |

### 6.3 Memory

| Scenario | Target |
|----------|--------|
| Single simulation | < 50 MB |
| 1000 batch | < 500 MB |
| Audio pipeline (1s, 4ch) | < 200 MB |

---

## 7. Test Execution

### 7.1 Running Tests

```bash
# Unit tests
pytest tests/ -v --tb=short

# With coverage
pytest tests/ --cov=vista_hil --cov-report=html

# Stress tests
pytest tests/comprehensive_stress_test_1000.py -v --timeout=600

# Boundary analysis
pytest tests/boundary_analysis.py -v
```

### 7.2 CI/CD Pipeline

- Every commit: unit tests + linting
- Every PR: unit + integration tests
- Release branches: 1000-scenario stress test
- Monthly: validation against NHTSA data

---

## 8. Quality Gates

### Pre-Commit
- [ ] All unit tests pass
- [ ] No lint errors
- [ ] No type errors

### Pre-Merge
- [ ] Coverage >= 85%
- [ ] Integration tests pass
- [ ] Code review approved

### Pre-Release
- [ ] 1000-scenario stress test: 100% pass
- [ ] Performance benchmarks within targets
- [ ] Validation against real data within accuracy
- [ ] Security review passed

### Production
- [ ] All pre-release gates met
- [ ] Hardware-in-the-loop test on target MCU
- [ ] Fleet simulation with 10+ devices
- [ ] OTA update test passes
