/**
 * @file imu_interface.c
 * @brief IMU SPI Communication Driver Implementation
 *
 * SPI driver for IAM-20680HP and H3LIS331DL IMU sensors.
 * Uses DMA for zero-copy transfers with data-ready interrupts.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 */

#include "imu_driver.h"
#include "firmware.h"
#include <string.h>

/* ========================================================================== */
/*  REGISTER MAP — IAM-20680HP                                                */
/* ========================================================================== */

#define IAM_REG_WHO_AM_I        0x75U
#define IAM_REG_SMPLRT_DIV      0x19U
#define IAM_REG_CONFIG          0x1AU
#define IAM_REG_GYRO_CONFIG     0x1BU
#define IAM_REG_ACCEL_CONFIG    0x1CU
#define IAM_REG_ACCEL_CONFIG2   0x1DU
#define IAM_REG_FIFO_EN         0x23U
#define IAM_REG_INT_PIN_CFG     0x37U
#define IAM_REG_INT_ENABLE      0x38U
#define IAM_REG_INT_STATUS      0x3AU
#define IAM_REG_ACCEL_XOUT_H    0x3BU
#define IAM_REG_TEMP_OUT_H      0x41U
#define IAM_REG_GYRO_XOUT_H     0x43U
#define IAM_REG_USER_CTRL       0x6AU
#define IAM_REG_PWR_MGMT_1      0x6BU
#define IAM_REG_PWR_MGMT_2      0x6CU
#define IAM_REG_FIFO_COUNTH     0x72U
#define IAM_REG_FIFO_R_W        0x74U

/* ========================================================================== */
/*  REGISTER MAP — H3LIS331DL                                                 */
/* ========================================================================== */

#define H3L_REG_WHO_AM_I        0x0FU
#define H3L_REG_CTRL_REG1       0x20U
#define H3L_REG_CTRL_REG2       0x21U
#define H3L_REG_CTRL_REG3       0x22U
#define H3L_REG_CTRL_REG4       0x23U
#define H3L_REG_CTRL_REG5       0x24U
#define H3L_REG_OUT_X_L         0x28U
#define H3L_REG_STATUS_REG      0x27U

/* ========================================================================== */
/*  SPI HELPERS                                                               */
/* ========================================================================== */

/** @brief SPI read command (MSB set) */
#define SPI_READ_BIT    0x80U

/**
 * @brief Assert chip-select (active low).
 */
static inline void cs_assert(const imu_context_t *ctx)
{
    /* TODO: HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET) */
    (void)ctx;
}

/**
 * @brief Deassert chip-select.
 */
static inline void cs_deassert(const imu_context_t *ctx)
{
    /* TODO: HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET) */
    (void)ctx;
}

/**
 * @brief SPI transmit/receive (blocking, poll mode).
 *
 * @param[in]  ctx     IMU context (provides SPI bus info).
 * @param[in]  tx      Transmit data (can be NULL for read-only).
 * @param[out] rx      Receive buffer (can be NULL for write-only).
 * @param[in]  len     Number of bytes.
 * @return VISTA_OK on success.
 */
static vista_error_t spi_transfer(const imu_context_t *ctx,
                                  const uint8_t *tx, uint8_t *rx, uint16_t len)
{
    /* TODO: HAL_SPI_TransmitReceive(SPIHandle, tx, rx, len, timeout) */
    (void)ctx;
    (void)tx;
    (void)rx;
    (void)len;
    return VISTA_OK;
}

/**
 * @brief Single register read.
 */
static vista_error_t reg_read(const imu_context_t *ctx, uint8_t reg,
                              uint8_t *value)
{
    uint8_t tx[2] = { reg | SPI_READ_BIT, 0x00U };
    uint8_t rx[2] = { 0U, 0U };

    cs_assert(ctx);
    vista_error_t ret = spi_transfer(ctx, tx, rx, 2U);
    cs_deassert(ctx);

    if (ret == VISTA_OK) {
        *value = rx[1];
    }
    return ret;
}

/**
 * @brief Single register write.
 */
