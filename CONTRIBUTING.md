# Contributing to VISTA

## Development Setup

```bash
git clone https://github.com/AdityaPagare619/vista-forensic-evidence.git
cd vista-forensic-evidence
pip install -r requirements.txt
pip install -e .
```

## Running Tests

```bash
# All tests (415+ tests, 99% pass rate)
python -m pytest vista_hil/ -v

# Specific module tests
python -m pytest vista_hil/test_crash_pulse_v2.py -v
python -m pytest vista_hil/test_reconstruction.py -v
python -m pytest vista_hil/test_eskf.py -v

# CISS benchmark (requires NHTSA data)
python benchmarks/run_ciss_benchmark.py
```

## Code Standards

- Python 3.8+
- All public functions must have docstrings
- All new code must have tests
- Follow existing code style
- No external dependencies beyond requirements.txt

## What We're Looking For

- Bug fixes with test coverage
- Performance improvements
- Documentation improvements
- New crash detection algorithms
- Real-world validation data
- Hardware integration contributions
- Translations of documentation
