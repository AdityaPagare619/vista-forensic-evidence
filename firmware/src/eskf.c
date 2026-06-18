/**
 * @file eskf.c
 * @brief Error-State Kalman Filter (ESKF) Implementation
 *
 * Quaternion-based ESKF for IMU sensor fusion on VISTA 2.0.
 *
 * State vector (7):
 *   q[0..3] = orientation quaternion (unit)
 *   b[0..2] = gyroscope bias (rad/s)
 *
 * Error state vector (6):
 *   δθ[0..2] = rotation error (small-angle approximation)
 *   δb[0..2] = gyroscope bias error
 *
 * Predict step: Integrate gyro, propagate covariance via linearized model.
 * Update step:  Accelerometer as primary (gravity reference), optional
 *               magnetometer for heading correction.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note Quaternion convention: Hamilton, scalar-first [w, x, y, z].
 * @note Reference: "Indirect Error-State Kalman Filter" (Sola, 2017).
 */

#include "firmware.h"
#include <math.h>
#include <string.h>

/* ========================================================================== */
/*  INTERNAL STATE                                                            */
/* ========================================================================== */

/**
 * @brief ESKF internal state (file-scope for encapsulation)
 */
typedef struct {
    /* Quaternion state [w, x, y, z] */
    float q[4];

    /* Gyro bias state */
    float b[3];

    /* Error-state covariance matrix P (6×6, symmetric, stored as 21 floats) */
    float P[21];

    /* Process noise covariance diagonal (6 elements) */
    float Q[6];

    /* Covariance reset flag (true after large correction) */
    bool cov_reset;
} eskf_state_t;

/** @brief ESKF instance (single filter — one per system) */
static eskf_state_t g_eskf;

/* ========================================================================== */
/*  MATH HELPERS                                                              */
/* ========================================================================== */

/**
 * @brief Normalize a quaternion to unit length.
 */
static void quat_normalize(float q[4])
{
    float mag = sqrtf(q[0] * q[0] + q[1] * q[1] +
                      q[2] * q[2] + q[3] * q[3]);
    if (mag > 1.0e-10f) {
        float inv_mag = 1.0f / mag;
        q[0] *= inv_mag;
        q[1] *= inv_mag;
        q[2] *= inv_mag;
        q[3] *= inv_mag;
    } else {
        /* Degenerate quaternion — reset to identity */
        q[0] = 1.0f;
        q[1] = 0.0f;
        q[2] = 0.0f;
        q[3] = 0.0f;
    }
}

/**
 * @brief Quaternion multiplication: q_out = q_a ⊗ q_b
 */
static void quat_mul(const float a[4], const float b[4], float out[4])
{
    out[0] = a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3];
    out[1] = a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2];
    out[2] = a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1];
    out[3] = a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0];
}

/**
 * @brief Compute skew-symmetric matrix from 3-vector.
 *
 * Output is 3×3 matrix stored as 9 floats (row-major).
 */
static void skew_symmetric(const float v[3], float S[9])
{
    S[0] =  0.0f;  S[1] = -v[2]; S[2] =  v[1];
    S[3] =  v[2];  S[4] =  0.0f; S[5] = -v[0];
    S[6] = -v[1];  S[7] =  v[0]; S[8] =  0.0f;
}

/**
 * @brief Compute the Jacobian of the rotation error (small-angle).
 *
 * This is the F matrix mapping error state to state derivative.
 * For quaternion state, the relationship is:
 *   q̇ = 0.5 * q ⊗ [0, ω]
 *   δq̇ = -[ω]× δθ / 2
 */
static void compute_F(const float gyro[3], float dt, float F[36])
{
    /* F is 6×6: [0, -I/2; 0, 0] for the rotation part,
     * with bias coupling as [-I, 0] for gyro bias.
     *
     * Simplified: F = I + F_dt, where:
     * F_dt[0..2, 0..2] = -skew(gyro) * dt / 2
     * F_dt[0..2, 3..5] = -I * dt
     * F_dt[3..5, 0..2] = 0
     * F_dt[3..5, 3..5] = 0
     */
    (void)memset(F, 0, sizeof(float) * 36U);

    float half_dt = 0.5f * dt;

    /* Diagonal = 1 */
    F[0]  = 1.0f;
    F[7]  = 1.0f;
    F[14] = 1.0f;
    F[21] = 1.0f;
    F[28] = 1.0f;
    F[35] = 1.0f;

    /* -skew(gyro) * dt / 2 for rotation error */
    F[1]  =  gyro[2] * half_dt;
    F[2]  = -gyro[1] * half_dt;
    F[5]  = -gyro[2] * half_dt;
    F[6]  =  gyro[0] * half_dt;
    F[9]  =  gyro[1] * half_dt;
    F[10] = -gyro[0] * half_dt;

    /* -I * dt for bias coupling */
    F[3]  = -dt;
    F[11] = -dt;
    F[19] = -dt;
}

