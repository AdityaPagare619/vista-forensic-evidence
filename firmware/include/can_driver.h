/**
 * @file can_driver.h
 * @brief CAN Bus Interface for VISTA 2.0
 *
 * Driver interface for dual FDCAN peripherals on STM32H743:
 *   - FDCAN1: Vehicle bus (500 kbps nominal, 2 Mbps FD data)
 *   - FDCAN2: Internal sensor bus
 *
 * Supports CAN FD with both classic and BRS (bit-rate switch) modes.
 * Provides interrupt-driven TX/RX with hardware FIFO management.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note MISRA-C:2012 compliant.
 */

#ifndef CAN_DRIVER_H
#define CAN_DRIVER_H

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
 * @brief CAN channel identifier
 */
typedef enum {
    CAN_CHANNEL_VEHICLE = 0,    /**< FDCAN1 — vehicle bus */
    CAN_CHANNEL_SENSOR  = 1,    /**< FDCAN2 — sensor bus */
    CAN_CHANNEL_COUNT   = 2
} can_channel_t;

/**
 * @brief CAN bus status
 */
typedef enum {
    CAN_STATUS_UNINIT   = 0,    /**< Not initialized */
    CAN_STATUS_OK       = 1,    /**< Bus active, no errors */
    CAN_STATUS_WARNING  = 2,    /**< Warning level errors */
    CAN_STATUS_PASSIVE  = 3,    /**< Error passive state */
    CAN_STATUS_BUS_OFF  = 4,    /**< Bus-off state */
    CAN_STATUS_OVERFLOW = 5     /**< RX FIFO overflow */
} can_status_t;

/**
 * @brief CAN message format
 */
typedef enum {
    CAN_FMT_CLASSIC    = 0,     /**< Classic CAN (up to 8 bytes) */
    CAN_FMT_FD         = 1,     /**< CAN FD without BRS */
    CAN_FMT_FD_BRS     = 2      /**< CAN FD with bit-rate switch */
} can_format_t;

/**
 * @brief CAN frame structure
 */
typedef struct {
    uint32_t id;                /**< CAN identifier (11 or 29 bit) */
    uint8_t dlc;                /**< Data length code (0..8, or 9..15 for FD) */
    uint8_t data[64];           /**< Frame data (up to 64 bytes for FD) */
    can_format_t format;        /**< Frame format */
    bool extended;              /**< true for 29-bit extended ID */
    bool rtr;                   /**< Remote transmission request */
    uint32_t timestamp_us;      /**< Receive timestamp */
    can_channel_t channel;      /**< Source channel */
} can_frame_t;

/**
 * @brief CAN TX message with priority
 */
typedef struct {
    can_frame_t frame;          /**< The CAN frame */
    uint8_t priority;           /**< Priority (0 = highest) */
    bool pending;               /**< true if queued for transmission */
} can_tx_msg_t;

/**
 * @brief CAN bus statistics
 */
typedef struct {
    uint32_t tx_count;          /**< Total frames transmitted */
    uint32_t rx_count;          /**< Total frames received */
    uint32_t tx_error_count;    /**< TX error count */
    uint32_t rx_error_count;    /**< RX error count */
    uint32_t overflow_count;    /**< RX overflow count */
    uint32_t last_error_code;   /**< Last LEC (last error code) */
    can_status_t status;        /**< Current bus status */
} can_stats_t;

/**
 * @brief CAN RX callback function type
 *
 * @param[in] frame  Received CAN frame.
 */
typedef void (*can_rx_callback_t)(const can_frame_t *frame);

/**
 * @brief CAN driver context (opaque internal state)
 */
typedef struct {
    can_channel_t channel;          /**< Channel ID */
    can_status_t status;            /**< Current status */
    can_rx_callback_t rx_callback;  /**< Application RX callback */
    can_stats_t stats;              /**< Statistics */
    can_tx_msg_t tx_queue[VISTA_CAN_TX_QUEUE_SIZE];  /**< TX queue */
    uint8_t tx_head;                /**< TX queue head index */
    uint8_t tx_tail;                /**< TX queue tail index */
    uint8_t tx_count;               /**< TX queue item count */
    bool fd_enabled;                /**< CAN FD mode enabled */
    bool initialized;               /**< Initialization complete */
} can_context_t;