static vista_error_t reg_write(const imu_context_t *ctx, uint8_t reg,
                               uint8_t value)
{
    uint8_t tx[2] = { reg & ~SPI_READ_BIT, value };
    uint8_t rx[2] = { 0U, 0U };

    cs_assert(ctx);
    vista_error_t ret = spi_transfer(ctx, tx, rx, 2U);
    cs_deassert(ctx);

    return ret;
}

/**
 * @brief Burst read from consecutive registers.
 */
static vista_error_t burst_read(const imu_context_t *ctx, uint8_t reg,
                                uint8_t *data, uint8_t len)
{
    uint8_t tx[16] = { 0U };
    uint8_t rx[16] = { 0U };

    tx[0] = reg | SPI_READ_BIT;

    cs_assert(ctx);
    vista_error_t ret = spi_transfer(ctx, tx, rx, (uint16_t)(len + 1U));
    cs_deassert(ctx);

    if (ret == VISTA_OK) {
        (void)memcpy(data, &rx[1], len);
    }
    return ret;
}

/* ========================================================================== */
/*  CRC-8 (for IAM-20680HP data integrity)                                    */
/* ========================================================================== */

/** @brief CRC-8 polynomial (x^8 + x^2 + x + 1) */
#define CRC8_POLY    0x07U

/**
 * @brief Compute CRC-8 over data buffer.
 */
static uint8_t crc8_compute(const uint8_t *data, uint8_t len)
{
    uint8_t crc = 0xFFU;
    for (uint8_t i = 0U; i < len; i++) {
        crc ^= data[i];
        for (uint8_t bit = 0U; bit < 8U; bit++) {
            if ((crc & 0x80U) != 0U) {
                crc = (uint8_t)((crc << 1U) ^ CRC8_POLY);
            } else {
                crc = (uint8_t)(crc << 1U);
            }
        }
    }
    return crc;
}

/* ========================================================================== */
/*  IAM-20680HP SPECIFIC OPERATIONS                                           */
/* ========================================================================== */

/**
 * @brief Configure IAM-20680HP registers for 1 kHz sampling.
 */
static vista_error_t iam20680hp_configure(imu_context_t *ctx)
{
    vista_error_t ret;

    /* Software reset */
    ret = reg_write(ctx, IAM_REG_PWR_MGMT_1, 0x80U);
    if (ret != VISTA_OK) return ret;

    /* Wait for reset to complete (100 ms) */
    /* TODO: HAL_Delay(100) */

    /* Select PLL clock source */
    ret = reg_write(ctx, IAM_REG_PWR_MGMT_1, 0x01U);
    if (ret != VISTA_OK) return ret;

    /* Sample rate divider: 1 kHz / (1+0) = 1 kHz */
    ret = reg_write(ctx, IAM_REG_SMPLRT_DIV, 0x00U);
    if (ret != VISTA_OK) return ret;

    /* DLPF bandwidth: 41 Hz */
    ret = reg_write(ctx, IAM_REG_CONFIG, 0x03U);
    if (ret != VISTA_OK) return ret;

    /* Gyro config: ±250 dps, DLPF enabled */
    ret = reg_write(ctx, IAM_REG_GYRO_CONFIG, 0x00U);
    if (ret != VISTA_OK) return ret;

    /* Accel config: ±4g */
    ret = reg_write(ctx, IAM_REG_ACCEL_CONFIG, 0x08U);
    if (ret != VISTA_OK) return ret;

    /* Enable data-ready interrupt on INT1 pin */
    ret = reg_write(ctx, IAM_REG_INT_PIN_CFG, 0x10U);
    if (ret != VISTA_OK) return ret;

    /* Enable RAW_DATA_RDY interrupt */
    ret = reg_write(ctx, IAM_REG_INT_ENABLE, 0x01U);
    if (ret != VISTA_OK) return ret;

    /* Enable I2C disable (SPI-only mode) */
    ret = reg_write(ctx, IAM_REG_USER_CTRL, 0x10U);

    return ret;
}

/**
 * @brief Read raw 6-axis data from IAM-20680HP.
 */