/**
 * @brief Set or update the process noise covariance diagonal.
 */
static void eskf_set_process_noise(eskf_state_t *s)
{
    /* Accelerometer-driven uncertainty */
    s->Q[0] = ESKF_GYRO_NOISE_VAR;           /* δθ_x */
    s->Q[1] = ESKF_GYRO_NOISE_VAR;           /* δθ_y */
    s->Q[2] = ESKF_GYRO_NOISE_VAR;           /* δθ_z */
    s->Q[3] = ESKF_GYRO_BIAS_WALK_VAR;       /* δb_x */
    s->Q[4] = ESKF_GYRO_BIAS_WALK_VAR;       /* δb_y */
    s->Q[5] = ESKF_GYRO_BIAS_WALK_VAR;       /* δb_z */
}

/* ========================================================================== */
/*  INITIALIZATION                                                            */
/* ========================================================================== */

vista_error_t eskf_init(firmware_context_t *ctx)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    (void)memset(&g_eskf, 0, sizeof(eskf_state_t));

    /* Initialize quaternion to identity (no rotation) */
    g_eskf.q[0] = 1.0f;
    g_eskf.q[1] = 0.0f;
    g_eskf.q[2] = 0.0f;
    g_eskf.q[3] = 0.0f;

    /* Initialize bias to zero */
    g_eskf.b[0] = 0.0f;
    g_eskf.b[1] = 0.0f;
    g_eskf.b[2] = 0.0f;

    /* Initialize covariance to reasonable values */
    /* P is 6×6 symmetric, stored as upper triangle (21 elements):
     * [0,0] [0,1] [0,2] [0,3] [0,4] [0,5]
     *       [1,1] [1,2] [1,3] [1,4] [1,5]
     *             [2,2] [2,3] [2,4] [2,5]
     *                   [3,3] [3,4] [3,5]
     *                         [4,4] [4,5]
     *                               [5,5]
     */
    g_eskf.P[0]  = 0.01f;  /* δθ_x variance */
    g_eskf.P[6]  = 0.01f;  /* δθ_y variance */
    g_eskf.P[11] = 0.01f;  /* δθ_z variance */
    g_eskf.P[15] = 0.001f; /* δb_x variance */
    g_eskf.P[18] = 0.001f; /* δb_y variance */
    g_eskf.P[20] = 0.001f; /* δb_z variance */

    /* Set process noise */
    eskf_set_process_noise(&g_eskf);

    g_eskf.cov_reset = false;

    return VISTA_OK;
}

/* ========================================================================== */
/*  PREDICTION STEP                                                           */
/* ========================================================================== */

