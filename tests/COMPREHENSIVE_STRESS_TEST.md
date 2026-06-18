# VISTA 2.0 — COMPREHENSIVE STRESS TEST REPORT

**Date:** 2026-06-14 20:27:21
**Total Scenarios:** 1035
**Elapsed Time:** 49.7s (21 scenarios/sec)
**Failures:** 0 (FN: 0, FP: 0, Errors: 0)

---
## 1. EXECUTIVE SUMMARY

**Overall Pass Rate:** 1035/1035 (100.0%)

### Crash Detection Performance
| Metric | Value |
|--------|-------|
| Total crash scenarios | 792 |
| True Positives (correctly detected) | 792 (100.0%) |
| **False Negatives (MISSED crashes)** | **0 (0.0%)** |
| **CRITICAL: Missed crash rate** | **0.00%** |

### False Positive Performance
| Metric | Value |
|--------|-------|
| Total non-crash scenarios | 243 |
| True Negatives (correctly not detected) | 243 (100.0%) |
| **False Positives (wrongly detected)** | **0 (0.0%)** |

### Sensor Saturation
| Metric | Value |
|--------|-------|
| Crashes with sensor saturation | 585 |
| Missed crashes due to saturation | 0 |

---
## 2. PASS/FAIL RATES BY DIMENSION

### Detection Rate by Speed (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| 5 | 2 | 2 | 0 | 100.0% |
| 8 | 1 | 1 | 0 | 100.0% |
| 10 | 12 | 12 | 0 | 100.0% |
| 12 | 1 | 1 | 0 | 100.0% |
| 15 | 5 | 5 | 0 | 100.0% |
| 20 | 53 | 53 | 0 | 100.0% |
| 25 | 11 | 11 | 0 | 100.0% |
| 30 | 88 | 88 | 0 | 100.0% |
| 35 | 2 | 2 | 0 | 100.0% |
| 40 | 72 | 72 | 0 | 100.0% |
| 45 | 4 | 4 | 0 | 100.0% |
| 50 | 199 | 199 | 0 | 100.0% |
| 60 | 100 | 100 | 0 | 100.0% |
| 65 | 1 | 1 | 0 | 100.0% |
| 70 | 50 | 50 | 0 | 100.0% |
| 75 | 12 | 12 | 0 | 100.0% |
| 80 | 61 | 61 | 0 | 100.0% |
| 90 | 55 | 55 | 0 | 100.0% |
| 100 | 49 | 49 | 0 | 100.0% |
| 110 | 2 | 2 | 0 | 100.0% |
| 120 | 12 | 12 | 0 | 100.0% |

### Detection Rate by Impact Angle (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| 0 | 512 | 512 | 0 | 100.0% |
| 15 | 18 | 18 | 0 | 100.0% |
| 30 | 36 | 36 | 0 | 100.0% |
| 45 | 31 | 31 | 0 | 100.0% |
| 60 | 39 | 39 | 0 | 100.0% |
| 75 | 12 | 12 | 0 | 100.0% |
| 90 | 118 | 118 | 0 | 100.0% |
| 180 | 26 | 26 | 0 | 100.0% |

### Detection Rate by Vehicle Class (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| motorcycle | 78 | 78 | 0 | 100.0% |
| sedan | 557 | 557 | 0 | 100.0% |
| suv | 99 | 99 | 0 | 100.0% |
| truck | 58 | 58 | 0 | 100.0% |

### Detection Rate by Sensor Type (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| h3lis331dl | 109 | 109 | 0 | 100.0% |
| iam20680hp | 63 | 63 | 0 | 100.0% |
| mpu6050 | 620 | 620 | 0 | 100.0% |

### Detection Rate by Mounting Location (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| dashboard | 86 | 86 | 0 | 100.0% |
| floor_structural | 652 | 652 | 0 | 100.0% |
| seat_rail | 54 | 54 | 0 | 100.0% |

### Detection Rate by Temperature (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| -20 | 25 | 25 | 0 | 100.0% |
| 0 | 7 | 7 | 0 | 100.0% |
| 25 | 731 | 731 | 0 | 100.0% |
| 40 | 4 | 4 | 0 | 100.0% |
| 60 | 25 | 25 | 0 | 100.0% |

### Detection Rate by Road Roughness (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| 0.1 | 5 | 5 | 0 | 100.0% |
| 0.3 | 764 | 764 | 0 | 100.0% |
| 0.5 | 9 | 9 | 0 | 100.0% |
| 0.7 | 4 | 4 | 0 | 100.0% |
| 0.9 | 10 | 10 | 0 | 100.0% |

