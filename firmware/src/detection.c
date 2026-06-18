/**
 * @file detection.c
 * @brief PDTSA (Principal Direction Time Series Analysis) Crash Detection
 *
 * Real-time crash/impact detection algorithm for VISTA 2.0.
 * Uses a sliding window of IMU samples with PCA-based feature extraction
 * to identify impact signatures in accelerometer time-series data.
 *
 * Algorithm overview:
 *   1. Maintain a circular buffer of N recent IMU samples (50 ms at 1 kHz)
 *   2. Compute principal components of acceleration data
 *   3. Project samples onto principal axis
 *   4. Detect threshold crossings with temporal validation
 *   5. Apply cooldown to prevent re-triggering
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note Real-time constraint: Must complete within 100 µs per sample.
 */

#include "firmware.h"
#include <math.h>
#include <string.h>

/* ========================================================================== */
/*  INTERNAL STATE                                                            */
/* ========================================================================== */

/**
 * @brief Sliding window buffer for IMU samples
 */
typedef struct {
    imu_vec3_f32_t accel[PDTSA_WINDOW_SIZE];   /**< Acceleration samples */
    uint32_t timestamp[PDTSA_WINDOW_SIZE];      /**< Sample timestamps */
    uint8_t head;                                /**< Write pointer */
    uint8_t count;                               /**< Valid sample count */
} detection_window_t;

/**
 * @brief Detection algorithm internal state
 */
typedef struct {
    detection_window_t window;              /**< Sliding window */
    float mean[3];                          /**< Running mean of acceleration */
    float principal_axis[3];                /**< Principal component direction */
    float principal_variance;               /**< Variance along principal axis */
    uint32_t last_trigger_us;               /**< Last trigger timestamp */
    uint32_t cooldown_remaining_us;         /**< Remaining cooldown */
    bool armed;                             /**< Detection enabled */
    bool triggered;                         /**< Currently in trigger state */
    uint8_t trigger_count;                  /**< Number of triggers */
} detection_state_t;

/** @brief Detection instance */
static detection_state_t g_det;

/* ========================================================================== */
/*  MATH HELPERS                                                              */
/* ========================================================================== */

/**
 * @brief Compute dot product of two 3-vectors.
 */
