# VISTA 2.0 — Deployment Guide
**Version:** 2.0.0 | **Date:** 2026-06-14

---

## 1. Software Requirements

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.8+ | Core runtime |
| NumPy | 1.21+ | Numerical computation |
| SciPy | 1.7+ | Signal processing, wavelets |
| PyYAML | 6.0+ | Sensor configuration |
| Git | 2.30+ | Version control |

**Install:**
```bash
cd vista-hil-design
pip install -r requirements.txt
python setup.py install
```

---

## 2. Hardware BOM (Production, 10K Units)

| Component | Model | Purpose | Unit Cost |
|-----------|-------|---------|-----------|
| IMU (×2) | IAM-20680HP | 6-DOF accel+gyro | $8.00 |
| High-G IMU | H3LIS331DL | ±400g acceleration | $5.00 |
| CAN Transceiver | TJA1050 | Vehicle bus interface | $1.50 |
| Mic Array (×4) | IM67D130A | Crash audio capture | $4.00 |
| Camera | IMX678 | Visual evidence | $35.00 |
| MCU | STM32H743VIT6 | Sensor hub + processing | $12.00 |
| FRAM | FM25V20A | Crash-safe storage | $3.00 |
| Supercapacitor | 4.7F/5.5V | Post-crash power | $5.00 |
| **TOTAL** | | | **$78.50** |

---

## 3. Assembly Procedure

### Step 1: PCB Assembly
1. Populate STM32H743VIT6 MCU (LQFP100 package)
2. Populate 3× IMU chips on SPI bus (CS pins: PA4, PA5, PA6)
3. Populate TJA1050 CAN transceiver on FDCAN1 pins (PB12/PB13)
4. Populate 4× MEMS mics on I2S bus (I2S2_SDI, I2S2_SCK, I2S2_WS)
5. Populate FRAM on SPI3 (PA15 CS)
6. Add 4.7F supercapacitor on main power rail
7. Add power supply section (5V/3A from vehicle 12V via buck converter)

### Step 2: Sensor Mounting
1. Mount sensor board to vehicle frame using M3 bolts (torque: 2 Nm)
2. Ensure rigid coupling to structural member (NOT dashboard, NOT seat)
3. Orient sensor: +X forward, +Y left, +Z up
4. Verify orientation with stationary test (Z-axis reads +1g)

### Step 3: Firmware Flash
```bash
cd firmware
make flash
```

### Step 4: Calibration
1. **Static calibration:** Place sensor flat, record 10s of data
2. **6-point tumble test:** Align each axis with gravity, record bias
3. **Dynamic calibration:** Drive vehicle at 60 km/h on smooth road, verify velocity estimate against GPS

---

## 4. Field Installation

1. Mount sensor board to rigid structural member (floor tunnel, firewall)
2. Connect CAN bus to vehicle OBD-II port (pins 6/14 on standard DLC)
3. Connect power: vehicle 12V → buck converter → 5V/3A to sensor board
4. Connect microphone array (4×) to I2S bus
5. Connect camera to DCMI interface (optional)
6. Power on and verify all sensors initialize (LED indicator green)
7. Drive 5 minutes for adaptive threshold calibration
8. Verify system status via debug UART (115200 baud)

---

## 5. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No CAN data | Wrong pinout on DLC | Verify pins 6 (CAN-L) and 14 (CAN-H) |
| IMU initialization failure | SPI clock too fast | Reduce to 5MHz during init |
| False positives on rough roads | Acceleration gate too low | Increase accel_gate_g in config |
| No detection on high-speed crashes | MPU6050 saturation | Switch to H3LIS331DL |
| Evidence chain verification fails | Clock drift | Synchronize RTC before deployment |
| Audio clipping | Mic gain too high | Reduce gain or increase AOP threshold |
| Camera frame drops | USB bandwidth | Use USB 3.0 port or reduce resolution |

---

## 6. Fleet Deployment

### Per-Vehicle Installation
1. Install sensor board (rigid mount to frame)
2. Connect power and CAN bus
3. Run 5-minute calibration drive
4. Register device with fleet manager
5. Verify telemetry connection
6. Install in vehicle, confirm green status LED

### Fleet Management
```python
from vista_hil.deployment import FleetManager
fleet = FleetManager()
# Register vehicle
device_id = fleet.register_device({
    'serial': 'VISTA-001',
    'vehicle_vin': 'XXX',
    'install_date': '2026-06-14'
})
# Monitor health
health = fleet.check_health(device_id)
```

---

*This guide covers software setup, hardware assembly, calibration, installation, troubleshooting, and fleet deployment for VISTA 2.0.*
