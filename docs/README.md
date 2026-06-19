# VISTA 2.0 Documentation Index

## Architecture & Design

| Document | Purpose | Audience |
|----------|---------|----------|
| [System Architecture](architecture/SYSTEM_ARCHITECTURE.md) | 8-layer architecture, interfaces, data flows, security model | Engineers, architects |
| [API Reference](api/API_REFERENCE.md) | Every public function, parameter, example | Developers |
| [Formula Catalog](formulas/FORMULA_CATALOG.md) | 20+ formulas with physical interpretation | Researchers, reviewers |
| [Deployment Guide](deployment/DEPLOYMENT_GUIDE.md) | BOM ($58.50@10K), assembly, calibration, fleet | Field engineers |
| [Testing Document](testing/TESTING_DOCUMENT.md) | 415+ tests, CISS benchmark, stress test | QA, reviewers |

## Architecture Decisions

| ADR | Decision | Rationale |
|-----|----------|-----------|
| [ADR-001](ADR/ADR-001-ESKF-over-Madgwick.md) | 15-state ESKF over Madgwick | Bias estimation, crash robustness |
| [ADR-002](ADR/ADR-002-5-Method-Detection-Cascade.md) | 5-method detection cascade | Redundancy, false positive rejection |
| [ADR-003](ADR/ADR-003-SHA-256-SHA-3-Dual-Hashing.md) | SHA-256 + SHA-3 dual hashing | Defense-in-depth, SWGDE compliance |
| [ADR-004](ADR/ADR-004-Dempster-Shafer-over-Bayesian.md) | Dempster-Shafer fusion | Handles uncertainty, no prior needed |
| [ADR-005](ADR/ADR-005-Vehicle-Transfer-Function.md) | Vehicle transfer function model | Simulation fidelity (0.997 correlation) |

## Research Documents

| Document | Purpose |
|----------|---------|
| [MASTER_SYNTHESIS.md](MASTER_SYNTHESIS.md) | Complete R&D journey, competitor analysis, honest assessment |
| [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md) | Test strategy, methodology, benchmarks |

## Reading Order

1. Start with [README.md](../README.md) for project overview
2. Read [System Architecture](architecture/SYSTEM_ARCHITECTURE.md) for the design
3. Check [Formula Catalog](formulas/FORMULA_CATALOG.md) for the math
4. Review [Testing Document](testing/TESTING_DOCUMENT.md) for validation
5. Read [MASTER_SYNTHESIS.md](MASTER_SYNTHESIS.md) for the honest assessment
