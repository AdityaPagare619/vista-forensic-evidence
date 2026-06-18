/**
 * @file camera_driver.h
 * @brief Camera Interface for VISTA 2.0
 *
 * Driver interface for Himax HM01B0 camera via DCMI (Digital Camera
 * Memory Interface) with DMA for zero-copy frame capture.
 *
 * Supports QVGA (320×240) grayscale at up to 30 fps. Frames are
 * double-buffered for continuous capture during event recording.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note MISRA-C:2012 compliant.
 */

#ifndef CAMERA_DRIVER_H
#define CAMERA_DRIVER_H

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
 * @brief Camera status
 */
typedef enum {
    CAM_STATUS_UNINIT   = 0,    /**< Not initialized */
    CAM_STATUS_STOPPED  = 1,    /**< Initialized, not capturing */
    CAM_STATUS_RUNNING  = 2,    /**< Actively capturing frames */
    CAM_STATUS_ERROR    = 3     /**< Hardware or I2C config error */
} camera_status_t;

/**
 * @brief Camera frame buffer state
 */
typedef enum {
    CAM_BUF_FREE     = 0,       /**< Available for DMA */
    CAM_BUF_Capturing = 1,      /**< DMA is writing to this buffer */
    CAM_BUF_Ready    = 2,       /**< Frame complete, ready for processing */
    CAM_BUF_Processing = 3      /**< CPU is reading this buffer */
} camera_buf_state_t;

/**
 * @brief Camera frame metadata
 */
typedef struct {
    uint32_t frame_number;       /**< Monotonic frame counter */
    uint32_t timestamp_us;       /**< Frame start timestamp */
    uint16_t width;              /**< Frame width in pixels */
    uint16_t height;             /**< Frame height in pixels */
    uint8_t pixel_format;        /**< 0 = grayscale, 1 = RGB565 */
    uint8_t status;              /**< 0 = OK, nonzero = error flags */
    uint16_t exposure_us;        /**< Exposure time (if readable) */
    uint8_t gain;                /**< Analog gain (if readable) */
} camera_frame_meta_t;

/**
 * @brief Camera frame buffer
 */
typedef struct {
    uint8_t data[VISTA_CAMERA_FRAME_SIZE];  /**< Pixel data */
    camera_frame_meta_t meta;               /**< Frame metadata */
    camera_buf_state_t state;               /**< Buffer state */
} camera_frame_t;

/**
 * @brief Camera frame callback
 *
 * @param[in] frame  Pointer to captured frame.
 */
typedef void (*camera_frame_callback_t)(const camera_frame_t *frame);

/**
 * @brief Camera driver context (opaque internal state)
 */
typedef struct {
    camera_status_t status;                 /**< Current status */
    camera_frame_t frames[VISTA_CAMERA_BUF_COUNT];  /**< Frame buffers */
    volatile uint8_t dma_write_idx;         /**< Current DMA buffer index */
    volatile uint8_t proc_read_idx;         /**< Current processing buffer */
    uint16_t sequence;                      /**< Frame sequence counter */
    uint32_t dropped_count;                 /**< Dropped frame count */
    camera_frame_callback_t callback;       /**< Frame complete callback */
    bool initialized;                       /**< Init complete flag */
} camera_context_t;

/* ========================================================================== */
/*  INITIALIZATION                                                            */
/* ========================================================================== */

/**
 * @brief Initialize the camera subsystem.
 *
 * Performs I2C configuration of HM01B0 registers, sets up DCMI interface,
 * configures DMA, and allocates frame buffers.
 *
 * @param[in] ctx  Caller-allocated camera context.
 * @return VISTA_OK on success, VISTA_ERR_SENSOR if camera not detected.
 */
vista_error_t camera_init(camera_context_t *ctx);

/**
 * @brief De-initialize camera and release DMA resources.
 *
 * @param[in] ctx  Camera context.
 * @return VISTA_OK on success.
 */
vista_error_t camera_deinit(camera_context_t *ctx);

/**
 * @brief Register a frame completion callback.
 *
 * @param[in] ctx       Camera context.
 * @param[in] callback  Callback function (NULL to unregister).
 * @return VISTA_OK on success.
 */
