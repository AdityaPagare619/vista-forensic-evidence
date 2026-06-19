# VISTA: Self-Verifying Crash Forensic Evidence Framework

> A seven-layer IoT forensic evidence architecture for autonomous crash detection, severity reconstruction, and tamper-evident evidence packaging on consumer embedded hardware. Validated on real NHTSA CISS 2024 crash data.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![IJVSS Submitted](https://img.shields.io/badge/IJVSS-Submitted-green.svg)](#)
[![Tests 415+](https://img.shields.io/badge/Tests-415%2B-passing-brightgreen.svg)](#testing)

---

## What VISTA Is

VISTA is a **forensic evidence pipeline** — not a crash detector. It autonomously detects crash events, reconstructs impact severity with quantified uncertainty, corroborates with multi-modal sensor data (inertial + diagnostic + acoustic + visual), and packages everything in a cryptographically self-verifiable format.

**Key result:** On 499 real NHTSA CISS 2024 crash cases, VISTA achieves **95.6% detection rate** and **13.09 km/h delta-V MAE** (95% CI: 11.99–14.16 km/h).

**Why it matters:** Professional EDR retrieval costs $15,000+ and requires trained operators. Consumer smartphone detection produces unvalidated severity estimates. VISTA automates the entire forensic evidence pipeline — from crash detection to cryptographically sealed evidence package — on a USD 55 embedded platform.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Sensor Acquisition                                     │
│  ├── Triple IMU (2× IAM-20680HP + 1× H3LIS331DL)               │
│  ├── CAN bus (TJA1050 direct, not ELM327)                       │
│  ├── 4× MEMS microphone array (48kHz)                           │
│  └── Camera (Sony IMX678 STARVIS 2)                             │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Signal Processing                                      │
│  ├── 63-tap FIR anti-alias filter (Kaiser, fc=100Hz)            │
│  ├── Error-State Kalman Filter (15-state, quaternion)            │
│  └── RTS backward smoother (forensic accuracy)                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Detection Cascade                                      │
│  ├── 3g acceleration gate (eliminates vibration FP)             │
│  ├── 5-method fusion: PDTSA + Energy + WPD + Kurtosis + Template│
│  ├── Weighted scoring with saturation override                   │
│  └── Result: 95.6% detection, 0% false positives (200 scenarios)│
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Reconstruction                                         │
│  ├── Delta-V with restitution correction                         │
│  ├── PDOF estimation (Kusano & Gabler method)                    │
│  ├── NHTSA injury probability curves                             │
│  └── 5-phase velocity history decomposition                     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 5: Audio Forensics (6-stage pipeline)                    │
│  ├── Impulse detection (±0.1ms)                                  │
│  ├── 12-class crash-specific classification                     │
│  ├── MVDR beamforming for source separation                      │
│  ├── GCC-PHAT temporal alignment (±0.1ms)                       │
│  └── SHA-256 + HMAC forensic chain                              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 6: Visual Analytics                                       │
│  ├── Multi-camera capture (4K front, 2K rear)                   │
│  ├── Burst capture (60fps, 2 seconds)                           │
│  ├── Key frame detection and evidence packaging                 │
│  └── Image quality assessment                                    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 7: Evidence Integrity                                     │
│  ├── SHA-256 + SHA-3 dual hashing                               │
│  ├── HMAC-SHA256 signatures                                      │
│  ├── Deterministic JSON serialization                            │
│  └── stdlib-only verification (Python hashlib/hmac)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# Install
pip install -r requirements.txt
pip install -e .

# Run tests (415+ tests, 99% pass rate)
python -m pytest vista_hil/ -v

# Run CISS benchmark on real NHTSA data
python benchmarks/run_ciss_benchmark.py

# Generate publication charts
python benchmarks/generate_all_charts.py
```

---

## Validation Results

### Real CISS 2024 Data (499 cases)

| Metric | Value |
|--------|-------|
| Detection Rate | 95.6% |
| Delta-V MAE | 13.09 km/h |
| 95% Bootstrap CI | [11.99, 14.16] km/h |
| RMSE | 17.87 km/h |
| Systematic Bias | +7.31 km/h |
| Median Absolute Error | 10.30 km/h |

### Simulation Validation

| Metric | Result |
|--------|--------|
| Crash pulse correlation | 0.997 (vs published data) |
| Vehicle transfer function | Validated |
| MEMS sensor model | Validated |

---

## Project Structure

```
vista-forensic-evidence/
├── vista_hil/                    # Core Python modules (23 files)
│   ├── pdtsa_v2.py              # PDTSA crash detection
│   ├── detection_cascade.py     # 5-method detection fusion
│   ├── eskf.py                  # Error-State Kalman Filter
│   ├── reconstruction.py        # Delta-V, PDOF, injury risk
│   ├── audio_pipeline.py        # 6-stage audio forensics
│   ├── visual_pipeline.py       # Multi-camera analytics
│   ├── evidence_chain.py        # SHA-256 + SHA-3 + HMAC
│   ├── deployment.py            # Fleet management
│   ├── mems_simulator.py        # MEMS sensor simulation
│   ├── crash_pulse_v2.py        # Multi-peak crash pulses
│   ├── realistic_simulation.py  # Vehicle transfer function
│   ├── hil_simulation.py        # HIL simulation loop
│   ├── stress_test.py           # 200-scenario stress test
│   └── test_*.py               # 415+ automated tests
├── firmware/                     # STM32H743 C firmware (16 files)
├── sensors/                      # Sensor YAML configs (3 files)
├── benchmarks/                   # CISS validation scripts + results
├── docs/                         # Architecture, API, formulas, deployment
│   ├── architecture/            # System architecture document
│   ├── api/                     # API reference
│   ├── formulas/                # Formula catalog with physics
│   ├── deployment/              # Deployment guide
│   ├── testing/                 # Testing document
│   └── ADR/                     # 5 architecture decisions
├── tests/                        # Stress test + validation reports
├── requirements.txt
├── setup.py
├── LICENSE
└── CONTRIBUTING.md
```

---

## Test Results

| Module | Tests | Status |
|--------|-------|--------|
| Crash Pulse v2 | 31 | ✅ |
| Reconstruction | 43 | ✅ |
| Detection Cascade | 19 | ✅ |
| Audio Pipeline | 59 | ✅ |
| Visual Analytics | 71 | ✅ |
| Evidence Chain | 19 | ✅ |
| Deployment | 104 | ✅ |
| ESKF | 23 | 22/23 |
| **Total** | **415+** | **99% pass** |

---

## Documentation

| Document | Description |
|----------|-------------|
| [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) | 8-layer architecture, interfaces, data flows |
| [API Reference](docs/api/API_REFERENCE.md) | Every public function, parameter, example |
| [Formula Catalog](docs/formulas/FORMULA_CATALOG.md) | 20+ formulas with physical interpretation |
| [Deployment Guide](docs/deployment/DEPLOYMENT_GUIDE.md) | BOM, assembly, calibration, fleet |
| [Testing Document](docs/testing/TESTING_DOCUMENT.md) | Complete test inventory |
| [Architecture Decisions](docs/ADR/) | 5 ADRs with rationale |

---

## Research

- **Paper:** Submitted to IJVSS "VISTA: Self-Verifying Crash Forensics on Consumer Embedded Hardware"
- **Benchmark:** CrashBench — standardized evaluation using real NHTSA CISS 2024 data
- **Data:** NHTSA CISS 2024 (public, accessed via NHTSA FTP)

---

## License

[MIT License](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.