static vista_error_t iam20680hp_read_raw(imu_context_t *ctx,
                                         imu_raw_sample_6axis_t *sample)
{
    uint8_t buf[14] = { 0U };
    vista_error_t ret;

    /* Read 14 bytes starting from ACCEL_XOUT_H:
     * Accel[6] + Temp[2] + Gyro[6] = 14 bytes */
    ret = burst_read(ctx, IAM_REG_ACCEL_XOUT_H, buf, 14U);
    if (ret != VISTA_OK) return ret;

    /* Parse accelerometer (big-endian) */
    sample->accel.x = (int16_t)(((uint16_t)buf[0] << 8U) | (uint16_t)buf[1]);
    sample->accel.y = (int16_t)(((uint16_t)buf[2] << 8U) | (uint16_t)buf[3]);
    sample->accel.z = (int16_t)(((uint16_t)buf[4] << 8U) | (uint16_t)buf[5]);

    /* Parse temperature */
    sample->temp_raw = buf[6];

    /* Parse gyroscope */
    sample->gyro.x = (int16_t)(((uint16_t)buf[8] << 8U) | (uint16_t)buf[9]);
    sample->gyro.y = (int16_t)(((uint16_t)buf[10] << 8U) | (uint16_t)buf[11]);
    sample->gyro.z = (int16_t)(((uint16_t)buf[12] << 8U) | (uint16_t)buf[13]);

    /* Timestamp */
    sample->timestamp_us = vista_get_dwt_cycles();

    /* Sequence number */
    sample->sequence = ctx->sequence++;

    /* CRC-8 over data bytes (excluding CRC itself) */
    sample->crc = crc8_compute(buf, 13U);

    return VISTA_OK;
}

/* ========================================================================== */
/*  H3LIS331DL SPECIFIC OPERATIONS                                            */
/* ========================================================================== */

/**
 * @brief Configure H3LIS331DL registers for 1 kHz sampling.
 */
static vista_error_t h3lis331dl_configure(imu_context_t *ctx)
{
    vista_error_t ret;

    /* CTRL_REG1: ODR=1 kHz, XYZ enable */
    ret = reg_write(ctx, H3L_REG_CTRL_REG1, 0x78U);
    if (ret != VISTA_OK) return ret;

    /* CTRL_REG2: ±100g full scale */
    ret = reg_write(ctx, H3L_REG_CTRL_REG2, 0x00U);
    if (ret != VISTA_OK) return ret;

    /* CTRL_REG3: Data-ready on INT1 */
    ret = reg_write(ctx, H3L_REG_CTRL_REG3, 0x08U);
    if (ret != VISTA_OK) return ret;

    /* CTRL_REG4: Block update, ±100g, high-resolution */
    ret = reg_write(ctx, H3L_REG_CTRL_REG4, 0x88U);
    if (ret != VISTA_OK) return ret;

    /* CTRL_REG5: Interrupt latch */
    ret = reg_write(ctx, H3L_REG_CTRL_REG5, 0x08U);

    return ret;
}

/**
 * @brief Read raw 3-axis data from H3LIS331DL.
 */
static vista_error_t h3lis331dl_read_raw(imu_context_t *ctx,
                                         imu_raw_sample_3axis_t *sample)
{
    uint8_t buf[6] = { 0U };
    vista_error_t ret;

    /* Read 6 bytes from OUT_X_L (auto-increment bit set) */
    ret = burst_read(ctx, H3L_REG_OUT_X_L | 0x80U, buf, 6U);
    if (ret != VISTA_OK) return ret;

    /* Parse accelerometer (little-endian) */
    sample->accel.x = (int16_t)((uint16_t)buf[0] | ((uint16_t)buf[1] << 8U));
    sample->accel.y = (int16_t)((uint16_t)buf[2] | ((uint16_t)buf[3] << 8U));
    sample->accel.z = (int16_t)((uint16_t)buf[4] | ((uint16_t)buf[5] << 8U));

    /* Timestamp */
    sample->timestamp_us = vista_get_dwt_cycles();

    /* Sequence */
    sample->sequence = ctx->sequence++;

    /* CRC */
    sample->crc = crc8_compute(buf, 6U);

    return VISTA_OK;
}

/* ========================================================================== */
/*  PUBLIC API — INITIALIZATION                                               */
/* ========================================================================== */