void eskf_predict(firmware_context_t *ctx, const imu_vec3_f32_t *gyro,
                  float dt)
{
    if ((ctx == NULL) || (gyro == NULL) || (dt <= 0.0f)) {
        return;
    }

    /* Compensate gyro for estimated bias */
    float omega[3];
    omega[0] = gyro->x - g_eskf.b[0];
    omega[1] = gyro->y - g_eskf.b[1];
    omega[2] = gyro->z - g_eskf.b[2];

    /* Compute rotation increment magnitude */
    float omega_mag = sqrtf(omega[0] * omega[0] + omega[1] * omega[1] +
                            omega[2] * omega[2]);

    /* Quaternion propagation using exact rotation formula */
    float dq[4];
    if (omega_mag > 1.0e-8f) {
        float half_angle = 0.5f * omega_mag * dt;
        float sin_ha = sinf(half_angle);
        float cos_ha = cosf(half_angle);
        float scale = sin_ha / omega_mag;

        dq[0] = cos_ha;
        dq[1] = omega[0] * scale;
        dq[2] = omega[1] * scale;
        dq[3] = omega[2] * scale;
    } else {
        /* Small angle approximation */
        float half_angle = 0.5f * omega_mag * dt;
        dq[0] = 1.0f - half_angle * half_angle;
        dq[1] = 0.5f * omega[0] * dt;
        dq[2] = 0.5f * omega[1] * dt;
        dq[3] = 0.5f * omega[2] * dt;
    }

    /* Propagate quaternion: q_new = q_old ⊗ dq */
    float q_new[4];
    quat_mul(g_eskf.q, dq, q_new);
    quat_normalize(q_new);
    g_eskf.q[0] = q_new[0];
    g_eskf.q[1] = q_new[1];
    g_eskf.q[2] = q_new[2];
    g_eskf.q[3] = q_new[3];

    /* Propagate covariance: P_new = F * P * F^T + Q_dt */
    float F[36];
    compute_F(omega, dt, F);

    /* Simplified covariance propagation (diagonal dominance approximation):
     * P[i][i] += Q[i] * dt for each error state dimension
     * Off-diagonal terms updated via linearized model
     */
    if (!g_eskf.cov_reset) {
        /* Full matrix update would go here. For resource-constrained MCU,
         * we use a simplified diagonal propagation with coupling terms. */
        for (uint8_t i = 0U; i < 6U; i++) {
            /* Add process noise (scaled by dt) */
            uint8_t idx = (i * (i + 1U)) / 2U + i;
            if (idx < 21U) {
                g_eskf.P[idx] += g_eskf.Q[i] * dt;
            }
        }

        /* Propagate off-diagonal terms (simplified) */
        /* F * P * F^T for rotation-bias coupling */
        for (uint8_t i = 0U; i < 3U; i++) {
            for (uint8_t j = 0U; j < 3U; j++) {
                uint8_t pi = (i < j) ? (i * 6U + j - (i * (i + 1U)) / 2U) :
                             (j * 6U + i - (j * (j + 1U)) / 2U);
                if (pi < 21U) {
                    g_eskf.P[pi] *= 0.99f;  /* Decay towards zero */
                }
            }
        }
    } else {
        /* Reset covariance after large correction */
        g_eskf.P[0]  = 0.01f;
        g_eskf.P[6]  = 0.01f;
        g_eskf.P[11] = 0.01f;
        g_eskf.P[15] = 0.001f;
        g_eskf.P[18] = 0.001f;
        g_eskf.P[20] = 0.001f;
        g_eskf.cov_reset = false;
    }

    /* Store fusion output in context */
    ctx->fusion.orientation.q0 = g_eskf.q[0];
    ctx->fusion.orientation.q1 = g_eskf.q[1];
    ctx->fusion.orientation.q2 = g_eskf.q[2];
    ctx->fusion.orientation.q3 = g_eskf.q[3];
    ctx->fusion.angular_vel.x = omega[0];
    ctx->fusion.angular_vel.y = omega[1];
    ctx->fusion.angular_vel.z = omega[2];
    ctx->fusion.gyro_bias.x = g_eskf.b[0];
    ctx->fusion.gyro_bias.y = g_eskf.b[1];
    ctx->fusion.gyro_bias.z = g_eskf.b[2];
    ctx->fusion.timestamp_us = vista_get_dwt_cycles();
}

/* ========================================================================== */
/*  UPDATE STEP — ACCELEROMETER                                                */
/* ========================================================================== */