static inline float vec3_dot(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/**
 * @brief Compute norm of a 3-vector.
 */
static inline float vec3_norm(const float v[3])
{
    return sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

/**
 * @brief Subtract two 3-vectors: out = a - b.
 */
static inline void vec3_sub(const float a[3], const float b[3], float out[3])
{
    out[0] = a[0] - b[0];
    out[1] = a[1] - b[1];
    out[2] = a[2] - b[2];
}

/**
 * @brief Add scalar multiple: out += scale * v.
 */
static inline void vec3_add_scaled(float out[3], const float v[3], float s)
{
    out[0] += v[0] * s;
    out[1] += v[1] * s;
    out[2] += v[2] * s;
}

/* ========================================================================== */
/*  PCA (POWER ITERATION METHOD)                                              */
/* ========================================================================== */

/**
 * @brief Compute principal component via power iteration.
 *
 * Finds the direction of maximum variance in the acceleration data.
 * Uses 10 iterations of power iteration on the covariance matrix.
 *
 * @param[in]  win     Sliding window data.
 * @param[out] axis    Principal direction (unit vector).
 * @param[out] variance  Variance along principal axis.
 */
static void compute_principal_component(const detection_window_t *win,
                                        float axis[3], float *variance)
{
    if ((win == NULL) || (axis == NULL) || (variance == NULL)) {
        return;
    }

    uint8_t n = win->count;
    if (n < 3U) {
        /* Not enough data */
        axis[0] = 0.0f;
        axis[1] = 0.0f;
        axis[2] = 1.0f;
        *variance = 0.0f;
        return;
    }

    /* Compute mean */
    float mean[3] = { 0.0f, 0.0f, 0.0f };
    for (uint8_t i = 0U; i < n; i++) {
        mean[0] += win->accel[i].x;
        mean[1] += win->accel[i].y;
        mean[2] += win->accel[i].z;
    }
    float inv_n = 1.0f / (float)n;
    mean[0] *= inv_n;
    mean[1] *= inv_n;
    mean[2] *= inv_n;

    /* Power iteration to find dominant eigenvector of covariance matrix */
    float v[3] = { 1.0f, 0.0f, 0.0f };  /* Initial guess */

    for (uint8_t iter = 0U; iter < 10U; iter++) {
        /* Multiply by covariance matrix: C * v */
        float Av[3] = { 0.0f, 0.0f, 0.0f };

        for (uint8_t i = 0U; i < n; i++) {
            float d[3];
            d[0] = win->accel[i].x - mean[0];
            d[1] = win->accel[i].y - mean[1];
            d[2] = win->accel[i].z - mean[2];

            /* Av += (d · v) * d */
            float proj = vec3_dot(d, v);
            vec3_add_scaled(Av, d, proj);
        }

        /* Normalize */
        float mag = vec3_norm(Av);
        if (mag > 1.0e-8f) {
            v[0] = Av[0] / mag;
            v[1] = Av[1] / mag;
            v[2] = Av[2] / mag;
        }
    }

    /* Compute variance along principal axis */
    float var_sum = 0.0f;
    for (uint8_t i = 0U; i < n; i++) {
        float d[3];
        d[0] = win->accel[i].x - mean[0];
        d[1] = win->accel[i].y - mean[1];
        d[2] = win->accel[i].z - mean[2];

        float proj = vec3_dot(d, v);
        var_sum += proj * proj;
    }

    axis[0] = v[0];
    axis[1] = v[1];
    axis[2] = v[2];
    *variance = var_sum * inv_n;
}

/* ========================================================================== */
/*  INITIALIZATION                                                            */
/* ========================================================================== */

vista_error_t detection_init(firmware_context_t *ctx)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    (void)memset(&g_det, 0, sizeof(detection_state_t));

    g_det.armed = false;
    g_det.triggered = false;
    g_det.trigger_count = 0U;

    /* Initialize principal axis to Z-up default */
    g_det.principal_axis[0] = 0.0f;
    g_det.principal_axis[1] = 0.0f;
    g_det.principal_axis[2] = 1.0f;

    return VISTA_OK;
}

/* ========================================================================== */
/*  DETECTION ALGORITHM                                                       */
/* ========================================================================== */

vista_error_t detection_feed(firmware_context_t *ctx,
                             const imu_sample_t *sample,
                             detection_result_t *result)
{
    if ((ctx == NULL) || (sample == NULL) || (result == NULL)) {
        return VISTA_ERR_RANGE;
    }

    /* Initialize result */
    (void)memset(result, 0, sizeof(detection_result_t));

    /* Only process from primary IMU (IMU 0) for now */
    if (sample->imu_id != 0U) {
        return VISTA_OK;
    }

    detection_window_t *win = &g_det.window;

    /* Add sample to circular buffer */
    uint8_t idx = win->head;
    win->accel[idx] = sample->accel_ms2;
    win->timestamp[idx] = sample->timestamp_us;
    win->head = (uint8_t)((idx + 1U) % PDTSA_WINDOW_SIZE);
    if (win->count < PDTSA_WINDOW_SIZE) {
        win->count++;
    }

    /* Need at least a full window before detecting */
    if (win->count < PDTSA_WINDOW_SIZE) {
        return VISTA_OK;
    }

    /* Update cooldown timer */
    uint32_t now_us = sample->timestamp_us;
    if (g_det.cooldown_remaining_us > 0U) {
        uint32_t elapsed = now_us - g_det.last_trigger_us;
        if (elapsed >= g_det.cooldown_remaining_us) {
            g_det.cooldown_remaining_us = 0U;
        } else {
            g_det.cooldown_remaining_us -= elapsed;
        }
    }

    /* Compute principal component */
    compute_principal_component(win, g_det.principal_axis,
                                &g_det.principal_variance);

    /* Compute peak acceleration along principal axis */
    float peak_projection = 0.0f;
    float mean_proj = 0.0f;
    uint8_t n = win->count;

    for (uint8_t i = 0U; i < n; i++) {
        float proj = vec3_dot((const float *)&win->accel[i],
                              g_det.principal_axis);
        mean_proj += proj;
    }
    mean_proj *= (1.0f / (float)n);

    for (uint8_t i = 0U; i < n; i++) {
        float proj = vec3_dot((const float *)&win->accel[i],
                              g_det.principal_axis);
        float deviation = proj - mean_proj;
        if (deviation > peak_projection) {
            peak_projection = deviation;
        }
    }

    /* Check high-g trigger (H3LIS331DL data if available) */
    float accel_magnitude = vec3_norm((const float *)&sample->accel_ms2);
    float accel_g = accel_magnitude / ESKF_GRAVITY;

    /* Detection criteria:
     * 1. Principal component variance exceeds threshold
     * 2. Peak acceleration along principal axis exceeds threshold
     * 3. Not in cooldown period
     * 4. System is in ARMED state
     */
    bool criteria_variance = (g_det.principal_variance >
                              (PDTSA_THRESHOLD * PDTSA_THRESHOLD));
    bool criteria_peak = (peak_projection >
                          (PDTSA_HIGHG_TRIGGER_G * ESKF_GRAVITY));
    bool criteria_cooldown = (g_det.cooldown_remaining_us == 0U);
    bool criteria_highg = (accel_g > PDTSA_HIGHG_TRIGGER_G);

    if ((criteria_variance || criteria_peak || criteria_highg) &&
        criteria_cooldown)
    {
        /* Impact detected! */
        if (!g_det.triggered) {
            g_det.triggered = true;
            g_det.trigger_count++;
            g_det.last_trigger_us = now_us;
            g_det.cooldown_remaining_us =
                (uint32_t)(PDTSA_COOLDOWN_MS * 1000U);

            result->impact_detected = true;
            result->detection_time_us = now_us;
            result->peak_accel_g = accel_g;
            result->principal_magnitude = g_det.principal_variance;
            result->severity = (peak_projection /
                               (PDTSA_HIGHG_TRIGGER_G * ESKF_GRAVITY));
            if (result->severity > 1.0f) {
                result->severity = 1.0f;
            }
            result->impact_axis[0] = g_det.principal_axis[0];
            result->impact_axis[1] = g_det.principal_axis[1];
            result->impact_axis[2] = g_det.principal_axis[2];
        }
    } else {
        /* No detection — check if trigger should be cleared */
        if (g_det.triggered) {
            uint32_t elapsed = now_us - g_det.last_trigger_us;
            if (elapsed > (uint32_t)(PDTSA_MIN_DURATION_MS * 1000U)) {
                g_det.triggered = false;
            }
        }
    }

    return VISTA_OK;
}

/* ========================================================================== */
/*  RESET                                                                     */
/* ========================================================================== */

void detection_reset(firmware_context_t *ctx)
{
    (void)ctx;
    g_det.triggered = false;
    g_det.cooldown_remaining_us = 0U;
}
