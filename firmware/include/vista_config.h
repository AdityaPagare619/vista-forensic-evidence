/**
 * @file vista_config.h
 * @brief VISTA 2.0 System Configuration Constants
 *
 * Central configuration header for the VISTA 2.0 embedded firmware running
 * on STM32H743VIT6. All compile-time constants, peripheral pin mappings,
 * clock configurations, and tuning parameters are defined here.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 * @date 2026
 *
 * @note This file must be included before any HAL or driver headers.
 * @note MISRA-C:2012 Rule 2.4 — All macros shall be used.
 */

#ifndef VISTA_CONFIG_H
#define VISTA_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================== */
/*  VERSION INFORMATION                                                        */
/* ========================================================================== */

#define VISTA_FW_VERSION_MAJOR   2U
#define VISTA_FW_VERSION_MINOR   0U
#define VISTA_FW_VERSION_PATCH   0U
#define VISTA_FW_VERSION_STRING  "2.0.0"

/* ========================================================================== */
/*  MCU CONFIGURATION — STM32H743VIT6                                          */
/* ========================================================================== */

/** @brief System clock frequency in Hz (480 MHz) */
#define VISTA_SYSCLK_HZ          480000000UL

/** @brief APB1 clock frequency in Hz */
#define VISTA_APB1CLK_HZ         120000000UL

/** @brief APB2 clock frequency in Hz */
#define VISTA_APB2CLK_HZ         120000000UL

/** @brief AHB clock frequency in Hz */
#define VISTA_AHBCLK_HZ          240000000UL

/** @brief HSE crystal frequency in Hz (25 MHz on VISTA board) */
#define VISTA_HSE_HZ             25000000UL

/** @brief Flash latency states for 480 MHz (4 wait states) */
#define VISTA_FLASH_LATENCY      4U

/** @brief Vector table offset — application starts at 0x08000000 */
#define VISTA_VTOR_OFFSET        0x08000000UL

/* ========================================================================== */
/*  MEMORY MAP                                                                */
/* ========================================================================== */

/** @brief Flash base address */
#define VISTA_FLASH_BASE         0x08000000UL

/** @brief Flash size in bytes (1 MB) */
#define VISTA_FLASH_SIZE         0x00100000UL

/** @brief RAM D1 (AXI SRAM) — main application RAM, 512 KB */
#define VISTA_RAM_D1_BASE        0x24000000UL
#define VISTA_RAM_D1_SIZE        0x00080000UL

/** @brief RAM D2 — SRAM1+SRAM2+SRAM3, 288 KB total */
#define VISTA_RAM_D2_BASE        0x30000000UL
#define VISTA_RAM_D2_SIZE        0x00048000UL

/** @brief RAM D3 — SRAM4 + ITCM + DTCM */
#define VISTA_RAM_D3_BASE        0x38000000UL
#define VISTA_RAM_D3_SIZE        0x00010000UL

/** @brief ITCM base (Instruction Tightly Coupled Memory, 64 KB) */
#define VISTA_ITCM_BASE          0x00000000UL
#define VISTA_ITCM_SIZE          0x00010000UL

/** @brief DTCM base (Data Tightly Coupled Memory, 128 KB) */
#define VISTA_DTCM_BASE          0x20000000UL
#define VISTA_DTCM_SIZE          0x00020000UL

/* ========================================================================== */
/*  IMU CONFIGURATION                                                         */
/* ========================================================================== */

/** @brief Number of IMU sensors */
#define VISTA_IMU_COUNT          3U

/** @brief IMU 0 — IAM-20680HP on SPI1 */
#define VISTA_IMU0_SPI           1U
#define VISTA_IMU0_CS_PORT       'A'  /* GPIOA */
#define VISTA_IMU0_CS_PIN        4U
#define VISTA_IMU0_DRDY_PORT     'C'  /* GPIOC */
#define VISTA_IMU0_DRDY_PIN      5U
#define VISTA_IMU0_TYPE          IMU_TYPE_IAM20680HP

