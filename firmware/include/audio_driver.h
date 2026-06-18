/**
 * @file audio_driver.h
 * @brief Audio / MEMS Microphone Interface for VISTA 2.0
 *
 * Driver interface for 4× MEMS microphones via I2S/SAI:
 *   - I2S2: Microphones 0,1 (stereo pair)
 *   - I2S3: Microphones 2,3 (stereo pair)
 *
 * Audio is captured at 48 kHz, 16-bit PCM, using DMA double-buffering
 * for zero-copy operation between ISR and processing context.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note MISRA-C:2012 compliant.
 */

#ifndef AUDIO_DRIVER_H
#define AUDIO_DRIVER_H

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
 * @brief Audio subsystem status
 */
typedef enum {
    AUDIO_STATUS_UNINIT   = 0,   /**< Not initialized */
    AUDIO_STATUS_STOPPED  = 1,   /**< Initialized but not capturing */
    AUDIO_STATUS_RUNNING  = 2,   /**< Actively capturing audio */
    AUDIO_STATUS_OVERRUN  = 3,   /**< Buffer overrun detected */
    AUDIO_STATUS_ERROR    = 4    /**< Hardware error */
} audio_status_t;

/**
 * @brief Audio buffer state (for double/triple buffering)
 */
typedef enum {
    AUDIO_BUF_FREE     = 0,      /**< Buffer available for DMA write */
    AUDIO_BUF_Filling  = 1,      /**< DMA is writing to this buffer */
    AUDIO_BUF_Ready    = 2,      /**< Buffer has complete data for processing */
    AUDIO_BUF_Processing = 3     /**< CPU is processing this buffer */
} audio_buf_state_t;

/**
 * @brief Single audio frame (one processing window)
 *
 * Contains interleaved samples from all microphones for a time window.
 * Layout: [Mic0_s0, Mic1_s0, Mic2_s0, Mic3_s0, Mic0_s1, ...]
 */
typedef struct {
    int16_t samples[VISTA_MIC_COUNT * VISTA_AUDIO_FRAME_SIZE]; /**< Interleaved PCM samples */
    uint32_t timestamp_us;       /**< Frame start timestamp */
    uint16_t sequence;           /**< Monotonic frame sequence */
    uint8_t status;              /**< 0 = OK, nonzero = overrun/error */
} audio_frame_t;

/**
 * @brief Audio processing callback
 *
 * Called when a complete audio frame is available for processing.
 * Must complete within VISTA_IMU_PERIOD_US to avoid data loss.
 *
 * @param[in] frame  Pointer to filled audio frame.
 */
typedef void (*audio_process_callback_t)(const audio_frame_t *frame);

/**
 * @brief Audio driver context (opaque internal state)
 */
typedef struct {
    audio_status_t status;              /**< Current status */
    audio_frame_t buffers[VISTA_AUDIO_BUFFER_COUNT];  /**< Frame buffers */
    volatile uint8_t dma_write_idx;     /**< Current DMA write buffer index */
    volatile uint8_t proc_read_idx;     /**< Current processing read index */
    uint8_t buffer_count;               /**< Number of active buffers */
    uint16_t sequence;                  /**< Frame sequence counter */
    uint32_t overrun_count;             /**< Cumulative overrun count */
    audio_process_callback_t callback;  /**< Processing callback */
    bool i2s2_enabled;                  /**< I2S2 (mics 0,1) active */
    bool i2s3_enabled;                  /**< I2S3 (mics 2,3) active */
} audio_context_t;

/* ========================================================================== */
/*  INITIALIZATION                                                            */
/* ========================================================================== */

/**
 * @brief Initialize the audio subsystem.
 *
 * Configures I2S peripherals for 48 kHz / 16-bit, sets up DMA channels,
 * and allocates frame buffers. Does not start capture.
 *
 * @param[in] ctx  Caller-allocated audio context.
 * @return VISTA_OK on success.
 */
vista_error_t audio_init(audio_context_t *ctx);

/**
 * @brief Register a processing callback for audio frames.
 *
 * @param[in] ctx       Audio context.
 * @param[in] callback  Callback function (NULL to unregister).
 * @return VISTA_OK on success.
 */
vista_error_t audio_register_callback(audio_context_t *ctx,
                                      audio_process_callback_t callback);

/* ========================================================================== */
/*  CAPTURE CONTROL                                                           */
/* ========================================================================== */

/**
 * @brief Start audio capture.
 *
 * Begins DMA transfers on both I2S interfaces. Calls callback when
 * frames are complete.
 *
 * @param[in] ctx  Audio context.
 * @return VISTA_OK on success.
 */
vista_error_t audio_start(audio_context_t *ctx);

/**
 * @brief Stop audio capture.
 *
 * @param[in] ctx  Audio context.
 * @return VISTA_OK on success.
 */
vista_error_t audio_stop(audio_context_t *ctx);

/* ========================================================================== */
/*  BUFFER MANAGEMENT                                                         */
/* ========================================================================== */

/**
 * @brief Get the next ready audio frame for processing.
 *
 * Returns a pointer to the next complete frame. The frame must be
 * released with audio_frame_release() when processing is done.
 *
 * @param[in]  ctx    Audio context.
 * @param[out] frame  Pointer to the ready frame (or NULL if none).
 * @return VISTA_OK if frame available, VISTA_ERR_TIMEOUT if none.
 */
vista_error_t audio_frame_get(audio_context_t *ctx, audio_frame_t **frame);

/**
 * @brief Release a processed audio frame.
 *
 * Returns the buffer to the free pool for DMA reuse.
 *
 * @param[in] ctx    Audio context.
 * @param[in] frame  Frame to release (must be from audio_frame_get).
 */
void audio_frame_release(audio_context_t *ctx, audio_frame_t *frame);

/* ========================================================================== */
/*  DMA / ISR HANDLERS                                                        */
/* ========================================================================== */

/**
 * @brief I2S2 DMA half-transfer interrupt handler.
 *
 * Called when first half of DMA buffer is complete (mics 0,1).
 * ISR-safe.
 *
 * @param[in] ctx  Audio context.
 */
void audio_i2s2_ht_isr(audio_context_t *ctx);

/**
 * @brief I2S2 DMA transfer-complete interrupt handler.
 *
 * Called when second half of DMA buffer is complete (mics 0,1).
 * ISR-safe.
 *
 * @param[in] ctx  Audio context.
 */
void audio_i2s2_tc_isr(audio_context_t *ctx);

/**
 * @brief I2S3 DMA half-transfer interrupt handler.
 *
 * @param[in] ctx  Audio context.
 */
void audio_i2s3_ht_isr(audio_context_t *ctx);

/**
 * @brief I2S3 DMA transfer-complete interrupt handler.
 *
 * @param[in] ctx  Audio context.
 */
void audio_i2s3_tc_isr(audio_context_t *ctx);

/* ========================================================================== */
/*  STATUS / DIAGNOSTICS                                                      */
/* ========================================================================== */

/**
 * @brief Get audio subsystem status.
 *
 * @param[in] ctx  Audio context.
 * @return Current status.
 */
audio_status_t audio_get_status(const audio_context_t *ctx);

/**
 * @brief Get overrun count since initialization.
 *
 * @param[in] ctx  Audio context.
 * @return Number of overrun events.
 */
uint32_t audio_get_overrun_count(const audio_context_t *ctx);

/**
 * @brief Reset overrun counter.
 *
 * @param[in] ctx  Audio context.
 */
void audio_reset_overrun_count(audio_context_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* AUDIO_DRIVER_H */
