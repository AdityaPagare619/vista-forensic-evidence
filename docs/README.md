# VISTA 2.0 — Documentation Index
**Version:** 2.0.0 | **Date:** 2026-06-14

---

## Documentation Structure

```
docs/
├── README.md                          ← This file
├── architecture/
│   └── SYSTEM_ARCHITECTURE.md         ← 8-layer architecture, interfaces, data flows
├── testing/
│   └── TESTING_DOCUMENT.md            ← 415 unit + 14 integration + 1035 stress tests
├── api/
│   └── API_REFERENCE.md               ← Every public function, every parameter
├── deployment/
│   └── DEPLOYMENT_GUIDE.md            ← BOM, assembly, calibration, troubleshooting
├── formulas/
│   └── FORMULA_CATALOG.md             ← Every formula with physical interpretation
├── ADR/
│   ├── ADR-001-ESKF-over-Madgwick.md  ← Why ESKF, not Madgwick
│   ├── ADR-002-5-Method-Detection.md  ← Why 5 detectors, not 1
│   ├── ADR-003-Dual-Hashing.md        ← Why SHA-256 + SHA-3
│   ├── ADR-004-Dempster-Shafer.md     ← Why DS over Bayesian
│   └── ADR-005-Vehicle-Transfer.md    ← Why transfer function is critical
└── paper/
    └── VISTA2.0_PAPER_SKELETON.tex    ← LaTeX skeleton with all formulas
```

## Quick Reference

| Document | Purpose | Audience |
|----------|---------|----------|
| System Architecture | Complete system design | Engineers, architects |
| Testing Document | All tests, results, methodology | QA, reviewers |
| API Reference | Module interfaces | Developers |
| Deployment Guide | Hardware assembly, calibration | Field engineers |
| Formula Catalog | Every formula with physics | Researchers, reviewers |
| ADR Collection | Design decisions and rationale | Architects, decision-makers |
| Paper Skeleton | LaTeX template with formulas | Paper writers |

## Reading Order

1. **README.md** (this file) — overview
2. **SYSTEM_ARCHITECTURE.md** — understand the system
3. **FORMULA_CATALOG.md** — understand the math
4. **TESTING_DOCUMENT.md** — understand what's been validated
5. **API_REFERENCE.md** — understand how to use it
6. **DEPLOYMENT_GUIDE.md** — understand how to deploy it
7. **ADR/** — understand why decisions were made
8. **paper/VISTA2.0_PAPER_SKELETON.tex** — write the paper

---

*All documentation is extracted from the actual source code and test results. No documentation is aspirational or fabricated.*
