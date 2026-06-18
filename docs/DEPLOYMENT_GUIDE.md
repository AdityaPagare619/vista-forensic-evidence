# VISTA 2.0 Deployment Guide

**Version:** 2.0.0  
**Date:** 2026-06-14  
**Status:** Production Reference

---

## Table of Contents

1. [Software Requirements](#1-software-requirements)
2. [Build Instructions](#2-build-instructions)
3. [Hardware Assembly](#3-hardware-assembly)
4. [Calibration Procedure](#4-calibration-procedure)
5. [Field Installation](#5-field-installation)
6. [Troubleshooting](#6-troubleshooting)
7. [Fleet Deployment](#7-fleet-deployment)
8. [Maintenance](#8-maintenance)

---

## 1. Software Requirements

### 1.1 Development Environment

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | >= 3.8 | Core runtime |
| NumPy | >= 1.20.0 | Numerical computation |
| SciPy | >= 1.7.0 | Signal processing (filters, FFT) |
| PyYAML | >= 5.4.0 | Sensor configuration loading |

### 1.2 Optional Dependencies

| Component | Version | Purpose |
|-----------|---------|---------|
| matplotlib | >= 3.4.0 | Visualization and plotting |
| pytest | >= 6.2.0 | Test runner |
| pytest-cov | >= 2.12.0 | Coverage reporting |
| pyserial | >= 3.5.0 | USB serial to RPi4 |
| spidev | >= 3.5 | SPI communication with STM32 |

### 1.3 Hardware Interface Software

| Component | Purpose | Notes |
|-----------|---------|-------|
| STM32CubeIDE | Firmware development | Free from STMicroelectronics |
| STM32H7 HAL | Hardware abstraction layer | Included with CubeIDE |
| ARM GCC Toolchain | Cross-compilation | arm-none-eabi-gcc >= 10.3 |
| OpenOCD | On-chip debugging | For SWD programming |

### 1.4 Embedded Firmware

| Component | File | Purpose |
|-----------|------|---------|
| ESKF implementation | `firmware/src/eskf.c` | 15-state error-state Kalman filter |
| Crash detection | `firmware/src/detection.c` | 5-method cascade |
| Evidence chain | `firmware/src/evidence.c` | SHA-256 + HMAC |
| IMU interface | `firmware/src/imu_interface.c` | SPI/I2C sensor driver |
| FRAM storage | `firmware/src/fram_storage.c` | Non-volatile evidence storage |
| Crash state machine | `firmware/src/crash_state_machine.c` | State transitions |

---

## 2. Build Instructions

### 2.1 Python Package (HIL Simulation)

```bash
# Clone repository
git clone https://github.com/vista-research/vista-hil.git
cd vista-hil

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .

# Install with all extras (hardware + visualization + dev)
pip install -e ".[all]"
```

### 2.2 Verify Installation

```bash
# Run installation test
python test_installation.py

# Run self-tests for each module
python -m vista_hil.mems_simulator
python -m vista_hil.crash_pulse
python -m vista_hil.evidence_chain
python -m vista_hil.detection_cascade
python -m vista_hil.visual_pipeline
python -m vista_hil.deployment
```

### 2.3 STM32 Firmware Build

```bash
cd firmware/

# Build with make
make clean
make all

# Build with CubeIDE
# Import project into STM32CubeIDE
# Project -> Build All

# Flash via ST-Link
make flash

# Flash via OpenOCD
openocd -f interface/stlink.cfg -f target/stm32h7x.cfg \
  -c "program build/vista_firmware.elf verify reset exit"
```

### 2.4 Cross-Platform Notes

| Platform | Notes |
|----------|-------|
| Linux (Ubuntu 20.04+) | Full support. Use system Python or conda. |
| macOS (11+) | Full support. Use Homebrew Python. |
| Windows (10+) | Full support. Use PowerShell or WSL. |
| Google Colab | Supported. `!pip install numpy scipy pyyaml` |
| Raspberry Pi (4/5) | Supported for deployment. Use ARM64 builds. |

---

## 3. Hardware Assembly

### 3.1 Bill of Materials

| Component | Model | Qty | Est. Cost (USD) |
|-----------|-------|-----|-----------------|
| MCU | STM32H743VITx | 1 | $15 |
| IMU (primary) | H3LIS331DL breakout | 1 | $8 |
| IMU (reference) | MPU6050 breakout | 1 | $3 |
| Accelerometer (high-g) | H3LIS331DL (400g) | 1 | $8 |
| Microphone array | 4x Infineon IM67D130A | 1 | $12 |
| Camera (front) | OV5640 4K module | 1 | $25 |
| Camera (rear) | OV2640 2K module | 1 | $10 |
| FRAM | FM25V20A (256KB) | 1 | $5 |
| SD Card | 32GB microSD | 1 | $8 |
| GPS Module | u-blox MAX-M10S | 1 | $20 |
| CAN Transceiver | TJA1050 | 1 | $2 |
| Power Supply | 12V to 5V/3.3V buck | 1 | $8 |
| PCB (custom) | 4-layer, 50x50mm | 1 | $15 |
| Enclosure | IP67 rated | 1 | $10 |
| Connectors | JST-SH, header pins | - | $5 |
| **Total** | | | **~$154** |

### 3.2 PCB Assembly

1. **Component Placement (Order):**
   - STM32H743 (center)
   - Power supply section (input protection, buck converter)
   - IMU sensors (near mounting holes for vibration coupling)
   - Microphone array (edge, away from power supply)
   - Camera connectors (FPC)
   - FRAM (near SPI bus)
   - SD card slot (edge for access)
   - GPS module (edge for antenna)
   - CAN transceiver (near connector)

2. **Critical Layout Rules:**
   - IMU ground plane: solid, no cuts under sensor
   - Decoupling caps: 100nF + 10uF on every VDD pin
   - SPI traces: matched length, < 50mm
   - I2C pullups: 4.7k to 3.3V
   - Analog ground: separated from digital, single-point connection

### 3.3 Wiring Diagram

```
STM32H743
  |
  +-- SPI1 --> H3LIS331DL (accel)
  |            SCK=PA5, MISO=PA6, MOSI=PA7, CS=PA4
  |
  +-- I2C1 --> MPU6050 (gyro+accel)
  |            SCL=PB8, SDA=PB9
  |
  +-- SPI2 --> FRAM (evidence storage)
  |            SCK=PB13, MISO=PB14, MOSI=PB15, CS=PB12
  |
  +-- SDMMC1 --> microSD (data logging)
  |               CLK=PC12, CMD=PD2, D0=PC8
  |
  +-- UART1 --> GPS (u-blox)
  |             TX=PA9, RX=PA10
  |
  +-- CAN1 --> Vehicle OBD-II
  |            TX=PB9, RX=PB8 (via TJA1050)
  |
  +-- I2S2 --> MEMS Microphones
  |            SCK=PB13, WS=PB12, SD=PB15
  |
  +-- DCMI --> Camera (OV5640)
  |            D0-D7, VSYNC, HREF, PCLK
  |
  +-- USB --> Host PC (HIL interface)
              PA11(D-), PA12(D+)
```

### 3.4 Assembly Verification

```bash
# Flash test firmware
make flash TEST=1

# Verify IMU communication
./vista_tool --scan-i2c
# Expected: MPU6050 at 0x68

./vista_tool --scan-spi
# Expected: H3LIS331DL on SPI1, FRAM on SPI2

# Verify sensor readout
./vista_tool --read-imu --duration 5
# Expected: ~1g on Z-axis, noise < 0.1g

# Verify evidence chain
./vista_tool --test-evidence
# Expected: SHA-256 + HMAC verification pass
```

---

## 4. Calibration Procedure

### 4.1 IMU Calibration (Factory)

**Purpose:** Determine factory offset and cross-axis sensitivity matrix.

**Equipment:**
- Precision rotation stage (optional)
- Known temperature environment (25C reference)
- 6 positions for 6-position calibration

**Procedure:**

1. **6-Position Static Calibration:**
   ```
   Place sensor in each orientation:
   +X, -X, +Y, -Y, +Z, -Z
   
   Record 1000 samples at each position.
   
   offset_x = (mean(+X) - mean(-X)) / 2
   offset_y = (mean(+Y) - mean(-Y)) / 2
   offset_z = (mean(+Z) - mean(-Z)) / 2 - g
   
   scale_x = g / ((mean(+X) - mean(-X)) / 2)
   scale_y = g / ((mean(+Y) - mean(-Y)) / 2)
   scale_z = g / ((mean(+Z) - mean(-Z)) / 2)
   ```

2. **Cross-Axis Matrix:**
   ```
   M = [[scale_x,  0,        0       ],
        [0,         scale_y,  0       ],
        [0,         0,        scale_z ]]
   
   # Apply rotation correction if axes not perfectly aligned
   # M = S * R (scale * rotation)
   ```

3. **Write to Configuration:**
   ```python
   # Update sensor YAML
   calibration:
     factory_offset:
       accel: [offset_x, offset_y, offset_z]
     cross_axis:
       matrix: [[M[0,0], M[0,1], M[0,2]],
                [M[1,0], M[1,1], M[1,2]],
                [M[2,0], M[2,1], M[2,2]]]
   ```

### 4.2 Noise Characterization

**Purpose:** Measure noise density for Allan variance.

**Procedure:**

1. Record 10,000 samples at 1kHz in static environment
2. Compute Allan variance:
   ```python
   def allan_variance(data, fs):
       tau = np.arange(1, len(data)//2) / fs
       avar = np.zeros(len(tau))
       for i, t in enumerate(tau):
           n = int(t * fs)
           chunks = len(data) // n
           means = [np.mean(data[j*n:(j+1)*n]) for j in range(chunks)]
           avar[i] = 0.5 * np.mean(np.diff(means)**2)
       return tau, avar
   ```
3. Find minimum of Allan variance curve → bias instability
4. Find slope = -1/2 region → angle random walk (noise density)

### 4.3 Temperature Calibration

**Purpose:** Determine temperature sensitivity coefficients.

**Procedure:**

1. Place sensor in thermal chamber
2. Cycle through: -20C, 0C, 25C, 50C, 85C
3. Record offset at each temperature
4. Fit linear model: `offset(T) = offset_0 + coeff * (T - T_ref)`
5. `temp_sensitivity_coeff` and `temp_offset_coeff` are the fitted parameters

### 4.4 Vehicle Transfer Function Calibration

**Purpose:** Determine vehicle-specific VTF parameters.

**Procedure:**

1. Mount VISTA unit at target location
2. Mount reference accelerometer at impact point (bumper)
3. Conduct low-speed impact tests (10, 20, 30 km/h)
4. Compare frequency content between reference and VISTA
5. Fit 2nd-order transfer function to measured frequency response
6. Extract natural frequency and damping ratio

---

## 5. Field Installation

### 5.1 Mounting Location Selection

| Location | Pros | Cons | Recommended |
|----------|------|------|-------------|
| Floor structural | Direct coupling, minimal filtering | Hard to access | Primary choice |
| Under seat | Protected, central | Some seat damping | Alternative |
| Dashboard | Easy access, visible | High filtering, vibration | Not recommended |
| ACM location | Reference quality | Requires OEM integration | Gold standard |

### 5.2 Mechanical Mounting

1. **Surface Preparation:**
   - Clean mounting surface with isopropyl alcohol
   - Ensure flat contact (no gaps > 0.5mm)
   - Apply threadlocker to screws

2. **Mounting Hardware:**
   - M4 bolts with vibration-resistant washers
   - Rubber grommets for vibration isolation (if needed)
   - Cable ties for strain relief

3. **Orientation:**
   - Align X-axis with vehicle forward direction
   - Align Z-axis with vehicle vertical (up)
   - Verify with 1g gravity reading on Z-axis

### 5.3 Electrical Connections

1. **Power:**
   - Connect to 12V accessory line (switched with ignition)
   - Verify 5V and 3.3V rails with multimeter
   - Check current draw: < 500mA typical

2. **CAN Bus:**
   - Connect to vehicle OBD-II port (CAN-H, CAN-L)
   - Verify CAN communication at 500kbps
   - Decode vehicle speed messages

3. **GPS Antenna:**
   - Mount antenna with clear sky view
   - Route cable away from power lines
   - Verify fix within 60 seconds outdoors

### 5.4 Post-Installation Verification

```bash
# Connect to VISTA unit via USB
vista_tool --status

# Expected output:
# MCU: STM32H743 OK
# IMU: H3LIS331DL OK (SPI1)
# Gyro: MPU6050 OK (I2C1)
# FRAM: FM25V20A OK (SPI2)
# SD: 32GB OK
# GPS: Fix acquired (3D)
# CAN: Connected (500kbps)
# Evidence Chain: Initialized, sequence=0

# Verify sensor readings
vista_tool --read-imu --duration 10 --output csv
# Check: Z-axis ~9.81 m/s², noise < 0.5 m/s²

# Verify evidence chain
vista_tool --test-evidence
# Expected: SHA-256 OK, SHA-3 OK, HMAC OK

# Verify detection system
vista_tool --test-detection
# Expected: Cascade configured, 5 detectors active
```

---

## 6. Troubleshooting

### 6.1 Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| IMU not responding | No data from SPI/I2C | Check wiring, verify CS pin, check power |
| GPS no fix | No satellite lock | Check antenna connection, ensure sky view |
| CAN bus errors | Frame errors in log | Verify baudrate (500kbps), check termination |
| SD card write error | "No space" or I/O error | Format FAT32, check card health |
| High noise floor | Std dev > 1g at rest | Verify mounting, check power supply ripple |
| False detections | Detects during braking | Adjust cascade weights, increase gate threshold |
| Evidence verification fails | HMAC mismatch | Verify shared_secret matches across devices |
| OTA update fails | Stuck in DOWNLOADING | Check network, verify package checksum |

### 6.2 Diagnostic Commands

```bash
# Full system diagnostic
vista_tool --diagnose

# IMU raw data dump
vista_tool --dump-imu --duration 5 --output raw.csv

# Evidence chain status
vista_tool --evidence-status

# Fleet registration check
vista_tool --fleet-check

# Firmware version
vista_tool --version
# Expected: VISTA-2.0.0 build <hash>

# Memory usage
vista_tool --memory-status
# Expected: Free > 50%, No fragmentation

# Temperature monitoring
vista_tool --temperature
# Expected: MCU < 70C, IMU < 85C
```

### 6.3 Log Analysis

```bash
# Collect logs
vista_tool --export-logs --output logs.zip

# Key log files:
# - /var/log/vista/detection.log    (detection events)
# - /var/log/vista/evidence.log     (evidence chain operations)
# - /var/log/vista/telemetry.log    (sensor data summary)
# - /var/log/vista/system.log       (system health)
```

### 6.4 Performance Degradation

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| Detection latency > 10ms | CPU overloaded | Reduce sampling rate, optimize code |
| Evidence chain gaps | FRAM full | Clear old evidence, increase storage |
| GPS drift | Multipath in urban canyon | Use differential GPS, fuse with CAN speed |
| Memory leak | Evidence records not freed | Restart device, update firmware |

---

## 7. Fleet Deployment

### 7.1 Fleet Registration

```python
from vista_hil.deployment import FleetManager

fleet = FleetManager(shared_secret=b"your-production-secret-32b!")

# Register devices
for device_seed in device_seeds:
    identity = fleet.register_device(device_seed)
    print(f"Registered: {identity.device_id}")
    # Flash this device_id to the physical device
```

### 7.2 Telemetry Monitoring

```python
# Process heartbeats
fleet.process_heartbeat(device_id, {
    TelemetryType.BATTERY_PCT: 85.0,
    TelemetryType.SPEED_KMH: 60.0,
    TelemetryType.CPU_TEMP_C: 45.0,
    TelemetryType.STORAGE_FREE_GB: 25.0,
})

# Check health
alerts = fleet.health.get_alerts(unacknowledged_only=True)
for alert in alerts:
    print(f"[{alert.severity.value}] {alert.device_id}: {alert.message}")
```

### 7.3 OTA Updates

```python
# Create update package
with open("firmware_v2.1.0.bin", "rb") as f:
    fw_data = f.read()

package = fleet.ota.create_package(
    version="2.1.0",
    description="Bug fix: detection latency improvement",
    firmware_data=fw_data,
)

# Schedule for specific devices
for device_id in target_devices:
    fleet.ota.schedule_update(device_id, package.package_id)

# Monitor progress
pending = fleet.ota.get_pending_updates()
print(f"Pending updates: {len(pending)}")
```

### 7.4 Evidence Chain Verification

```python
# Verify a device's evidence chain
result = fleet.evidence.verify_chain(device_id)
if result["valid"]:
    print(f"Chain valid: {result['record_count']} records")
else:
    print(f"Chain INVALID: {result['errors']}")
```

---

## 8. Maintenance

### 8.1 Regular Checks (Monthly)

| Check | Method | Criteria |
|-------|--------|----------|
| Sensor health | Read IMU, check noise floor | Std dev < 0.5g |
| Storage capacity | Check SD/FRAM usage | Free > 20% |
| Battery level | Telemetry query | > 20% |
| Evidence chain | Verify chain integrity | All valid |
| Firmware version | Query device | Latest stable |
| GPS accuracy | Compare with known position | Error < 10m |

### 8.2 Firmware Updates

1. Create OTA package (see Section 7.3)
2. Schedule update during low-activity period
3. Monitor update progress
4. Verify post-update functionality
5. Rollback if issues detected

### 8.3 Data Management

- **Evidence retention:** Store crash evidence for minimum 7 years (legal requirement)
- **Telemetry retention:** 90 days rolling window
- **Log retention:** 30 days rolling window
- **Backup:** Nightly backup of evidence chain to cloud storage

### 8.4 End-of-Life

When decommissioning a VISTA unit:
1. Export all evidence records
2. Verify chain integrity one final time
3. Securely wipe FRAM and SD card (3-pass overwrite)
4. Record decommission in fleet management system
5. Return device to manufacturer for recycling
