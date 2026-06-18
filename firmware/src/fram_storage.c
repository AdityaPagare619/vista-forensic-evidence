/**
 * @file fram_storage.c
 * @brief FRAM Crash-Safe Storage Implementation
 *
 * Driver for SPI-connected Ferroelectric RAM (FRAM) for persistent
 * crash-safe storage. FRAM provides:
 *   - 10^14 write cycle endurance (vs 10^5 for Flash/EEPROM)
 *   - Write speeds comparable to SRAM (no write delay)
 *   - Non-volatile with battery-free retention
 *
 * Memory map:
 *   Region 0: System configuration (4 KB, offset 0x0000)
 *   Region 1: Calibration data (4 KB, offset 0x1000)
 *   Region 2: Evidence chain (16 KB, offset 0x2000)
 *   Region 3: Event log (8 KB, offset 0x6000)
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 */

#include "firmware.h"
#include <string.h>

/* ========================================================================== */
/*  FRAM MEMORY MAP                                                           */
/* ========================================================================== */

/** @brief Region base offsets in FRAM */
static const uint32_t REGION_OFFSETS[] = {
    0x0000U,    /* FRAM_REGION_CONFIG:   0x0000 - 0x0FFF (4 KB) */
    0x1000U,    /* FRAM_REGION_CAL:      0x1000 - 0x1FFF (4 KB) */
    0x2000U,    /* FRAM_REGION_EVIDENCE: 0x2000 - 0x5FFF (16 KB) */
    0x6000U     /* FRAM_REGION_LOG:      0x6000 - 0x7FFF (8 KB) */
};

/** @brief Region sizes */
static const uint16_t REGION_SIZES[] = {
    0x1000,     /* 4 KB */
    0x1000,     /* 4 KB */
    0x4000,     /* 16 KB */
    0x2000      /* 8 KB */
};

/* ========================================================================== */
/*  SPI HELPERS                                                               */
/* ========================================================================== */

/** @brief FRAM SPI context (file-scope) */
static struct {
    uint8_t spi_bus;
    uint8_t cs_port;
    uint8_t cs_pin;
    bool initialized;
} g_fram;

/**
 * @brief Assert FRAM chip-select.
 */
static inline void fram_cs_assert(void)
{
    /* TODO: HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET) */
}

/**
 * @brief Deassert FRAM chip-select.
 */
static inline void fram_cs_deassert(void)
{
    /* TODO: HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET) */
}

/**
 * @brief SPI transfer for FRAM.
 */
static vista_error_t fram_spi_transfer(const uint8_t *tx, uint8_t *rx,
                                       uint16_t len)
{
    /* TODO: HAL_SPI_TransmitReceive(SPIHandle, tx, rx, len, timeout) */
    (void)tx;
    (void)rx;
    (void)len;
    return VISTA_OK;
}

/* ========================================================================== */
/*  FRAM BASIC OPERATIONS                                                     */
/* ========================================================================== */

/**
 * @brief Enable FRAM write operations.
 */
static vista_error_t fram_write_enable(void)
{
    uint8_t cmd = VISTA_FRAM_WREN;
    uint8_t rx = 0U;

    fram_cs_assert();
    vista_error_t ret = fram_spi_transfer(&cmd, &rx, 1U);
    fram_cs_deassert();

    return ret;
}

/**
 * @brief Disable FRAM write operations.
 */
static vista_error_t fram_write_disable(void)
{
    uint8_t cmd = VISTA_FRAM_WRDI;
    uint8_t rx = 0U;

    fram_cs_assert();
    vista_error_t ret = fram_spi_transfer(&cmd, &rx, 1U);
    fram_cs_deassert();

    return ret;
}

/**
 * @brief Read FRAM status register.
 */
static vista_error_t fram_read_status(uint8_t *status)
{
    uint8_t tx[2] = { VISTA_FRAM_RDSR, 0x00U };
    uint8_t rx[2] = { 0U, 0U };

    fram_cs_assert();
    vista_error_t ret = fram_spi_transfer(tx, rx, 2U);
    fram_cs_deassert();

    if (ret == VISTA_OK) {
        *status = rx[1];
    }
    return ret;
}

/**
 * @brief Read FRAM JEDEC ID for device verification.
 */
static vista_error_t fram_read_id(uint8_t *manufacturer, uint8_t *density)
{
    uint8_t tx[4] = { VISTA_FRAM_RDID, 0x00U, 0x00U, 0x00U };
    uint8_t rx[4] = { 0U, 0U, 0U, 0U };

    fram_cs_assert();
    vista_error_t ret = fram_spi_transfer(tx, rx, 4U);
    fram_cs_deassert();

    if (ret == VISTA_OK) {
        *manufacturer = rx[1];
        *density = rx[3];
    }
    return ret;
}

/**
 * @brief Wait for any ongoing write to complete (poll WIP bit).
 *
 * FRAM writes are nearly instantaneous (< 50 µs), but we check
 * the WIP bit for safety.
 */
static vista_error_t fram_wait_ready(void)
{
    uint8_t status;
    vista_error_t ret;
    uint32_t timeout = 10000U;  /* 10 ms timeout */

    do {
        ret = fram_read_status(&status);
        if (ret != VISTA_OK) {
            return ret;
        }
        timeout--;
    } while ((status & 0x01U) != 0U && timeout > 0U);

    if (timeout == 0U) {
        return VISTA_ERR_TIMEOUT;
    }

    return VISTA_OK;
}

/* ========================================================================== */
/*  PUBLIC API — INITIALIZATION                                               */
/* ========================================================================== */

