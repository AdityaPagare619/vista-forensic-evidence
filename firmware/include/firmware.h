/**
 * @file firmware.h
 * @brief VISTA 2.0 Main System Header
 *
 * Top-level firmware header that aggregates all subsystem interfaces and
 * defines the system-wide data structures, state machine, and entry points.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 * @date 2026
 *
 * @note Include this file for access to all firmware subsystems.
 * @note MISRA-C:2012 compliant.
 */

#ifndef FIRMWARE_H
#define FIRMWARE_H

#ifdef __cplusplus
extern "C" {
#endif

#include "vista_config.h"
#include "imu_driver.h"
#include "can_driver.h"
#include "audio_driver.h"
#include "camera_driver.h"
#include <stdint.h>
#include <stdbool.h>

/* ========================================================================== */
/*  FORWARD DECLARATIONS                                                      */
/* ========================================================================== */

typedef struct firmware_context firmware_context_t;

/* ========================================================================== */
/*  SYSTEM STATE MACHINE                                                      */
/* ========================================================================== */

/**
 * @brief System operational states
 *
 * State transitions:
 *   INIT -> SELF_TEST -> IDLE -> ARMED -> RECORDING -> POST_CRASH -> IDLE
 *   Any state -> FAULT (on unrecoverable error)
 *   FAULT -> INIT (on watchdog reset recovery)
 */
typedef enum {
    SYS_STATE_INIT       = 0,   /**< Hardware initialization */
    SYS_STATE_SELF_TEST  = 1,   /**< Built-in self-test */
    SYS_STATE_IDLE       = 2,   /**< Systems ready, not recording */
    SYS_STATE_ARMED      = 3,   /**< Recording sensor data, awaiting event */
    SYS_STATE_RECORDING  = 4,   /**< Event detected, high-priority recording */
    SYS_STATE_POST_CRASH = 5,   /**< Post-crash recording on supercapacitor */
    SYS_STATE_FAULT      = 6,   /**< Unrecoverable fault, attempting save */
    SYS_STATE_COUNT      = 7
} sys_state_t;

/**
 * @brief State transition event types
 */
typedef enum {
    STATE_EVT_INIT_COMPLETE = 0,     /**< Init done */
    STATE_EVT_SELFTEST_PASS = 1,     /**< Self-test passed */
    STATE_EVT_SELFTEST_FAIL = 2,     /**< Self-test failed */
    STATE_EVT_ARM_CMD       = 3,     /**< Arm command received */
    STATE_EVT_DISARM_CMD    = 4,     /**< Disarm command received */
    STATE_EVT_IMPACT_DET    = 5,     /**< Impact detected by PDTSA */
    STATE_EVT_POSTCRASH_ENTRY = 6,   /**< Entering post-crash mode */
    STATE_EVT_RECORD_COMPLETE = 7,   /**< Recording complete */
    STATE_EVT_FAULT         = 8,     /**< Fault condition */
    STATE_EVT_RECOVERY      = 9,     /**< Recovery from fault */
    STATE_EVT_COUNT         = 10
} sys_state_event_t;

/**
 * @brief State transition log entry
 */
typedef struct {
    sys_state_t from_state;         /**< Previous state */
    sys_state_t to_state;           /**< New state */
    sys_state_event_t event;        /**< Triggering event */
    uint32_t timestamp_us;          /**< Transition timestamp */
} state_log_entry_t;

/* ========================================================================== */
/*  SENSOR FUSION OUTPUT                                                      */
/* ========================================================================== */

/**
 * @brief Quaternion orientation
 */
typedef struct {
    float q0;                       /**< Scalar component (w) */
    float q1;                       /**< Vector x component */
    float q2;                       /**< Vector y component */
    float q3;                       /**< Vector z component */
} quaternion_t;

/**
 * @brief Fused sensor output from ESKF
 */
typedef struct {
    quaternion_t orientation;       /**< Estimated orientation quaternion */
    imu_vec3_f32_t angular_vel;     /**< Bias-corrected angular velocity (rad/s) */
    imu_vec3_f32_t linear_accel;    /**< Bias-corrected linear acceleration (m/s^2) */
    imu_vec3_f32_t gyro_bias;       /**< Current gyro bias estimate */
    float confidence;               /**< Filter confidence (0..1) */
    uint32_t timestamp_us;          /**< Timestamp */
} fusion_output_t;

/* ========================================================================== */
/*  DETECTION OUTPUT                                                          */
/* ========================================================================== */

/**
 * @brief PDTSA detection result
 */
typedef struct {
    bool impact_detected;           /**< true if impact signature matched */
    float severity;                 /**< Impact severity (0..1) */
    float principal_magnitude;      /**< PCA principal component magnitude */
    uint32_t detection_time_us;     /**< Timestamp of detection */
    uint32_t event_duration_ms;     /**< Duration of event in ms */
    imu_vec3_f32_t impact_axis;     /**< Principal impact direction (unit vector) */
    float peak_accel_g;             /**< Peak acceleration in g */
} detection_result_t;

/* ========================================================================== */
/*  EVIDENCE CHAIN                                                            */
/* ========================================================================== */

/**
 * @brief Evidence block types
 */
typedef enum {
    EVIDENCE_TYPE_SENSOR_SNAP = 0,  /**< Sensor data snapshot */
    EVIDENCE_TYPE_IMPACT_DET  = 1,  /**< Impact detection event */
    EVIDENCE_TYPE_STATE_TRANS = 2,  /**< State transition */
    EVIDENCE_TYPE_CAN_LOG     = 3,  /**< CAN bus message log */
    EVIDENCE_TYPE_AUDIO_SNAP  = 4,  /**< Audio snapshot */
    EVIDENCE_TYPE_IMAGE       = 5,  /**< Camera frame */
    EVIDENCE_TYPE_FAULT_LOG   = 6,  /**< Fault/error log */
    EVIDENCE_TYPE_COUNT       = 7
} evidence_type_t;

/**
 * @brief Evidence block header
 *
 * Each evidence block contains a hash of the previous block,
 * creating a tamper-evident chain stored in FRAM.
 */
typedef struct {
    uint32_t block_id;              /**< Monotonic block counter */
    evidence_type_t type;           /**< Evidence type */
    uint32_t timestamp_us;          /**< Creation timestamp */
    uint16_t payload_size;          /**< Payload size in bytes */
    uint8_t prev_hash[EVIDENCE_SHA256_SIZE];  /**< SHA-256 of previous block */
    uint8_t block_hash[EVIDENCE_SHA256_SIZE];  /**< SHA-256 of this block */
    uint8_t hmac[EVIDENCE_HMAC_SIZE];          /**< HMAC-SHA256 of block */
} evidence_header_t;

/**
 * @brief Complete evidence block (header + payload)
 */
typedef struct {
    evidence_header_t header;                           /**< Block header */
    uint8_t payload[EVIDENCE_MAX_PAYLOAD];              /**< Block payload */
} evidence_block_t;

/* ========================================================================== */
/*  FRAM STORAGE LAYOUT                                                       */
/* ========================================================================== */

/**
 * @brief FRAM memory map regions
 */
typedef enum {
    FRAM_REGION_CONFIG   = 0,     /**< System configuration (4 KB) */
    FRAM_REGION_CAL      = 1,     /**< Calibration data (4 KB) */
    FRAM_REGION_EVIDENCE = 2,     /**< Evidence chain (16 KB) */
    FRAM_REGION_LOG      = 3,     /**< Event log (8 KB) */
    FRAM_REGION_COUNT    = 4
} fram_region_t;

/* ========================================================================== */
/*  CRASH STATE MACHINE CONTEXT                                               */
/* ========================================================================== */

/**
 * @brief Crash detection context
 */
typedef struct {
    bool impact_detected;               /**< Impact detected flag */
    uint32_t impact_timestamp_us;       /**< Impact detection time */
    uint32_t postcrash_start_us;        /**< Post-crash recording start */
    uint32_t supercap_mv;               /**< Supercapacitor voltage (mV) */
    bool power_failing;                 /**< Power failure imminent */
    uint32_t frames_captured;           /**< Post-crash frames captured */
    bool evidence_saved;                /**< Evidence chain saved to FRAM */
} crash_state_t;

/* ========================================================================== */
/*  FIRMWARE CONTEXT                                                          */
/* ========================================================================== */

/**
 * @brief Main firmware context — aggregates all subsystems
 *
 * Allocated statically in main.c. Passed to all subsystem functions.
 */
struct firmware_context {
    /* System state */
    sys_state_t state;                      /**< Current system state */
    sys_state_t prev_state;                 /**< Previous state */
    uint32_t state_entry_time_us;           /**< Timestamp of state entry */

    /* IMU subsystem */
    imu_context_t imu[VISTA_IMU_COUNT];    /**< IMU driver contexts */

    /* CAN subsystem */
    can_context_t can[VISTA_CAN_CHANNEL_COUNT];  /**< CAN driver contexts */

    /* Audio subsystem */
    audio_context_t audio;                  /**< Audio driver context */

    /* Camera subsystem */
    camera_context_t camera;               /**< Camera driver context */

    /* Sensor fusion */
    fusion_output_t fusion;                 /**< Latest fusion output */
    bool fusion_initialized;                /**< ESKF initialization complete */

    /* Detection */
    detection_result_t detection;           /**< Latest detection result */
    uint32_t last_detection_us;             /**< Timestamp of last detection */

    /* Crash state */
    crash_state_t crash;                    /**< Crash state machine */

    /* Evidence chain */
    uint32_t evidence_block_count;          /**< Current block count */
    evidence_block_t current_evidence;      /**< Working evidence block */

    /* State log */
    state_log_entry_t state_log[STATE_EVENT_LOG_SIZE];  /**< State transition log */
    uint8_t state_log_head;                 /**< Log head index */
    uint8_t state_log_count;               /**< Log entry count */

    /* System health */
    uint32_t loop_count;                    /**< Main loop iteration count */
    uint32_t uptime_ms;                     /**< System uptime in ms */
    uint8_t reset_reason;                   /**< Last reset reason */
    bool watchdog_fed;                      /**< Watchdog service flag */

    /* Power management */
    uint32_t vcap_mv;                       /**< Supercapacitor voltage (mV) */
    bool supercap_ready;                    /**< Supercapacitor charged */
};

/* ========================================================================== */
/*  MAIN ENTRY POINTS                                                         */
/* ========================================================================== */

/**
 * @brief System entry point (called after reset).
 *
 * Configures clocks, initializes all peripherals, runs self-test,
 * and enters main loop.
 */
void vista_main(void);

/**
 * @brief Main loop iteration.
 *
 * Processes all subsystems, runs state machine, and services interrupts.
 * Target period: 1 ms.
 */
void vista_loop(void);

/**
 * @brief System clock configuration (480 MHz).
 *
 * Configures PLL1 for 480 MHz SYSCLK from 25 MHz HSE.
 * Sets Flash wait states and bus prescalers.
 *
 * @return VISTA_OK on success.
 */
vista_error_t vista_clock_config(void);

/**
 * @brief Peripheral initialization sequence.
 *
 * Initializes GPIO, DMA, SPI, I2S, I2C, DCMI, CAN, ADC, and timers
 * in dependency order.
 *
 * @param[in] ctx  Firmware context.
 * @return VISTA_OK on success.
 */
vista_error_t vista_periph_init(firmware_context_t *ctx);

/* ========================================================================== */
/*  STATE MACHINE                                                             */
/* ========================================================================== */

/**
 * @brief Execute one tick of the system state machine.
 *
 * @param[in] ctx      Firmware context.
 * @param[in] event    Event to process (or STATE_EVT_COUNT for no event).
 * @return VISTA_OK on success.
 */
vista_error_t vista_state_machine_tick(firmware_context_t *ctx,
                                      sys_state_event_t event);

/**
 * @brief Get string name for a system state.
 *
 * @param[in] state  System state.
 * @return Pointer to static string.
 */
const char *vista_state_name(sys_state_t state);

/**
 * @brief Log a state transition.
 *
 * @param[in] ctx      Firmware context.
 * @param[in] from     Previous state.
 * @param[in] to       New state.
 * @param[in] event    Triggering event.
 */
void vista_state_log(firmware_context_t *ctx, sys_state_t from,
                     sys_state_t to, sys_state_event_t event);

/* ========================================================================== */
/*  SENSOR FUSION (ESKF interface)                                            */
/* ========================================================================== */

/**
 * @brief Initialize the Error-State Kalman Filter.
 *
 * @param[in] ctx  Firmware context.
 * @return VISTA_OK on success.
 */
vista_error_t eskf_init(firmware_context_t *ctx);

/**
 * @brief ESKF prediction step (called at IMU rate).
 *
 * @param[in] ctx      Firmware context.
 * @param[in] gyro     Gyro measurement (rad/s).
 * @param[in] dt       Time step (seconds).
 */
void eskf_predict(firmware_context_t *ctx, const imu_vec3_f32_t *gyro,
                  float dt);

/**
 * @brief ESKF update step with accelerometer.
 *
 * @param[in] ctx      Firmware context.
 * @param[in] accel    Accelerometer measurement (m/s^2).
 */
void eskf_update_accel(firmware_context_t *ctx, const imu_vec3_f32_t *accel);

/**
 * @brief Get current fusion output.
 *
 * @param[in]  ctx     Firmware context.
 * @param[out] output  Fusion output.
 */
void eskf_get_output(const firmware_context_t *ctx, fusion_output_t *output);

/* ========================================================================== */
/*  DETECTION (PDTSA interface)                                               */
/* ========================================================================== */

/**
 * @brief Initialize the PDTSA detection algorithm.
 *
 * @param[in] ctx  Firmware context.
 * @return VISTA_OK on success.
 */
vista_error_t detection_init(firmware_context_t *ctx);

/**
 * @brief Feed a new IMU sample into the detection algorithm.
 *
 * @param[in]  ctx      Firmware context.
 * @param[in]  sample   New IMU sample.
 * @param[out] result   Detection result (valid after sufficient samples).
 * @return VISTA_OK on success.
 */
vista_error_t detection_feed(firmware_context_t *ctx,
                             const imu_sample_t *sample,
                             detection_result_t *result);

/**
 * @brief Reset detection state (after event processing).
 *
 * @param[in] ctx  Firmware context.
 */
void detection_reset(firmware_context_t *ctx);

/* ========================================================================== */
/*  EVIDENCE CHAIN                                                            */
/* ========================================================================== */

/**
 * @brief Initialize the evidence chain system.
 *
 * @param[in] ctx  Firmware context.
 * @return VISTA_OK on success.
 */
vista_error_t evidence_init(firmware_context_t *ctx);

/**
 * @brief Add a new evidence block to the chain.
 *
 * Computes SHA-256 hash of the block, HMAC, and links to previous block.
 * Writes to FRAM immediately for crash safety.
 *
 * @param[in] ctx       Firmware context.
 * @param[in] type      Evidence type.
 * @param[in] payload   Data payload.
 * @param[in] payload_size  Payload size in bytes.
 * @return VISTA_OK on success.
 */
vista_error_t evidence_add(firmware_context_t *ctx, evidence_type_t type,
                           const uint8_t *payload, uint16_t payload_size);

/**
 * @brief Verify the integrity of the entire evidence chain.
 *
 * Walks all blocks from FRAM, verifying hashes and HMACs.
 *
 * @param[in] ctx  Firmware context.
 * @return VISTA_OK if chain is valid, VISTA_ERR_CRC on corruption.
 */
vista_error_t evidence_verify_chain(const firmware_context_t *ctx);

/* ========================================================================== */
/*  FRAM STORAGE                                                              */
/* ========================================================================== */

/**
 * @brief Initialize FRAM driver.
 *
 * @return VISTA_OK on success, VISTA_ERR_STORAGE if FRAM not detected.
 */
vista_error_t fram_init(void);

/**
 * @brief Read data from FRAM.
 *
 * @param[in]  addr    FRAM address (byte offset).
 * @param[out] data    Read buffer.
 * @param[in]  len     Number of bytes to read.
 * @return VISTA_OK on success.
 */
vista_error_t fram_read(uint32_t addr, uint8_t *data, uint16_t len);

/**
 * @brief Write data to FRAM.
 *
 * @param[in] addr   FRAM address (byte offset).
 * @param[in] data   Data to write.
 * @param[in] len    Number of bytes to write.
 * @return VISTA_OK on success.
 */
vista_error_t fram_write(uint32_t addr, const uint8_t *data, uint16_t len);

/**
 * @brief Erase a FRAM region (fill with 0xFF).
 *
 * @param[in] region  FRAM region to erase.
 * @return VISTA_OK on success.
 */
vista_error_t fram_erase_region(fram_region_t region);

/* ========================================================================== */
/*  CRYPTO (SHA-256 + HMAC)                                                   */
/* ========================================================================== */

/**
 * @brief Compute SHA-256 hash.
 *
 * @param[in]  data     Input data.
 * @param[in]  len      Data length in bytes.
 * @param[out] digest   32-byte hash output.
 */
void crypto_sha256(const uint8_t *data, uint32_t len, uint8_t digest[32]);

/**
 * @brief Compute HMAC-SHA256.
 *
 * @param[in]  key      HMAC key.
 * @param[in]  key_len  Key length in bytes.
 * @param[in]  data     Input data.
 * @param[in]  data_len Data length in bytes.
 * @param[out] mac      32-byte MAC output.
 */
void crypto_hmac_sha256(const uint8_t *key, uint32_t key_len,
                        const uint8_t *data, uint32_t data_len,
                        uint8_t mac[32]);

/* ========================================================================== */
/*  POWER MANAGEMENT                                                          */
/* ========================================================================== */

/**
 * @brief Read supercapacitor voltage via ADC.
 *
 * @param[in]  ctx  Firmware context.
 * @param[out] mv   Voltage in millivolts.
 * @return VISTA_OK on success.
 */
vista_error_t power_read_vcap(firmware_context_t *ctx, uint32_t *mv);

/**
 * @brief Check if supercapacitor is charged above threshold.
 *
 * @param[in] ctx  Firmware context.
 * @return true if supercap is ready for post-crash power.
 */
bool power_supercap_ready(const firmware_context_t *ctx);

/**
 * @brief Enter low-power stop mode (until wakeup interrupt).
 *
 * @return VISTA_OK on wakeup.
 */
vista_error_t power_enter_stop(void);

/* ========================================================================== */
/*  UTILITY / DEBUG                                                           */
/* ========================================================================== */

/**
 * @brief Get system uptime in milliseconds.
 *
 * @return Uptime since last reset.
 */
uint32_t vista_get_uptime_ms(void);

/**
 * @brief Get DWT cycle counter value (microsecond precision).
 *
 * @return Current cycle counter.
 */
uint32_t vista_get_dwt_cycles(void);

/**
 * @brief Convert DWT cycles to microseconds.
 *
 * @param[in] cycles  DWT cycle count.
 * @return Microseconds.
 */
uint32_t vista_cycles_to_us(uint32_t cycles);

/**
 * @brief Hard fault handler (called from assembly vector).
 *
 * Logs fault registers to FRAM and attempts controlled shutdown.
 *
 * @param[in] stack_frame  Pointer to exception stack frame.
 */
void vista_hardfault_handler(void *stack_frame);

/**
 * @brief Reset the system (software reset via RCC).
 */
void vista_system_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* FIRMWARE_H */