vista_error_t camera_register_callback(camera_context_t *ctx,
                                       camera_frame_callback_t callback);

/* ========================================================================== */
/*  CAPTURE CONTROL                                                           */
/* ========================================================================== */

/**
 * @brief Start continuous frame capture.
 *
 * @param[in] ctx  Camera context.
 * @return VISTA_OK on success.
 */
vista_error_t camera_start(camera_context_t *ctx);

/**
 * @brief Stop frame capture.
 *
 * @param[in] ctx  Camera context.
 * @return VISTA_OK on success.
 */
vista_error_t camera_stop(camera_context_t *ctx);

/**
 * @brief Capture a single frame (blocking).
 *
 * Captures one frame into the specified buffer. Blocks until frame
 * is complete or timeout.
 *
 * @param[in]  ctx     Camera context.
 * @param[out] frame   Frame buffer to capture into.
 * @param[in]  timeout_ms  Maximum wait time.
 * @return VISTA_OK on success, VISTA_ERR_TIMEOUT on timeout.
 */
vista_error_t camera_capture_single(camera_context_t *ctx,
                                    camera_frame_t *frame,
                                    uint32_t timeout_ms);

/* ========================================================================== */
/*  BUFFER MANAGEMENT                                                         */
/* ========================================================================== */

/**
 * @brief Get the next completed frame for processing.
 *
 * @param[in]  ctx    Camera context.
 * @param[out] frame  Pointer to the ready frame (or NULL).
 * @return VISTA_OK if frame available, VISTA_ERR_TIMEOUT if none.
 */
vista_error_t camera_frame_get(camera_context_t *ctx, camera_frame_t **frame);

/**
 * @brief Release a processed frame buffer.
 *
 * @param[in] ctx    Camera context.
 * @param[in] frame  Frame to release.
 */
void camera_frame_release(camera_context_t *ctx, camera_frame_t *frame);

/* ========================================================================== */
/*  DMA / ISR HANDLERS                                                        */
/* ========================================================================== */

/**
 * @brief DCMI DMA half-transfer interrupt handler.
 *
 * ISR-safe. Called when first half of frame buffer is filled.
 *
 * @param[in] ctx  Camera context.
 */
void camera_dma_ht_isr(camera_context_t *ctx);

/**
 * @brief DCMI DMA transfer-complete interrupt handler.
 *
 * ISR-safe. Called when full frame is captured. Swaps buffers and
 * invokes callback if registered.
 *
 * @param[in] ctx  Camera context.
 */
void camera_dma_tc_isr(camera_context_t *ctx);

/* ========================================================================== */
/*  CONFIGURATION                                                             */
/* ========================================================================== */

/**
 * @brief Set camera frame rate.
 *
 * @param[in] ctx     Camera context.
 * @param[in] fps     Target frame rate (1..30).
 * @return VISTA_OK on success.
 */
vista_error_t camera_set_fps(camera_context_t *ctx, uint8_t fps);

/**
 * @brief Set camera exposure manually.
 *
 * @param[in] ctx         Camera context.
 * @param[in] exposure_us Exposure time in microseconds.
 * @return VISTA_OK on success.
 */
vista_error_t camera_set_exposure(camera_context_t *ctx, uint32_t exposure_us);

/**
 * @brief Set camera gain.
 *
 * @param[in] ctx    Camera context.
 * @param[in] gain   Gain value (0..63 for HM01B0).
 * @return VISTA_OK on success.
 */
vista_error_t camera_set_gain(camera_context_t *ctx, uint8_t gain);

/* ========================================================================== */
/*  STATUS / DIAGNOSTICS                                                      */
/* ========================================================================== */

/**
 * @brief Get camera status.
 *
 * @param[in] ctx  Camera context.
 * @return Current status.
 */
camera_status_t camera_get_status(const camera_context_t *ctx);

/**
 * @brief Get dropped frame count.
 *
 * @param[in] ctx  Camera context.
 * @return Number of frames dropped since init.
 */
uint32_t camera_get_dropped_count(const camera_context_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* CAMERA_DRIVER_H */