/* ========================================================================== */
/*  INITIALIZATION                                                            */
/* ========================================================================== */

/**
 * @brief Initialize a CAN channel.
 *
 * Configures FDCAN peripheral, message RAM, TX/RX FIFOs, and enables
 * interrupts. Puts bus into active state.
 *
 * @param[in] channel  CAN channel (VEHICLE or SENSOR).
 * @param[in] ctx      Caller-allocated context.
 * @param[in] fd_en    Enable CAN FD mode.
 * @return VISTA_OK on success.
 */
vista_error_t can_init(can_channel_t channel, can_context_t *ctx, bool fd_en);

/**
 * @brief De-initialize a CAN channel.
 *
 * @param[in] channel  CAN channel.
 * @param[in] ctx      Context to de-init.
 * @return VISTA_OK on success.
 */
vista_error_t can_deinit(can_channel_t channel, can_context_t *ctx);

/**
 * @brief Register an RX callback for incoming frames.
 *
 * @param[in] ctx       CAN context.
 * @param[in] callback  Callback function (NULL to unregister).
 * @return VISTA_OK on success.
 */
vista_error_t can_register_rx_callback(can_context_t *ctx,
                                       can_rx_callback_t callback);

/* ========================================================================== */
/*  TRANSMISSION                                                              */
/* ========================================================================== */

/**
 * @brief Transmit a CAN frame (blocking).
 *
 * @param[in] ctx    CAN context.
 * @param[in] frame  Frame to transmit.
 * @return VISTA_OK on success, VISTA_ERR_BUSY if TX FIFO full.
 */
vista_error_t can_transmit(can_context_t *ctx, const can_frame_t *frame);

/**
 * @brief Enqueue a CAN frame for interrupt-driven transmission.
 *
 * @param[in] ctx       CAN context.
 * @param[in] frame     Frame to enqueue.
 * @param[in] priority  Priority (0 = highest).
 * @return VISTA_OK on success, VISTA_ERR_OVERFLOW if queue full.
 */
vista_error_t can_transmit_queue(can_context_t *ctx, const can_frame_t *frame,
                                 uint8_t priority);

/**
 * @brief Process TX queue (call from main loop).
 *
 * Sends queued frames if TX FIFO has space. Called periodically.
 *
 * @param[in] ctx  CAN context.
 * @return Number of frames sent.
 */
uint8_t can_tx_process_queue(can_context_t *ctx);

/* ========================================================================== */
/*  RECEPTION                                                                 */
/* ========================================================================== */

/**
 * @brief Poll for received CAN frames (non-blocking).
 *
 * @param[in]  ctx    CAN context.
 * @param[out] frame  Received frame output.
 * @return VISTA_OK if a frame was read, VISTA_ERR_TIMEOUT if none.
 */
vista_error_t can_receive(can_context_t *ctx, can_frame_t *frame);

/**
 * @brief CAN RX FIFO 0 interrupt handler.
 *
 * Reads frames from hardware FIFO and dispatches to callback.
 * ISR-safe — does not block.
 *
 * @param[in] ctx  CAN context.
 */
void can_rx_isr(can_context_t *ctx);

/**
 * @brief CAN TX complete interrupt handler.
 *
 * @param[in] ctx  CAN context.
 */
void can_tx_isr(can_context_t *ctx);

/**
 * @brief CAN error interrupt handler.
 *
 * @param[in] ctx  CAN context.
 */
void can_error_isr(can_context_t *ctx);

/* ========================================================================== */
/*  STATUS / DIAGNOSTICS                                                      */
/* ========================================================================== */

/**
 * @brief Get CAN bus statistics.
 *
 * @param[in] ctx  CAN context.
 * @return Pointer to statistics structure.
 */
const can_stats_t *can_get_stats(const can_context_t *ctx);

/**
 * @brief Get current bus status.
 *
 * @param[in] ctx  CAN context.
 * @return Current status.
 */
can_status_t can_get_status(const can_context_t *ctx);

/**
 * @brief Reset CAN error counters.
 *
 * @param[in] ctx  CAN context.
 */
void can_reset_errors(can_context_t *ctx);

/**
 * @brief Perform CAN bus-off recovery.
 *
 * @param[in] ctx  CAN context.
 * @return VISTA_OK on successful recovery.
 */
vista_error_t can_recover_bus_off(can_context_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* CAN_DRIVER_H */