/** @brief IMU 1 — IAM-20680HP on SPI2 */
#define VISTA_IMU1_SPI           2U
#define VISTA_IMU1_CS_PORT       'B'  /* GPIOB */
#define VISTA_IMU1_CS_PIN        12U
#define VISTA_IMU1_DRDY_PORT     'C'  /* GPIOC */
#define VISTA_IMU1_DRDY_PIN      6U
#define VISTA_IMU1_TYPE          IMU_TYPE_IAM20680HP

/** @brief IMU 2 — H3LIS331DL on SPI4 (high-g accelerometer only) */
#define VISTA_IMU2_SPI           4U
#define VISTA_IMU2_CS_PORT       'E'  /* GPIOE */
#define VISTA_IMU2_CS_PIN        4U
#define VISTA_IMU2_DRDY_PORT     'E'  /* GPIOE */
#define VISTA_IMU2_DRDY_PIN      5U
#define VISTA_IMU2_TYPE          IMU_TYPE_H3LIS331DL

/** @brief IMU sampling rate in Hz */
#define VISTA_IMU_SAMPLE_RATE_HZ 1000U

/** @brief IMU SPI clock speed in Hz (10 MHz) */
#define VISTA_IMU_SPI_CLK_HZ     10000000UL

/** @brief IMU sample period in microseconds */
#define VISTA_IMU_PERIOD_US      (1000000UL / VISTA_IMU_SAMPLE_RATE_HZ)

/** @brief IMU FIFO depth for DMA buffering */
#define VISTA_IMU_FIFO_DEPTH     16U

/** @brief IAM-20680HP WHO_AM_I expected value */
#define IAM20680HP_WHO_AM_I      0xE5U

/** @brief H3LIS331DL WHO_AM_I expected value */
#define H3LIS331DL_WHO_AM_I      0x32U

/* ========================================================================== */
/*  CAN BUS CONFIGURATION                                                     */
/* ========================================================================== */

/** @brief Number of CAN channels */
#define VISTA_CAN_CHANNEL_COUNT  2U

/** @brief CAN0 — FDCAN1 for vehicle bus */
#define VISTA_CAN0_PERIPH        1U
#define VISTA_CAN0_TX_PORT       'D'  /* GPIOD */
#define VISTA_CAN0_TX_PIN        1U
#define VISTA_CAN0_RX_PORT       'D'  /* GPIOD */
#define VISTA_CAN0_RX_PIN        0U

/** @brief CAN1 — FDCAN2 for sensor bus */
#define VISTA_CAN1_PERIPH        2U
#define VISTA_CAN1_TX_PORT       'B'  /* GPIOB */
#define VISTA_CAN1_TX_PIN        13U
#define VISTA_CAN1_RX_PORT       'B'  /* GPIOB */
#define VISTA_CAN1_RX_PIN        12U

/** @brief CAN nominal bitrate in bps (500 kbps) */
#define VISTA_CAN_BITRATE        500000UL

/** @brief CAN FD data bitrate in bps (2 Mbps) */
#define VISTA_CAN_FD_BITRATE     2000000UL

/** @brief CAN TX mailbox count */
#define VISTA_CAN_TX_MAILBOXES   3U

/** @brief CAN RX FIFO 0 size */
#define VISTA_CAN_RX_FIFO0_SIZE  64U

/** @brief CAN RX FIFO 1 size */
#define VISTA_CAN_RX_FIFO1_SIZE  64U

/** @brief CAN message buffer size for outbound queue */
#define VISTA_CAN_TX_QUEUE_SIZE  32U

/* ========================================================================== */
/*  AUDIO / I2S CONFIGURATION                                                 */
/* ========================================================================== */

/** @brief Number of MEMS microphones */
#define VISTA_MIC_COUNT          4U

/** @brief Audio sample rate in Hz */
#define VISTA_AUDIO_SAMPLE_RATE  48000U

/** @brief Audio bit depth */
#define VISTA_AUDIO_BIT_DEPTH    16U

/** @brief Audio samples per frame (for processing window) */
#define VISTA_AUDIO_FRAME_SIZE   256U

