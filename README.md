# VISTA: Self-Verifying Crash Forensics on Consumer Embedded Hardware

**Vehicle Intelligence and Safety Telematics Architecture**

A seven-layer IoT forensic crash evidence framework for autonomous crash detection, severity reconstruction, and tamper-evident evidence packaging on consumer embedded hardware.

---

## What VISTA Is

VISTA is a forensic evidence pipeline — not a crash detector. It autonomously detects crash events, reconstructs impact severity with quantified uncertainty, corroborates with multi-modal sensor data, and packages everything in a cryptographically self-verifiable format that any investigator can authenticate without proprietary software.

**Key result:** On 499 real NHTSA CISS 2024 crash cases, VISTA achieves 95.6% detection rate and 13.09 km/h delta-V MAE (95% CI: 11.99-14.16 km/h).

---

## Architecture

```
Layer 1: Sensor Acquisition  →  IMU ×3, OBD-II, MEMS mic ×4, Camera
Layer 2: Signal Processing    →  FIR filter, ESKF, RTS smoother
Layer 3: Detection Cascade    →  5-method fusion (PDTSA + Energy + WPD + Kurtosis + Template)
Layer 4: Reconstruction       →  Delta-V, PDOF, injury risk, velocity history
Layer 5: Audio Forensics      →  6-stage pipeline (impulse → classification → alignment → chain)
Layer 6: Visual Analytics     →  Multi-camera, burst capture, evidence packaging
Layer 7: Evidence Integrity   →  SHA-256 + SHA-3 + HMAC, stdlib-only verification
Layer 8: Deployment           →  Fleet management, telemetry, OTA updates
```

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the integration test
python -m pytest vista_hil/test_crash_pulse_v2.py -v

# Run the CISS benchmark
python benchmarks/run_ciss_benchmark.py

# Generate benchmark charts
python benchmarks/generate_all_charts.py
```

---

## Project Structure

```
vista-forensics/
├── vista_hil/                  # Core Python modules
│   ├── pdtsa_v2.py            # PDTSA crash detection
│   ├── reconstruction.py      # Delta-V, PDOF, injury risk
│   ├── detection_cascade.py   # 5-method detection fusion
│   ├── eskf.py                # Error-State Kalman Filter
│   ├── audio_pipeline.py      # 6-stage audio forensics
│   ├── visual_pipeline.py     # Multi-camera analytics
│   ├── evidence_chain.py      # SHA-256 + SHA-3 + HMAC
│   ├── deployment.py          # Fleet management
│   ├── mems_simulator.py      # MEMS sensor simulation
│   ├── crash_pulse_v2.py      # Multi-peak crash pulses
│   ├── realistic_simulation.py # Vehicle transfer function
│   ├── hil_simulation.py      # HIL simulation loop
│   └── test_*.py              # 415+ tests
├── firmware/                   # STM32H743 C firmware skeleton
│   ├── include/               # 6 header files
│   ├── src/                   # 7 source files
│   └── Makefile               # ARM cross-compilation
├── sensors/                    # Sensor YAML configs
│   ├── mpu6050.yaml
│   ├── h3lis331dl.yaml
│   └── iam20680hp.yaml
├── benchmarks/                 # CISS validation
│   ├── run_ciss_benchmark.py  # Real CISS data processing
│   └── generate_all_charts.py # Publication charts
├── docs/                       # Documentation suite
│   ├── architecture/          # System architecture
│   ├── api/                   # API reference
│   ├── formulas/              # Formula catalog
│   ├── deployment/            # Deployment guide
│   ├── testing/               # Testing document
│   └── ADR/                   # Architecture decisions
├── requirements.txt
└── setup.py
```

---

## Test Results

| Module | Tests | Status |
|--------|-------|--------|
| Crash Pulse v2 | 31 | ✅ All pass |
| Reconstruction | 43 | ✅ All pass |
| Detection Cascade | 19 | ✅ All pass |
| Audio Pipeline | 59 | ✅ All pass |
| Visual Analytics | 71 | ✅ All pass |
| Evidence Chain | 19 | ✅ All pass |
| Deployment | 104 | ✅ All pass |
| ESKF | 23 | 22/23 (known physics limitation) |
| **Total** | **415+** | **99% pass rate** |

---

## Validation Results

**Real CISS 2024 Data (499 cases):**
- Detection Rate: 95.6%
- Delta-V MAE: 13.09 km/h
- 95% CI: [11.99, 14.16] km/h
- RMSE: 17.87 km/h
- Bias: +7.31 km/h

**Simulation Validation:**
- Crash pulse correlation with published data: 0.997
- Vehicle transfer function: validated
- MEMS sensor model: validated

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/architecture/SYSTEM_ARCHITECTURE.md` | 8-layer architecture, interfaces, data flows |
| `docs/api/API_REFERENCE.md` | Every public function and parameter |
| `docs/formulas/FORMULA_CATALOG.md` | All formulas with physical interpretation |
| `docs/testing/TESTING_DOCUMENT.md` | Complete test inventory |
| `docs/deployment/DEPLOYMENT_GUIDE.md` | Assembly, calibration, fleet setup |
| `docs/ADR/` | 5 architecture decision records |

---

## Research Publications

- **Paper Submitted:** IJVSS "VISTA: Self-Verifying Crash Forensics on Consumer Embedded Hardware"
- **Benchmark:** CrashBench — standardized evaluation using real NHTSA CISS 2024 data

---

## License

MIT License — see LICENSE file for details.

---

## Contact

For questions, issues, or collaboration:
- Project: VISTA Forensic Evidence
- Focus: Road safety, insurance, fleet management