vista_error_t imu_init(uint8_t imu_id, imu_context_t *ctx)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return VISTA_ERR_RANGE;
    }

    /* Configure context based on IMU ID */
    switch (imu_id) {
    case 0U:
        ctx->spi_bus = VISTA_IMU0_SPI;
        ctx->cs_port = VISTA_IMU0_CS_PORT;
        ctx->cs_pin  = VISTA_IMU0_CS_PIN;
        ctx->type    = VISTA_IMU0_TYPE;
        break;
    case 1U:
        ctx->spi_bus = VISTA_IMU1_SPI;
        ctx->cs_port = VISTA_IMU1_CS_PORT;
        ctx->cs_pin  = VISTA_IMU1_CS_PIN;
        ctx->type    = VISTA_IMU1_TYPE;
        break;
    case 2U:
        ctx->spi_bus = VISTA_IMU2_SPI;
        ctx->cs_port = VISTA_IMU2_CS_PORT;
        ctx->cs_pin  = VISTA_IMU2_CS_PIN;
        ctx->type    = VISTA_IMU2_TYPE;
        break;
    default:
        return VISTA_ERR_RANGE;
    }

    ctx->status = IMU_STATUS_UNINIT;
    ctx->sequence = 0U;
    ctx->error_count = 0U;
    ctx->data_ready = false;

    /* Configure sensor-specific registers */
    vista_error_t ret;
    if (ctx->type == IMU_TYPE_IAM20680HP) {
        ret = iam20680hp_configure(ctx);
    } else {
        ret = h3lis331dl_configure(ctx);
    }

    if (ret == VISTA_OK) {
        /* Verify WHO_AM_I */
        uint8_t who_am_i = 0U;
        ret = imu_reg_read(imu_id, ctx,
                           (ctx->type == IMU_TYPE_IAM20680HP) ?
                           IAM_REG_WHO_AM_I : H3L_REG_WHO_AM_I,
                           &who_am_i);
        if (ret == VISTA_OK) {
            uint8_t expected = (ctx->type == IMU_TYPE_IAM20680HP) ?
                               IAM20680HP_WHO_AM_I : H3LIS331DL_WHO_AM_I;
            if (who_am_i != expected) {
                ctx->status = IMU_STATUS_ERROR;
                ret = VISTA_ERR_SENSOR;
            } else {
                ctx->status = IMU_STATUS_READY;
            }
        }
    }

    if (ret != VISTA_OK) {
        ctx->error_count++;
        ctx->status = IMU_STATUS_ERROR;
    }

    return ret;
}

vista_error_t imu_init_all(imu_context_t contexts[VISTA_IMU_COUNT])
{
    vista_error_t worst_ret = VISTA_OK;

    for (uint8_t i = 0U; i < VISTA_IMU_COUNT; i++) {
        vista_error_t ret = imu_init(i, &contexts[i]);
        if (ret != VISTA_OK) {
            worst_ret = ret;
        }
    }

    return worst_ret;
}

vista_error_t imu_set_calibration(uint8_t imu_id, imu_context_t *ctx,
                                  const imu_cal_t *cal)
{
    if ((ctx == NULL) || (cal == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return VISTA_ERR_RANGE;
    }

    ctx->calibration = *cal;
    return VISTA_OK;
}

vista_error_t imu_reconfigure(uint8_t imu_id, imu_context_t *ctx,
                              uint8_t accel_fs, uint16_t gyro_fs)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return VISTA_ERR_RANGE;
    }

    if (ctx->type == IMU_TYPE_H3LIS331DL) {
        /* H3LIS331DL only has configurable full-scale */
        return VISTA_OK;
    }

    /* Map accel full-scale to register value */
    uint8_t accel_reg;
    switch (accel_fs) {
    case 2U:  accel_reg = 0x00U; break;
    case 4U:  accel_reg = 0x08U; break;
    case 8U:  accel_reg = 0x10U; break;
    case 16U: accel_reg = 0x18U; break;
    default:  return VISTA_ERR_RANGE;
    }

    /* Map gyro full-scale to register value */
    uint8_t gyro_reg;
    switch (gyro_fs) {
    case 250U:  gyro_reg = 0x00U; break;
    case 500U:  gyro_reg = 0x08U; break;
    case 1000U: gyro_reg = 0x10U; break;
    case 2000U: gyro_reg = 0x18U; break;
    default:    return VISTA_ERR_RANGE;
    }

    vista_error_t ret;
    ret = reg_write(ctx, IAM_REG_ACCEL_CONFIG, accel_reg);
    if (ret == VISTA_OK) {
        ret = reg_write(ctx, IAM_REG_GYRO_CONFIG, gyro_reg);
    }

    return ret;
}