/** @brief Number of double-buffered audio frames */
#define VISTA_AUDIO_BUFFER_COUNT 4U

/** @brief Audio DMA half-transfer and transfer-complete buffer size (samples) */
#define VISTA_AUDIO_DMA_BUF_SIZE (VISTA_AUDIO_FRAME_SIZE * VISTA_AUDIO_BUFFER_COUNT)

/** @brief I2S2 — Microphones 0,1 (stereo pair) */
#define VISTA_I2S2_WS_PORT       'B'
#define VISTA_I2S2_WS_PIN        12U
#define VISTA_I2S2_SCK_PORT      'B'
#define VISTA_I2S2_SCK_PIN       13U
#define VISTA_I2S2_SD_PORT       'C'
#define VISTA_I2S2_SD_PIN        2U

/** @brief I2S3 — Microphones 2,3 (stereo pair) */
#define VISTA_I2S3_WS_PORT       'A'
#define VISTA_I2S3_WS_PIN        4U
#define VISTA_I2S3_SCK_PORT      'A'
#define VISTA_I2S3_SCK_PIN       5U
#define VISTA_I2S3_SD_PORT       'C'
#define VISTA_I2S3_SD_PIN        10U

/* ========================================================================== */
/*  CAMERA / DCMI CONFIGURATION                                               */
/* ========================================================================== */

/** @brief Camera interface type */
#define VISTA_CAMERA_TYPE        CAMERA_TYPE_HM01B0  /* Himax HM01B0 */

/** @brief Camera resolution — QVGA */
#define VISTA_CAMERA_WIDTH       320U
#define VISTA_CAMERA_HEIGHT      240U

/** @brief Camera pixel format (grayscale) */
#define VISTA_CAMERA_PIXEL_FMT   0U  /* 0 = grayscale, 1 = RGB565 */

/** @brief Camera frame rate target */
#define VISTA_CAMERA_FPS         30U

/** @brief Camera frame buffer count (double-buffered) */
#define VISTA_CAMERA_BUF_COUNT   2U

/** @brief Camera frame buffer size in bytes */
#define VISTA_CAMERA_FRAME_SIZE  (VISTA_CAMERA_WIDTH * VISTA_CAMERA_HEIGHT)

/** @brief DCMI data pins (8-bit parallel) */
#define VISTA_DCMI_D0_PORT       'A'
#define VISTA_DCMI_D0_PIN        9U
#define VISTA_DCMI_D1_PORT       'A'
#define VISTA_DCMI_D1_PIN        10U
#define VISTA_DCMI_D2_PORT       'C'
#define VISTA_DCMI_D2_PIN        8U
#define VISTA_DCMI_D3_PORT       'C'
#define VISTA_DCMI_D3_PIN        9U
#define VISTA_DCMI_D4_PORT       'C'
#define VISTA_DCMI_D4_PIN        11U
#define VISTA_DCMI_D5_PORT       'B'
#define VISTA_DCMI_D5_PIN        6U
#define VISTA_DCMI_D6_PORT       'E'
#define VISTA_DCMI_D6_PIN        5U
#define VISTA_DCMI_D7_PORT       'E'
#define VISTA_DCMI_D7_PIN        6U
#define VISTA_DCMI_VSYNC_PORT    'B'
#define VISTA_DCMI_VSYNC_PIN     7U
#define VISTA_DCMI_HSYNC_PORT    'A'
#define VISTA_DCMI_HSYNC_PIN     4U
#define VISTA_DCMI_PCLK_PORT     'A'
#define VISTA_DCMI_PCLK_PIN      6U
#define VISTA_DCMI_XCLK_PORT     'A'
#define VISTA_DCMI_XCLK_PIN      8U

/* ========================================================================== */
/*  FRAM CONFIGURATION                                                        */
/* ========================================================================== */

/** @brief FRAM SPI peripheral */
#define VISTA_FRAM_SPI           6U

/** @brief FRAM SPI clock speed in Hz (8 MHz) */
#define VISTA_FRAM_SPI_CLK_HZ    8000000UL