void eskf_update_accel(firmware_context_t *ctx, const imu_vec3_f32_t *accel)
{
    if ((ctx == NULL) || (accel == NULL)) {
        return;
    }

    /* Normalize accelerometer measurement */
    float a_mag = sqrtf(accel->x * accel->x + accel->y * accel->y +
                        accel->z * accel->z);

    if (a_mag < 0.5f || a_mag > 2.0f * ESKF_GRAVITY) {
        /* Accelerometer not reliable (free-fall or excessive acceleration) */
        return;
    }

    /* Expected gravity in body frame from current quaternion */
    float gx = 2.0f * (g_eskf.q[1] * g_eskf.q[3] -
                        g_eskf.q[0] * g_eskf.q[2]);
    float gy = 2.0f * (g_eskf.q[0] * g_eskf.q[1] +
                        g_eskf.q[2] * g_eskf.q[3]);
    float gz = g_eskf.q[0] * g_eskf.q[0] - g_eskf.q[1] * g_eskf.q[1] -
               g_eskf.q[2] * g_eskf.q[2] + g_eskf.q[3] * g_eskf.q[3];

    /* Normalize expected gravity */
    float g_norm = sqrtf(gx * gx + gy * gy + gz * gz);
    if (g_norm > 1.0e-8f) {
        gx /= g_norm;
        gy /= g_norm;
        gz /= g_norm;
    }

    /* Normalize measured acceleration */
    float ax = accel->x / a_mag;
    float ay = accel->y / a_mag;
    float az = accel->z / a_mag;

    /* Innovation (measurement error) */
    float innov[3];
    innov[0] = ax - gx;
    innov[1] = ay - gy;
    innov[2] = az - gz;

    /* Check for excessive innovation (outlier rejection) */
    float innov_mag = sqrtf(innov[0] * innov[0] + innov[1] * innov[1] +
                            innov[2] * innov[2]);
    if (innov_mag > 0.5f) {
        /* Outlier — skip update */
        return;
    }

    /* Measurement Jacobian H (3×6): d(accel)/d(error_state)
     * H = [R^T * [a]×, 0]  where [a]× is skew of expected gravity */
    float H[18];  /* 3×6 matrix */
    (void)memset(H, 0, sizeof(H));

    /* H[0..2, 0..2] = cross-product matrix of gravity direction */
    float accel_cross[9];
    float grav[3] = { gx, gy, gz };
    skew_symmetric(grav, accel_cross);

    /* Transpose of cross product (for error-state Jacobian) */
    H[0] = accel_cross[0]; H[1] = accel_cross[3]; H[2] = accel_cross[6];
    H[3] = accel_cross[1]; H[4] = accel_cross[4]; H[5] = accel_cross[7];
    H[6] = accel_cross[2]; H[7] = accel_cross[5]; H[8] = accel_cross[8];

    /* Measurement noise */
    float R = ESKF_ACCEL_NOISE_VAR;

    /* Innovation covariance: S = H * P * H^T + R */
    float S = 0.0f;
    for (uint8_t i = 0U; i < 3U; i++) {
        for (uint8_t j = 0U; j < 6U; j++) {
            float h_j = H[i * 6U + j];
            uint8_t pj = (j < 3U) ?
                         (j * 6U + j - (j * (j + 1U)) / 2U + j) :
                         (j * 6U + j - (j * (j + 1U)) / 2U + j);
            if (pj < 21U) {
                S += h_j * g_eskf.P[pj] * h_j;
            }
        }
    }
    S += R;

    /* Kalman gain: K = P * H^T / S */
    float K[6];  /* 6×3 gain (stored flattened) */
    for (uint8_t i = 0U; i < 6U; i++) {
        float sum = 0.0f;
        for (uint8_t j = 0U; j < 3U; j++) {
            uint8_t pi = (i < j) ?
                         (i * 6U + j - (i * (i + 1U)) / 2U + i) :
                         (j * 6U + i - (j * (j + 1U)) / 2U + j);
            if (pi < 21U) {
                sum += g_eskf.P[pi] * H[j * 6U + i];
            }
        }
        K[i] = sum / S;
    }

    /* Error state correction: δx = K * innov */
    float dx[6];
    for (uint8_t i = 0U; i < 6U; i++) {
        dx[i] = K[i * 3U] * innov[0] +
                K[i * 3U + 1U] * innov[1] +
                K[i * 3U + 2U] * innov[2];
    }

    /* Apply rotation correction to quaternion (first-order) */
    g_eskf.q[0] -= 0.5f * (g_eskf.q[1] * dx[0] + g_eskf.q[2] * dx[1] +
                             g_eskf.q[3] * dx[2]);
    g_eskf.q[1] += 0.5f * (g_eskf.q[0] * dx[0] + g_eskf.q[2] * dx[2] -
                             g_eskf.q[3] * dx[1]);
    g_eskf.q[2] += 0.5f * (g_eskf.q[0] * dx[1] + g_eskf.q[3] * dx[0] -
                             g_eskf.q[1] * dx[2]);
    g_eskf.q[3] += 0.5f * (g_eskf.q[0] * dx[2] + g_eskf.q[1] * dx[1] -
                             g_eskf.q[2] * dx[0]);
    quat_normalize(g_eskf.q);

    /* Apply bias correction */
    g_eskf.b[0] += dx[3];
    g_eskf.b[1] += dx[4];
    g_eskf.b[2] += dx[5];

    /* Update covariance: P_new = (I - K*H) * P */
    for (uint8_t i = 0U; i < 6U; i++) {
        for (uint8_t j = 0U; j < 6U; j++) {
            float kht = K[i] * H[j];  /* Simplified single-element K*H */
            uint8_t idx = (i <= j) ?
                         (i * 6U + j - (i * (i + 1U)) / 2U + i) :
                         (j * 6U + i - (j * (j + 1U)) / 2U + j);
            if (idx < 21U) {
                g_eskf.P[idx] -= kht * g_eskf.P[idx];
            }
        }
    }

    /* Confidence estimate based on innovation magnitude */
    ctx->fusion.confidence = 1.0f - (innov_mag / 0.5f);
    if (ctx->fusion.confidence < 0.0f) {
        ctx->fusion.confidence = 0.0f;
    }
    if (ctx->fusion.confidence > 1.0f) {
        ctx->fusion.confidence = 1.0f;
    }
}

/* ========================================================================== */
/*  OUTPUT                                                                    */
/* ========================================================================== */

void eskf_get_output(const firmware_context_t *ctx, fusion_output_t *output)
{
    if ((ctx == NULL) || (output == NULL)) {
        return;
    }

    *output = ctx->fusion;
}
