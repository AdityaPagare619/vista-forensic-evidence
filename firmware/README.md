# VISTA 2.0 Firmware

Embedded firmware skeleton for the VISTA 2.0 crash data recorder running on **STM32H743VIT6** (Cortex-M7, 480 MHz, 1 MB Flash, 1 MB RAM).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Main Loop (1 kHz)                     │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │  IMU x3  │  │  ESKF    │  │  PDTSA   │  │  CAN x2  ││
│  │  SPI DMA │→ │  Fusion  │→ │  Detect  │  │  FDCAN   ││
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘│
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Audio x4 │  │  Camera  │  │  Evidence Chain      │  │
│  │  I2S DMA │  │  DCMI    │  │  SHA-256 + HMAC      │  │
│  └─────────┘  └──────────┘  │  FRAM Storage        │  │
│                              └──────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐│
│  │         Crash State Machine                          ││
│  │  INIT → SELF_TEST → IDLE → ARMED → RECORDING        ││
│  │                                → POST_CRASH          ││
│  │                                    (supercap power)  ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

## Peripheral Map

| Peripheral | Function | Bus | DMA Stream |
|-----------|----------|-----|------------|
| IMU 0 | IAM-20680HP (6-axis) | SPI1 | DMA1_S0 |
| IMU 1 | IAM-20680HP (6-axis) | SPI2 | DMA1_S1 |
| IMU 2 | H3LIS331DL (high-g) | SPI4 | DMA1_S2 |
| MIC 0-1 | I2S stereo pair | I2S2 | DMA1_S3 |
| MIC 2-3 | I2S stereo pair | I2S3 | DMA1_S4 |
| Camera | HM01B0 QVGA | DCMI | DMA2_S0 |
| FRAM | MB85RC64 (32 KB) | SPI6 | DMA2_S1 |
| CAN 0 | Vehicle bus (500k/2M FD) | FDCAN1 | — |
| CAN 1 | Sensor bus | FDCAN2 | — |

## Building

### Prerequisites

- **ARM GCC Toolchain**: `arm-none-eabi-gcc` ≥ 10.3
- **STM32CubeH7**: HAL and CMSIS drivers (adjust paths in Makefile)
- **OpenOCD** or **STM32CubeProgrammer**: for flashing

### Quick Start

```bash
# Install toolchain (Ubuntu/Debian)
sudo apt install gcc-arm-none-eabi

# Clone STM32CubeH7 and set up drivers
git clone https://github.com/STMicroelectronics/STM32CubeH7.git
cd firmware
ln -s ../STM32CubeH7/Drivers Drivers

# Build release firmware
make

# Build debug firmware
make debug

# Flash via ST-Link
make flash

# Show firmware size
make size

# Generate disassembly
make disasm
```

### Build Targets

| Target | Description |
|--------|-------------|
| `make` | Release build (-O2, LTO) |
| `make debug` | Debug build (-Og, symbols) |
| `make clean` | Remove build artifacts |
| `make flash` | Flash via OpenOCD/ST-Link |
| `make flash-cube` | Flash via STM32CubeProgrammer |
| `make gdb` | Start GDB debug session |
| `make size` | Show firmware size breakdown |
| `make disasm` | Generate disassembly listing |
| `make misra` | Run MISRA-C static analysis |
| `make analyze` | Run cppcheck static analysis |
| `make docs` | Generate Doxygen documentation |

## File Structure

```
firmware/
├── include/
│   ├── vista_config.h       # System constants, pin mapping, memory map
│   ├── imu_driver.h         # IMU sensor interface (IAM-20680HP, H3LIS331DL)
│   ├── can_driver.h         # CAN bus interface (FDCAN1, FDCAN2)
│   ├── audio_driver.h       # Audio interface (4× MEMS mic via I2S)
│   ├── camera_driver.h      # Camera interface (DCMI)
│   └── firmware.h           # Main system header (state machine, ESKF, evidence)
├── src/
│   ├── main.c               # Entry point, main loop, ISR vectors
│   ├── imu_interface.c      # IMU SPI driver with DMA and CRC
│   ├── eskf.c               # Error-State Kalman Filter
│   ├── detection.c          # PDTSA crash detection algorithm
│   ├── evidence.c           # SHA-256 + HMAC evidence chain
│   ├── crash_state_machine.c # System state machine
│   └── fram_storage.c       # FRAM driver for crash-safe storage
├── Makefile                 # ARM cross-compilation build system
├── STM32H743VITx_FLASH.ld  # Linker script
└── README.md                # This file
```

## State Machine

```
                    ┌──────────┐
              ┌────→│   INIT   │────┐
              │     └──────────┘    │ init complete
              │                     ▼
              │     ┌──────────┐    ┌──────────┐
              │     │  FAULT   │←───│SELF_TEST │
              │     └──────────┘    └──────────┘
              │         ↑              │ pass
              │         │              ▼
              │     ┌──────────┐    ┌──────────┐
              │     │  RECOVERY│    │   IDLE   │←─┐
              │     └──────────┘    └──────────┘  │
              │                     │ arm cmd     │
              │                     ▼              │
              │     ┌──────────┐    ┌──────────┐  │
              └─────│  RECORD  │←───│  ARMED   │──┘
                    └──────────┘    └──────────┘  │
                         │ impact    │ disarm     │
                         │ detected  └────────────┘
                         ▼
                    ┌──────────┐
                    │POST_CRASH│
                    └──────────┘
                    (supercap power)
```

## Evidence Chain

Each evidence block is cryptographically linked:

```
Block N:
┌─────────────────────────────────────┐
│ block_id: N                         │
│ type: IMPACT_DET / SENSOR_SNAP / ...│
│ timestamp: µs                       │
│ prev_hash: SHA-256(Block N-1)       │ ← chain link
│ payload: [event data]               │
│ block_hash: SHA-256(header + data)  │ ← integrity
│ hmac: HMAC-SHA256(block_hash)       │ ← authentication
└─────────────────────────────────────┘
```

Stored in FRAM (16 KB region) for crash-safe persistence. Survives power loss.

## ESKF (Error-State Kalman Filter)

Quaternion-based orientation estimation:

- **State**: quaternion (4) + gyro bias (3) = 7 dimensions
- **Error state**: rotation error (3) + bias error (3) = 6 dimensions
- **Predict**: Gyro integration with bias compensation
- **Update**: Accelerometer (gravity reference), outlier rejection
- **Output**: Orientation quaternion, bias-corrected angular velocity, confidence

## PDTSA Detection

Real-time crash detection:

1. **Sliding window**: 50 ms of IMU data (50 samples @ 1 kHz)
2. **PCA**: Power iteration for principal component of acceleration
3. **Threshold**: Peak acceleration along principal axis > 5g
4. **Cooldown**: 100 ms between detections
5. **Output**: Impact severity, direction, peak acceleration

## Coding Standards

- **MISRA-C:2012** compliant where possible
- **Doxygen** comments for all public functions
- **Header guards** on all headers
- **Error codes** — all functions return `vista_error_t`
- **No dynamic allocation** — all buffers statically allocated
- **ISR-safe** — functions marked with documentation
- **Stack usage** monitored via `-fstack-usage`

## Hardware Notes

- **Supercapacitor**: Powers the system post-crash for ~5 seconds
- **FRAM**: Non-volatile storage with 10^14 write endurance
- **IMU orientation**: IMU0/IMU1 aligned to vehicle axes, IMU2 (high-g) vertical
- **Camera**: HM01B0 low-power QVGA for post-crash imaging
- **CAN FD**: 500 kbps nominal, 2 Mbps data rate

## License

Proprietary — VISTA Project. Internal use only.