/** @brief FRAM CS pin */
#define VISTA_FRAM_CS_PORT       'G'
#define VISTA_FRAM_CS_PIN        8U

/** @brief FRAM total capacity in bytes (32 KB) */
#define VISTA_FRAM_SIZE          0x00008000UL

/** @brief FRAM write enable instruction */
#define VISTA_FRAM_WREN          0x06U

/** @brief FRAM write disable instruction */
#define VISTA_FRAM_WRDI          0x04U

/** @brief FRAM read instruction */
#define VISTA_FRAM_READ          0x03U

/** @brief FRAM write instruction */
#define VISTA_FRAM_WRITE         0x02U

/** @brief FRAM read status register */
#define VISTA_FRAM_RDSR          0x05U

/** @brief FRAM JEDEC ID instruction */
#define VISTA_FRAM_RDID          0x9FU

/* ========================================================================== */
/*  ESKF (Error-State Kalman Filter) CONFIGURATION                             */
/* ========================================================================== */

/** @brief ESKF state dimension (quaternion + gyro bias) */
#define ESKF_STATE_DIM           7U

/** @brief ESKF error state dimension (3 rotation error + 3 gyro bias) */
#define ESKF_ERROR_STATE_DIM     6U

/** @brief ESKF measurement dimension (accelerometer) */
#define ESKF_MEAS_DIM            3U

/** @brief Gravity magnitude in m/s^2 */
#define ESKF_GRAVITY             9.80665f

/** @brief Accelerometer noise variance */
#define ESKF_ACCEL_NOISE_VAR     0.5f

/** @brief Gyroscope noise variance (rad/s)^2 */
#define ESKF_GYRO_NOISE_VAR      0.01f

/** @brief Gyroscope bias random walk variance */
#define ESKF_GYRO_BIAS_WALK_VAR  1.0e-6f

/** @brief ESKF initialization settling time in ms */
#define ESKF_SETTLE_MS           500U

/** @brief Magnetometer enabled (0 = disabled, 1 = enabled) */
#define ESKF_USE_MAGNETOMETER    0U

/* ========================================================================== */
/*  PDTSA (Crash Detection) CONFIGURATION                                     */
/* ========================================================================== */

/** @brief PDTSA sliding window size in samples (50 ms at 1 kHz) */
#define PDTSA_WINDOW_SIZE        50U

/** @brief PDTSA detection threshold (normalized) */
#define PDTSA_THRESHOLD          0.85f

/** @brief PDTSA minimum event duration in ms */
#define PDTSA_MIN_DURATION_MS    5U

/** @brief PDTSA cooldown period in ms after detection */
#define PDTSA_COOLDOWN_MS        100U

/** @brief Number of principal components to analyze */
#define PDTSA_NUM_PCA_COMPONENTS 3U

/** @brief High-g accelerometer threshold for trigger (in g) */
#define PDTSA_HIGHG_TRIGGER_G    5.0f

/* ========================================================================== */
/*  EVIDENCE CHAIN CONFIGURATION                                              */
/* ========================================================================== */

/** @brief SHA-256 output digest size in bytes */
#define EVIDENCE_SHA256_SIZE     32U

/** @brief HMAC-SHA256 output size in bytes */
#define EVIDENCE_HMAC_SIZE       32U

/** @brief Maximum evidence payload size in bytes */
#define EVIDENCE_MAX_PAYLOAD     512U

/** @brief Evidence chain maximum blocks before wrap */
#define EVIDENCE_CHAIN_MAX_BLOCKS 4096U

/** @brief Evidence storage region size in FRAM (bytes) */
#define EVIDENCE_STORAGE_SIZE    0x00004000UL  /* 16 KB */

/** @brief HMAC key size in bytes (256-bit key) */
#define EVIDENCE_HMAC_KEY_SIZE   32U

/* ========================================================================== */
/*  STATE MACHINE CONFIGURATION                                               */
/* ========================================================================== */

/** @brief Maximum time in INIT state before fault (ms) */
#define STATE_INIT_TIMEOUT_MS    5000U