### Detection Rate by Crash Shape (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| half_sine | 30 | 30 | 0 | 100.0% |
| haversine | 732 | 732 | 0 | 100.0% |
| triangular | 30 | 30 | 0 | 100.0% |

### Detection Rate by Direction (Crash Scenarios)

| Parameter | Total | Detected | Missed/FP | Rate |
|-----------|-------|----------|-----------|------|
| frontal | 731 | 731 | 0 | 100.0% |
| oblique/offset | 13 | 13 | 0 | 100.0% |
| rear | 26 | 26 | 0 | 100.0% |
| side | 22 | 22 | 0 | 100.0% |


---
## 3. FAILURE TAXONOMY (Categorized by Root Cause)


---
## 4. DETAILED FALSE NEGATIVES (Missed Crashes)

Total missed crashes: **0**



---
## 5. DETAILED FALSE POSITIVES (Wrongly Detected)

Total false positives: **0**



---
## 7. RECOMMENDATIONS

| Priority | Area | Recommendation |
|----------|------|----------------|
| **LOW** | Algorithm Enhancement | Consider implementing the full 5-method Detection Cascade (detection_cascade.py) instead of single-method PDTSA. The cascade provides redundancy: Energy Flux, Wavelet, Kurtosis, and Template Matching can catch crashes that PDTSA misses. |
| **LOW** | Sensor Fusion | For production, consider dual-sensor fusion: H3LIS331DL (±400g) for crash detection + MPU6050 (±16g) for reconstruction. The high-g sensor ensures no saturation while the low-g sensor provides better resolution for delta-v calculation. |


### Detailed Recommendations

#### 1. [LOW] Algorithm Enhancement

Consider implementing the full 5-method Detection Cascade (detection_cascade.py) instead of single-method PDTSA. The cascade provides redundancy: Energy Flux, Wavelet, Kurtosis, and Template Matching can catch crashes that PDTSA misses.

#### 2. [LOW] Sensor Fusion

For production, consider dual-sensor fusion: H3LIS331DL (±400g) for crash detection + MPU6050 (±16g) for reconstruction. The high-g sensor ensures no saturation while the low-g sensor provides better resolution for delta-v calculation.


---
## 8. CONFIDENCE ASSESSMENT

### Test Coverage Confidence

| Dimension | Values Tested | Coverage | Confidence |
|-----------|---------------|----------|------------|
| Speed | 14 values (5–120 km/h) | Full range | HIGH |
| Impact angle | 7 values (0–90°) | Full range | HIGH |
| Overlap | 4 values (25–100%) | Full range | HIGH |
| Vehicle class | 4 types | All major classes | HIGH |
| Temperature | 5 values (-20–60°C) | Full range | HIGH |
| Sensor | 3 types | All available sensors | HIGH |
| Mounting | 3 locations | All available mounts | HIGH |
| Road roughness | 5 levels (0.1–0.9) | Full range | HIGH |
| Crash shape | 3 types | Haversine, half-sine, triangular | MEDIUM |
| Non-crash events | 17 categories | Comprehensive | HIGH |

### Overall Confidence

- **Detection rate confidence:** HIGH (0/792 missed = 0.0%)
- **False positive confidence:** HIGH (0/243 false alarms = 0.0%)
- **Test volume confidence:** HIGH (1035 scenarios)

---
## 9. TEST LIMITATIONS

1. **Simulation vs. Real-World:** This test uses parametric crash pulse models, not real crash data. Real crashes have complex, multi-modal acceleration profiles that may differ from haversine/half-sine/triangular models.
2. **Single Sensor Location:** The test assumes a single sensor. Real vehicles may have multiple sensors providing redundancy.
3. **No OBD/Audio Integration:** The confidence scoring does not include OBD speed drop or audio classification bonuses.
4. **Streaming vs. Batch:** The test runs in batch mode. Real-time streaming detection may have different latency characteristics.
5. **Crash Shape Limitation:** Only 3 pulse shapes tested. Real crashes may have more complex profiles (e.g., multi-peak, asymmetric).

---
## 10. APPENDIX: SCENARIO COUNTS

| Category | Count |
|----------|-------|
| Total scenarios | 1035 |
| Crash scenarios | 792 |
| Non-crash scenarios | 243 |
| **Correct results** | **1035** |
| **Failed results** | **0** |
| False negatives (missed crashes) | 0 |
| False positives (false alarms) | 0 |
| Simulation errors | 0 |
| **Overall pass rate** | **100.0%** |

---
*Report generated by VISTA 2.0 Comprehensive Stress Test*