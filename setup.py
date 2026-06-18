"""
VISTA 2.0 HIL Simulation Package Setup
"""

from setuptools import setup, find_packages

setup(
    name="vista-hil",
    version="2.0.0",
    description="Hardware-in-the-Loop Simulation for VISTA 2.0 Forensic Crash Evidence Framework",
    author="VISTA Research Team",
    author_email="vista-research@example.com",
    url="https://github.com/vista-research/vista-hil",
    license="MIT",
    
    packages=find_packages(),
    python_requires=">=3.8",
    
    install_requires=[
        "numpy>=1.20.0",
        "scipy>=1.7.0",
        "pyyaml>=5.4.0",
    ],
    
    extras_require={
        "hardware": [
            "pyserial>=3.5.0",
            "spidev>=3.5",
        ],
        "visualization": [
            "matplotlib>=3.4.0",
        ],
        "dev": [
            "pytest>=6.2.0",
            "pytest-cov>=2.12.0",
        ],
        "all": [
            "pyserial>=3.5.0",
            "spidev>=3.5",
            "matplotlib>=3.4.0",
            "pytest>=6.2.0",
            "pytest-cov>=2.12.0",
        ],
    },
    
    entry_points={
        "console_scripts": [
            "vista-hil=vista_hil.hil_simulation:main",
        ],
    },
    
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Scientific/Engineering :: Image Recognition",
    ],
    
    keywords="MEMS IMU simulation crash-test hardware-in-the-loop VISTA forensic",
)