/* ========================================================================== */
/*  PUBLIC API — DATA ACQUISITION                                             */
/* ========================================================================== */

vista_error_t imu_read_raw(uint8_t imu_id, imu_context_t *ctx, void *sample)
{
    if ((ctx == NULL) || (sample == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return VISTA_ERR_RANGE;
    }

    if (ctx->type == IMU_TYPE_IAM20680HP) {
        return iam20680hp_read_raw(ctx, (imu_raw_sample_6axis_t *)sample);
    } else {
        return h3lis331dl_read_raw(ctx, (imu_raw_sample_3axis_t *)sample);
    }
}

vista_error_t imu_read_dma_start(uint8_t imu_id, imu_context_t *ctx)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return VISTA_ERR_RANGE;
    }

    if (ctx->data_ready) {
        return VISTA_ERR_BUSY;
    }

    /* TODO: Start SPI DMA transfer
     * 1. Assert CS
     * 2. Configure DMA source/dest
     * 3. Enable SPI DMA request
     * 4. Start DMA transfer
     * CS will be deasserted by DMA TC interrupt
     */

    cs_assert(ctx);

    /* Placeholder — actual DMA setup needed */
    ctx->data_ready = false;

    return VISTA_OK;
}

bool imu_dma_poll(uint8_t imu_id, imu_context_t *ctx)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return false;
    }

    if (ctx->data_ready) {
        ctx->data_ready = false;
        return true;
    }

    return false;
}

void imu_drdy_isr(uint8_t imu_id)
{
    /* Access firmware context — requires g_isr_ctx from main.c */
    /* TODO: Get firmware context and access imu[imu_id] */
    /* This is called from DMA TC or EXTI ISR */

    /* Placeholder: In full implementation, this would:
     * 1. Deassert CS (if DMA-controlled)
     * 2. Set data_ready flag
     * 3. Increment sequence counter
     */
}

/* ========================================================================== */
/*  PUBLIC API — DATA PROCESSING                                              */
/* ========================================================================== */

void imu_convert_6axis(const imu_raw_sample_6axis_t *raw,
                       const imu_cal_t *cal, uint8_t imu_id,
                       imu_sample_t *out)
{
    if ((raw == NULL) || (cal == NULL) || (out == NULL)) {
        return;
    }

    /* IAM-20680HP sensitivity:
     * Accel: ±4g -> 8192 LSB/g
     * Gyro:  ±250 dps -> 131 LSB/dps
     */
    const float accel_sensitivity = (4.0f * ESKF_GRAVITY) / 8192.0f;
    const float gyro_sensitivity  = (250.0f * 0.017453293f) / 131.0f;

    /* Apply calibration and convert to SI units */
    out->accel_ms2.x = ((float)raw->accel.x * accel_sensitivity)
                        + cal->accel_offset.x;
    out->accel_ms2.y = ((float)raw->accel.y * accel_sensitivity)
                        + cal->accel_offset.y;
    out->accel_ms2.z = ((float)raw->accel.z * accel_sensitivity)
                        + cal->accel_offset.z;

    out->gyro_rads.x = ((float)raw->gyro.x * gyro_sensitivity)
                        + cal->gyro_offset.x;
    out->gyro_rads.y = ((float)raw->gyro.y * gyro_sensitivity)
                        + cal->gyro_offset.y;
    out->gyro_rads.z = ((float)raw->gyro.z * gyro_sensitivity)
                        + cal->gyro_offset.z;

    /* Temperature conversion: TEMP_OUT = (raw / 333.87) + 21.0 */
    out->temperature_c = ((float)raw->temp_raw / 333.87f) + 21.0f;

    out->timestamp_us = raw->timestamp_us;
    out->sequence = raw->sequence;
    out->imu_id = imu_id;
}