vista_error_t fram_init(void)
{
    /* Configure FRAM context */
    g_fram.spi_bus = VISTA_FRAM_SPI;
    g_fram.cs_port = VISTA_FRAM_CS_PORT;
    g_fram.cs_pin = VISTA_FRAM_CS_PIN;
    g_fram.initialized = false;

    /* TODO: Initialize SPI peripheral for FRAM */

    /* Verify FRAM is present by reading JEDEC ID */
    uint8_t manufacturer, density;
    vista_error_t ret = fram_read_id(&manufacturer, &density);
    if (ret != VISTA_OK) {
        return VISTA_ERR_STORAGE;
    }

    /* Verify expected manufacturer (e.g., Fujitsu MB85RC64) */
    /* TODO: Add specific manufacturer ID check based on FRAM part */

    g_fram.initialized = true;
    return VISTA_OK;
}

/* ========================================================================== */
/*  PUBLIC API — READ / WRITE                                                 */
/* ========================================================================== */

vista_error_t fram_read(uint32_t addr, uint8_t *data, uint16_t len)
{
    if (!g_fram.initialized) {
        return VISTA_ERR_STATE;
    }

    if ((addr + len) > VISTA_FRAM_SIZE) {
        return VISTA_ERR_RANGE;
    }

    /* Build FRAM read command: [0x03, addr_high, addr_low, data...] */
    uint8_t tx[3 + 512];  /* Max read size limited by buffer */
    uint8_t rx[3 + 512];

    if ((len + 3U) > sizeof(tx)) {
        return VISTA_ERR_RANGE;
    }

    tx[0] = VISTA_FRAM_READ;
    tx[1] = (uint8_t)((addr >> 8U) & 0xFFU);
    tx[2] = (uint8_t)(addr & 0xFFU);

    (void)memset(&tx[3], 0x00U, len);

    fram_cs_assert();
    vista_error_t ret = fram_spi_transfer(tx, rx, (uint16_t)(len + 3U));
    fram_cs_deassert();

    if (ret == VISTA_OK) {
        (void)memcpy(data, &rx[3], len);
    }

    return ret;
}

vista_error_t fram_write(uint32_t addr, const uint8_t *data, uint16_t len)
{
    if (!g_fram.initialized) {
        return VISTA_ERR_STATE;
    }

    if ((addr + len) > VISTA_FRAM_SIZE) {
        return VISTA_ERR_RANGE;
    }

    /* Enable writes */
    vista_error_t ret = fram_write_enable();
    if (ret != VISTA_OK) {
        return ret;
    }

    /* Build FRAM write command: [0x02, addr_high, addr_low, data...] */
    uint8_t tx[3 + 512];

    if ((len + 3U) > sizeof(tx)) {
        return VISTA_ERR_RANGE;
    }

    tx[0] = VISTA_FRAM_WRITE;
    tx[1] = (uint8_t)((addr >> 8U) & 0xFFU);
    tx[2] = (uint8_t)(addr & 0xFFU);
    (void)memcpy(&tx[3], data, len);

    uint8_t rx[3 + 512];
    (void)memset(rx, 0, sizeof(rx));

    fram_cs_assert();
    ret = fram_spi_transfer(tx, rx, (uint16_t)(len + 3U));
    fram_cs_deassert();

    if (ret == VISTA_OK) {
        /* Wait for write to complete */
        ret = fram_wait_ready();
    }

    /* Disable writes */
    (void)fram_write_disable();

    return ret;
}

vista_error_t fram_erase_region(fram_region_t region)
{
    if ((uint32_t)region >= (uint32_t)FRAM_REGION_COUNT) {
        return VISTA_ERR_RANGE;
    }

    uint32_t offset = REGION_OFFSETS[region];
    uint16_t size = REGION_SIZES[region];

    /* Fill with 0xFF */
    uint8_t fill_buf[64];
    (void)memset(fill_buf, 0xFFU, sizeof(fill_buf));

    uint16_t remaining = size;
    uint32_t addr = offset;

    while (remaining > 0U) {
        uint16_t chunk = (remaining > sizeof(fill_buf)) ?
                         (uint16_t)sizeof(fill_buf) : remaining;

        vista_error_t ret = fram_write(addr, fill_buf, chunk);
        if (ret != VISTA_OK) {
            return ret;
        }

        addr += chunk;
        remaining -= chunk;
    }

    return VISTA_OK;
}

/* ========================================================================== */
/*  STRUCTURED READ / WRITE (for config and calibration)                      */
/* ========================================================================== */

vista_error_t fram_read_config(void *config, uint16_t size)
{
    return fram_read(REGION_OFFSETS[FRAM_REGION_CONFIG],
                     (uint8_t *)config, size);
}

vista_error_t fram_write_config(const void *config, uint16_t size)
{
    return fram_write(REGION_OFFSETS[FRAM_REGION_CONFIG],
                      (const uint8_t *)config, size);
}

vista_error_t fram_read_calibration(void *cal, uint16_t size)
{
    return fram_read(REGION_OFFSETS[FRAM_REGION_CAL],
                     (uint8_t *)cal, size);
}

vista_error_t fram_write_calibration(const void *cal, uint16_t size)
{
    return fram_write(REGION_OFFSETS[FRAM_REGION_CAL],
                      (const uint8_t *)cal, size);
}

vista_error_t fram_read_log(void *log, uint16_t size)
{
    return fram_read(REGION_OFFSETS[FRAM_REGION_LOG],
                     (uint8_t *)log, size);
}

vista_error_t fram_write_log(const void *log, uint16_t size)
{
    return fram_write(REGION_OFFSETS[FRAM_REGION_LOG],
                      (const uint8_t *)log, size);
}
