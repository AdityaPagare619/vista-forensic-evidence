# Contributing to VISTA

## How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all existing tests pass (`python -m pytest vista_hil/ -v`)
5. Submit a pull request

## Development Setup

```bash
git clone https://github.com/AdityaPagare619/vista-forensic-evidence.git
cd vista-forensic-evidence
pip install -r requirements.txt
python -m pytest vista_hil/ -v
```

## Code Standards

- Python 3.8+
- All public functions must have docstrings
- All new code must have tests
- Follow existing code style (PEP 8 where applicable)

## Testing

```bash
# Run all tests
python -m pytest vista_hil/ -v

# Run specific module tests
python -m pytest vista_hil/test_crash_pulse_v2.py -v
python -m pytest vista_hil/test_reconstruction.py -v

# Run CISS benchmark
python benchmarks/run_ciss_benchmark.py
```

## What We're Looking For

- Bug fixes with test coverage
- Performance improvements
- Documentation improvements
- New crash detection algorithms
- Real-world validation data
- Hardware integration contributions