void imu_convert_3axis(const imu_raw_sample_3axis_t *raw,
                       const imu_cal_t *cal, uint8_t imu_id,
                       imu_sample_t *out)
{
    if ((raw == NULL) || (cal == NULL) || (out == NULL)) {
        return;
    }

    /* H3LIS331DL sensitivity: ±100g -> 176 LSB/g */
    const float accel_sensitivity = (100.0f * ESKF_GRAVITY) / 176.0f;

    out->accel_ms2.x = ((float)raw->accel.x * accel_sensitivity)
                        + cal->accel_offset.x;
    out->accel_ms2.y = ((float)raw->accel.y * accel_sensitivity)
                        + cal->accel_offset.y;
    out->accel_ms2.z = ((float)raw->accel.z * accel_sensitivity)
                        + cal->accel_offset.z;

    /* No gyroscope on H3LIS331DL */
    out->gyro_rads.x = 0.0f;
    out->gyro_rads.y = 0.0f;
    out->gyro_rads.z = 0.0f;

    out->temperature_c = 0.0f;
    out->timestamp_us = raw->timestamp_us;
    out->sequence = raw->sequence;
    out->imu_id = imu_id;
}

bool imu_verify_crc(const uint8_t *data, uint8_t len, uint8_t expected)
{
    uint8_t computed = crc8_compute(data, len);
    return (computed == expected);
}

/* ========================================================================== */
/*  PUBLIC API — STATUS / DIAGNOSTICS                                         */
/* ========================================================================== */

imu_status_t imu_get_status(uint8_t imu_id, const imu_context_t *ctx)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return IMU_STATUS_UNINIT;
    }
    return ctx->status;
}

uint32_t imu_get_error_count(uint8_t imu_id, const imu_context_t *ctx)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return 0U;
    }
    return ctx->error_count;
}

vista_error_t imu_self_test(uint8_t imu_id, imu_context_t *ctx)
{
    if ((ctx == NULL) || (imu_id >= VISTA_IMU_COUNT)) {
        return VISTA_ERR_RANGE;
    }

    if (ctx->type == IMU_TYPE_IAM20680HP) {
        /* IAM-20680HP self-test:
         * 1. Read accel/gyro in normal mode
         * 2. Enable self-test (ACCEL_CONFIG: 0x80, GYRO_CONFIG: 0x80)
         * 3. Read accel/gyro in self-test mode
         * 4. Compute difference
         * 5. Check against datasheet min/max values
         * 6. Restore normal mode
         */

        /* Save current config */
        uint8_t accel_cfg, gyro_cfg;
        (void)reg_read(ctx, IAM_REG_ACCEL_CONFIG, &accel_cfg);
        (void)reg_read(ctx, IAM_REG_GYRO_CONFIG, &gyro_cfg);

        /* Enable self-test */
        (void)reg_write(ctx, IAM_REG_ACCEL_CONFIG, accel_cfg | 0x80U);
        (void)reg_write(ctx, IAM_REG_GYRO_CONFIG, gyro_cfg | 0x80U);

        /* TODO: Wait for settling, read values, compare, restore */

        /* Restore normal mode */
        (void)reg_write(ctx, IAM_REG_ACCEL_CONFIG, accel_cfg);
        (void)reg_write(ctx, IAM_REG_GYRO_CONFIG, gyro_cfg);
    } else {
        /* H3LIS331DL self-test: Enable SELF_TEST bits in CTRL_REG4 */
        uint8_t ctrl4;
        (void)reg_read(ctx, H3L_REG_CTRL_REG4, &ctrl4);
        (void)reg_write(ctx, H3L_REG_CTRL_REG4, ctrl4 | 0x02U);

        /* TODO: Read data, verify, restore */

        (void)reg_write(ctx, H3L_REG_CTRL_REG4, ctrl4);
    }

    ctx->status = IMU_STATUS_READY;
    return VISTA_OK;
}

/* ========================================================================== */
/*  PUBLIC API — REGISTER ACCESS                                              */
/* ========================================================================== */

vista_error_t imu_reg_read(uint8_t imu_id, imu_context_t *ctx,
                           uint8_t reg, uint8_t *value)
{
    if ((ctx == NULL) || (value == NULL)) {
        return VISTA_ERR_RANGE;
    }
    return reg_read(ctx, reg, value);
}

vista_error_t imu_reg_write(uint8_t imu_id, imu_context_t *ctx,
                            uint8_t reg, uint8_t value)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }
    return reg_write(ctx, reg, value);
}
