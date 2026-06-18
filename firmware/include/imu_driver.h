/**
 * @file imu_driver.h
 * @brief IMU Sensor Interface for VISTA 2.0
 *
 * Driver interface for 3× IMU sensors connected via SPI:
 *   - 2× InvenSense IAM-20680HP (6-axis: accelerometer + gyroscope)
 *   - 1× LIS/H3LIS331DL (3-axis high-g accelerometer)
 *
 * All sensors are sampled at 1 kHz via DMA-driven SPI transfers with
 * hardware data-ready interrupts for minimal latency.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note MISRA-C:2012 compliant — all functions have single return point.
 * @note ISR-safe: functions marked _isr may be called from interrupt context.
 */

#ifndef IMU_DRIVER_H
#define IMU_DRIVER_H

#ifdef __cplusplus
extern "C" {
#endif

#include "vista_config.h"
#include <stdint.h>
#include <stdbool.h>

/* ========================================================================== */
/*  TYPE DEFINITIONS                                                          */
/* ========================================================================== */

/**
 * @brief IMU sensor type enumeration
 */
typedef enum {
    IMU_TYPE_IAM20680HP = 0,    /**< IAM-20680HP 6-axis IMU */
    IMU_TYPE_H3LIS331DL = 1,    /**< H3LIS331DL high-g accelerometer */
    IMU_TYPE_COUNT      = 2     /**< Number of distinct IMU types */
} imu_type_t;

/**
 * @brief IMU sensor status
 */
typedef enum {
    IMU_STATUS_UNINIT    = 0,   /**< Not initialized */
    IMU_STATUS_READY     = 1,   /**< Initialized and ready */
    IMU_STATUS_RUNNING   = 2,   /**< Actively sampling */
    IMU_STATUS_ERROR     = 3,   /**< Communication error */
    IMU_STATUS_CRC_FAIL  = 4    /**< Data integrity check failed */
} imu_status_t;

/**
 * @brief 3-axis integer vector
 */
typedef struct {
    int16_t x;                  /**< X-axis value */
    int16_t y;                  /**< Y-axis value */
    int16_t z;                  /**< Z-axis value */
} imu_vec3_i16_t;

/**
 * @brief 3-axis floating-point vector (SI units)
 */
typedef struct {
    float x;                    /**< X-axis value (m/s^2 or rad/s) */
    float y;                    /**< Y-axis value */
    float z;                    /**< Z-axis value */
} imu_vec3_f32_t;

/**
 * @brief Raw IMU sample from IAM-20680HP (accel + gyro)
 */
typedef struct {
    imu_vec3_i16_t accel;       /**< Accelerometer (raw counts) */
    imu_vec3_i16_t gyro;        /**< Gyroscope (raw counts) */
    uint32_t timestamp_us;      /**< Sample timestamp (DWT cycle counter) */
    uint8_t temp_raw;           /**< Raw temperature byte */
    uint8_t status_reg;         /**< Status register value */
    uint16_t sequence;          /**< Monotonic sequence number */
    uint8_t crc;                /**< Data CRC-8 for integrity */
} imu_raw_sample_6axis_t;

/**
 * @brief Raw IMU sample from H3LIS331DL (accel only)
 */
typedef struct {
    imu_vec3_i16_t accel;       /**< Accelerometer (raw counts) */
    uint32_t timestamp_us;      /**< Sample timestamp */
    uint8_t status_reg;         /**< Status register value */
    uint16_t sequence;          /**< Monotonic sequence number */
    uint8_t crc;                /**< Data CRC-8 for integrity */
} imu_raw_sample_3axis_t;

/**
 * @brief Processed IMU sample in engineering units
 */
typedef struct {
    imu_vec3_f32_t accel_ms2;   /**< Acceleration in m/s^2 */
    imu_vec3_f32_t gyro_rads;   /**< Angular velocity in rad/s */
    float temperature_c;        /**< Temperature in degrees Celsius */
    uint32_t timestamp_us;      /**< Sample timestamp */
    uint16_t sequence;          /**< Sequence number */
    uint8_t imu_id;             /**< Source IMU index (0, 1, or 2) */
} imu_sample_t;

/**
 * @brief IMU calibration parameters
 */
typedef struct {
    imu_vec3_f32_t accel_offset;    /**< Accelerometer bias offset (m/s^2) */
    imu_vec3_f32_t accel_scale[3];  /**< Accelerometer scale factors (per axis) */
    imu_vec3_f32_t gyro_offset;     /**< Gyroscope bias offset (rad/s) */
    imu_vec3_f32_t gyro_scale[3];   /**< Gyroscope scale factors (per axis) */
    bool valid;                     /**< Calibration data is valid */
} imu_cal_t;

/**
 * @brief Per-IMU driver context (opaque internal state)
 */
typedef struct {
    uint8_t spi_bus;                /**< SPI bus number (1, 2, or 4) */
    uint8_t cs_port;                /**< Chip-select GPIO port */
    uint8_t cs_pin;                 /**< Chip-select GPIO pin */
    uint8_t drdy_port;              /**< Data-ready GPIO port */
    uint8_t drdy_pin;               /**< Data-ready GPIO pin */
    imu_type_t type;                /**< Sensor type */
    imu_status_t status;            /**< Current status */
    imu_cal_t calibration;          /**< Calibration parameters */
    uint16_t sequence;              /**< Sequence counter */
    uint32_t error_count;           /**< Cumulative error count */
    uint8_t rx_buf[14];             /**< SPI receive buffer (max frame) */
    uint8_t tx_buf[14];             /**< SPI transmit buffer */
    volatile bool data_ready;       /**< Data-ready flag (set by ISR) */
} imu_context_t;

/* ========================================================================== */
/*  INITIALIZATION / CONFIGURATION                                            */
/* ========================================================================== */

/**
 * @brief Initialize a single IMU sensor.
 *
 * Performs soft-reset, verifies WHO_AM_I, configures ODR and full-scale,
 * and enables data-ready interrupt. Blocks until complete or timeout.
 *
 * @param[in] imu_id  IMU index (0, 1, or 2).
 * @param[in] ctx     Pointer to caller-allocated IMU context.
 * @return VISTA_OK on success, or error code.
 */
vista_error_t imu_init(uint8_t imu_id, imu_context_t *ctx);

/**
 * @brief Initialize all three IMU sensors.
 *
 * @param[in] contexts  Array of 3 IMU context structures.
 * @return VISTA_OK if all sensors initialized, VISTA_ERR_SENSOR on partial.
 */
vista_error_t imu_init_all(imu_context_t contexts[VISTA_IMU_COUNT]);

/**
 * @brief Load calibration parameters for an IMU.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @param[in] cal     Calibration data (from FRAM storage).
 * @return VISTA_OK on success.
 */
vista_error_t imu_set_calibration(uint8_t imu_id, imu_context_t *ctx,
                                  const imu_cal_t *cal);

/**
 * @brief Reconfigure IMU full-scale range at runtime.
 *
 * @param[in] imu_id    IMU index.
 * @param[in] ctx       IMU context.
 * @param[in] accel_fs  Accelerometer full-scale (2, 4, 8, 16 g).
 * @param[in] gyro_fs   Gyroscope full-scale (250, 500, 1000, 2000 dps).
 * @return VISTA_OK on success.
 */
vista_error_t imu_reconfigure(uint8_t imu_id, imu_context_t *ctx,
                              uint8_t accel_fs, uint16_t gyro_fs);

/* ========================================================================== */
/*  DATA ACQUISITION                                                          */
/* ========================================================================== */

/**
 * @brief Read a single raw sample from an IMU (polling mode).
 *
 * @param[in]  imu_id  IMU index.
 * @param[in]  ctx     IMU context.
 * @param[out] sample  Raw sample output.
 * @return VISTA_OK on success, VISTA_ERR_TIMEOUT if DRDY not asserted.
 */
vista_error_t imu_read_raw(uint8_t imu_id, imu_context_t *ctx,
                           void *sample);

/**
 * @brief Read raw sample via DMA (non-blocking).
 *
 * Initiates a DMA transfer. Call imu_dma_poll() from main loop to check
 * completion. The data_ready flag in ctx is set on completion.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @return VISTA_OK if DMA started, VISTA_ERR_BUSY if previous not done.
 */
vista_error_t imu_read_dma_start(uint8_t imu_id, imu_context_t *ctx);

/**
 * @brief Check if DMA transfer is complete.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @return true if new data available, false if transfer in progress.
 */
bool imu_dma_poll(uint8_t imu_id, imu_context_t *ctx);

/**
 * @brief Data-ready ISR handler.
 *
 * Called from EXTI interrupt when DRDY pin asserts. This is ISR-safe.
 *
 * @param[in] imu_id  IMU index that triggered the interrupt.
 */
void imu_drdy_isr(uint8_t imu_id);

/* ========================================================================== */
/*  DATA PROCESSING                                                           */
/* ========================================================================== */

/**
 * @brief Convert raw 6-axis sample to engineering units.
 *
 * Applies calibration offsets, scale factors, and sensitivity conversion.
 *
 * @param[in]  raw     Raw sample from IAM-20680HP.
 * @param[in]  cal     Calibration parameters.
 * @param[in]  imu_id  IMU index for output tagging.
 * @param[out] out     Processed sample in SI units.
 */
void imu_convert_6axis(const imu_raw_sample_6axis_t *raw,
                       const imu_cal_t *cal, uint8_t imu_id,
                       imu_sample_t *out);

/**
 * @brief Convert raw 3-axis sample to engineering units.
 *
 * @param[in]  raw     Raw sample from H3LIS331DL.
 * @param[in]  cal     Calibration parameters.
 * @param[in]  imu_id  IMU index for output tagging.
 * @param[out] out     Processed sample (gyro fields zeroed).
 */
void imu_convert_3axis(const imu_raw_sample_3axis_t *raw,
                       const imu_cal_t *cal, uint8_t imu_id,
                       imu_sample_t *out);

/**
 * @brief Verify CRC-8 of a raw IMU sample.
 *
 * @param[in] data   Pointer to sample data (excluding CRC byte).
 * @param[in] len    Number of data bytes.
 * @param[in] expected  Expected CRC value.
 * @return true if CRC matches, false otherwise.
 */
bool imu_verify_crc(const uint8_t *data, uint8_t len, uint8_t expected);

/* ========================================================================== */
/*  STATUS / DIAGNOSTICS                                                      */
/* ========================================================================== */

/**
 * @brief Get current status of an IMU sensor.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @return Current status enum value.
 */
imu_status_t imu_get_status(uint8_t imu_id, const imu_context_t *ctx);

/**
 * @brief Get cumulative error count for an IMU.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @return Number of communication errors since init.
 */
uint32_t imu_get_error_count(uint8_t imu_id, const imu_context_t *ctx);

/**
 * @brief Perform built-in self-test on an IMU.
 *
 * Enables self-test mode, reads response, compares against expected
 * values from datasheet. Restores normal mode on completion.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @return VISTA_OK if self-test passes.
 */
vista_error_t imu_self_test(uint8_t imu_id, imu_context_t *ctx);

/* ========================================================================== */
/*  REGISTER-LEVEL ACCESS (for advanced use)                                   */
/* ========================================================================== */

/**
 * @brief Read a register from an IMU.
 *
 * @param[in]  imu_id  IMU index.
 * @param[in]  ctx     IMU context.
 * @param[in]  reg     Register address.
 * @param[out] value   Register value read.
 * @return VISTA_OK on success.
 */
vista_error_t imu_reg_read(uint8_t imu_id, imu_context_t *ctx,
                           uint8_t reg, uint8_t *value);

/**
 * @brief Write a register on an IMU.
 *
 * @param[in] imu_id  IMU index.
 * @param[in] ctx     IMU context.
 * @param[in] reg     Register address.
 * @param[in] value   Value to write.
 * @return VISTA_OK on success.
 */
vista_error_t imu_reg_write(uint8_t imu_id, imu_context_t *ctx,
                            uint8_t reg, uint8_t value);

#ifdef __cplusplus
}
#endif

#endif /* IMU_DRIVER_H */