/** @brief Maximum time in SELF_TEST before fault (ms) */
#define STATE_SELFTEST_TIMEOUT_MS 3000U

/** @brief Armed-to-crash detection grace period (ms) */
#define STATE_ARM_GRACE_MS       100U

/** @brief Post-crash recording duration (ms) */
#define STATE_POSTCRASH_DURATION_MS 5000U

/** @brief Maximum number of state transition events logged */
#define STATE_EVENT_LOG_SIZE     64U

/* ========================================================================== */
/*  DMA CONFIGURATION                                                         */
/* ========================================================================== */

/** @brief DMA stream for IMU0 SPI RX */
#define VISTA_DMA_IMU0_STREAM    0U

/** @brief DMA stream for IMU1 SPI RX */
#define VISTA_DMA_IMU1_STREAM    1U

/** @brief DMA stream for IMU2 SPI RX */
#define VISTA_DMA_IMU2_STREAM    2U

/** @brief DMA stream for Audio I2S2 RX */
#define VISTA_DMA_AUDIO0_STREAM  3U

/** @brief DMA stream for Audio I2S3 RX */
#define VISTA_DMA_AUDIO1_STREAM  4U

/** @brief DMA stream for Camera DCMI RX */
#define VISTA_DMA_CAMERA_STREAM  5U

/** @brief DMA stream for FRAM SPI TX */
#define VISTA_DMA_FRAM_STREAM    6U

/* ========================================================================== */
/*  TIMING / WATCHDOG                                                         */
/* ========================================================================== */

/** @brief Independent watchdog timeout in ms */
#define VISTA_IWDG_TIMEOUT_MS    2000U

/** @brief Main loop target period in ms */
#define VISTA_MAIN_LOOP_PERIOD_MS 1U

/** @brief Status LED blink rate in ms (heartbeat) */
#define VISTA_LED_HEARTBEAT_MS   500U

/** @brief Supercapacitor low-voltage threshold in mV */
#define VISTA_SUPERCAP_LOW_MV    3000U

/** @brief Supercapacitor critical threshold in mV */
#define VISTA_SUPERCAP_CRIT_MV   2700U

/** @brief ADC channel for supercapacitor voltage */
#define VISTA_SUPERCAP_ADC_CH    0U

/* ========================================================================== */
/*  ERROR CODES                                                               */
/* ========================================================================== */

/** @brief Error codes used throughout the firmware */
typedef enum {
    VISTA_OK              = 0,    /**< Success */
    VISTA_ERR_INIT        = 1,    /**< Initialization failure */
    VISTA_ERR_TIMEOUT     = 2,    /**< Operation timeout */
    VISTA_ERR_SPI         = 3,    /**< SPI communication error */
    VISTA_ERR_I2C         = 4,    /**< I2C communication error */
    VISTA_ERR_CAN         = 5,    /**< CAN bus error */
    VISTA_ERR_DMA         = 6,    /**< DMA error */
    VISTA_ERR_CRC         = 7,    /**< CRC / checksum mismatch */
    VISTA_ERR_RANGE       = 8,    /**< Parameter out of range */
    VISTA_ERR_OVERFLOW    = 9,    /**< Buffer overflow */
    VISTA_ERR_BUSY        = 10,   /**< Resource busy */
    VISTA_ERR_FAULT       = 11,   /**< Hardware fault */
    VISTA_ERR_NO_POWER    = 12,   /**< Insufficient power */
    VISTA_ERR_SENSOR      = 13,   /**< Sensor failure */
    VISTA_ERR_STORAGE     = 14,   /**< Storage error */
    VISTA_ERR_CRYPTO      = 15,   /**< Cryptographic error */
    VISTA_ERR_STATE       = 16,   /**< Invalid state for operation */
    VISTA_ERR_NOMEM       = 17,   /**< Insufficient memory */
    VISTA_ERR_COUNT       = 18    /**< Sentinel — always last */
} vista_error_t;

#ifdef __cplusplus
}
#endif

#endif /* VISTA_CONFIG_H */
