/**
 * @file crash_state_machine.c
 * @brief Crash State Machine Implementation
 *
 * Manages the VISTA 2.0 crash recording lifecycle:
 *   INIT -> SELF_TEST -> IDLE -> ARMED -> RECORDING -> POST_CRASH
 *
 * The state machine coordinates sensor recording during crash events,
 * manages supercapacitor power, and ensures evidence is saved before
 * power loss.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 */

#include "firmware.h"
#include <string.h>

/* ========================================================================== */
/*  STATE TRANSITION TABLE                                                    */
/* ========================================================================== */

/**
 * @brief State transition entry
 */
typedef struct {
    sys_state_t current;            /**< Current state */
    sys_state_event_t event;        /**< Triggering event */
    sys_state_t next;               /**< Next state */
    bool valid;                     /**< Transition is valid */
} state_transition_t;

/**
 * @brief State transition table — defines valid transitions.
 *
 * Indexed by (current_state * EVENT_COUNT + event). Unused entries
 * are marked as invalid (no transition).
 */
static const state_transition_t TRANSITIONS[] = {
    /* From INIT */
    { SYS_STATE_INIT,  STATE_EVT_INIT_COMPLETE,  SYS_STATE_SELF_TEST, true },
    { SYS_STATE_INIT,  STATE_EVT_FAULT,          SYS_STATE_FAULT,     true },

    /* From SELF_TEST */
    { SYS_STATE_SELF_TEST, STATE_EVT_SELFTEST_PASS, SYS_STATE_IDLE,   true },
    { SYS_STATE_SELF_TEST, STATE_EVT_SELFTEST_FAIL, SYS_STATE_FAULT,  true },

    /* From IDLE */
    { SYS_STATE_IDLE,  STATE_EVT_ARM_CMD,        SYS_STATE_ARMED,     true },
    { SYS_STATE_IDLE,  STATE_EVT_FAULT,          SYS_STATE_FAULT,     true },

    /* From ARMED */
    { SYS_STATE_ARMED, STATE_EVT_DISARM_CMD,     SYS_STATE_IDLE,      true },
    { SYS_STATE_ARMED, STATE_EVT_IMPACT_DET,     SYS_STATE_RECORDING, true },
    { SYS_STATE_ARMED, STATE_EVT_FAULT,          SYS_STATE_FAULT,     true },

    /* From RECORDING */
    { SYS_STATE_RECORDING, STATE_EVT_POSTCRASH_ENTRY, SYS_STATE_POST_CRASH, true },
    { SYS_STATE_RECORDING, STATE_EVT_RECORD_COMPLETE,  SYS_STATE_IDLE,      true },
    { SYS_STATE_RECORDING, STATE_EVT_FAULT,            SYS_STATE_FAULT,     true },

    /* From POST_CRASH */
    { SYS_STATE_POST_CRASH, STATE_EVT_RECORD_COMPLETE, SYS_STATE_IDLE,  true },
    { SYS_STATE_POST_CRASH, STATE_EVT_FAULT,           SYS_STATE_FAULT, true },

    /* From FAULT */
    { SYS_STATE_FAULT, STATE_EVT_RECOVERY,       SYS_STATE_INIT,      true },
};

/** @brief Number of transition table entries */
#define TRANSITION_COUNT  (sizeof(TRANSITIONS) / sizeof(TRANSITIONS[0]))

/* ========================================================================== */
/*  STATE ACTIONS                                                             */
/* ========================================================================== */

/**
 * @brief Enter INIT state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_init(firmware_context_t *ctx)
{
    /* Reset sub-state machines */
    ctx->fusion_initialized = false;
    ctx->loop_count = 0U;
}

/**
 * @brief Enter SELF_TEST state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_self_test(firmware_context_t *ctx)
{
    /* Self-test will be run by main loop */
    (void)ctx;
}

/**
 * @brief Enter IDLE state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_idle(firmware_context_t *ctx)
{
    /* Stop all recording */
    audio_stop(&ctx->audio);
    camera_stop(&ctx->camera);

    /* Reset crash state */
    ctx->crash.impact_detected = false;
    ctx->crash.power_failing = false;
    ctx->crash.frames_captured = 0U;
    ctx->crash.evidence_saved = false;
}

/**
 * @brief Enter ARMED state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_armed(firmware_context_t *ctx)
{
    /* Reset detection state */
    detection_reset(ctx);

    /* Start continuous IMU capture */
    for (uint8_t i = 0U; i < VISTA_IMU_COUNT; i++) {
        imu_read_dma_start(i, &ctx->imu[i]);
    }

    /* Start audio capture */
    audio_start(&ctx->audio);

    /* Start camera capture */
    camera_start(&ctx->camera);
}

/**
 * @brief Enter RECORDING state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_recording(firmware_context_t *ctx)
{
    /* Increase recording priority */
    ctx->crash.impact_detected = true;
    ctx->crash.impact_timestamp_us = vista_get_dwt_cycles();

    /* Log event as evidence */
    evidence_add(ctx, EVIDENCE_TYPE_IMPACT_DET,
                 (const uint8_t *)&ctx->detection,
                 sizeof(detection_result_t));
}

/**
 * @brief Enter POST_CRASH state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_post_crash(firmware_context_t *ctx)
{
    ctx->crash.postcrash_start_us = vista_get_dwt_cycles();
    ctx->crash.frames_captured = 0U;

    /* Log post-crash entry as evidence */
    evidence_add(ctx, EVIDENCE_TYPE_STATE_TRANS,
                 (const uint8_t *)&ctx->state,
                 sizeof(sys_state_t));
}

/**
 * @brief Enter FAULT state.
 *
 * @param[in] ctx  Firmware context.
 */
static void state_enter_fault(firmware_context_t *ctx)
{
    /* Attempt to save evidence chain */
    if (!ctx->crash.evidence_saved) {
        evidence_verify_chain(ctx);
        ctx->crash.evidence_saved = true;
    }

    /* Log fault event */
    evidence_add(ctx, EVIDENCE_TYPE_FAULT_LOG,
                 (const uint8_t *)&ctx->state,
                 sizeof(sys_state_t));
}

/** @brief State enter function table */
typedef void (*state_enter_fn)(firmware_context_t *ctx);

static const state_enter_fn ENTER_FUNCTIONS[] = {
    state_enter_init,           /* INIT */
    state_enter_self_test,      /* SELF_TEST */
    state_enter_idle,           /* IDLE */
    state_enter_armed,          /* ARMED */
    state_enter_recording,      /* RECORDING */
    state_enter_post_crash,     /* POST_CRASH */
    state_enter_fault           /* FAULT */
};

/* ========================================================================== */
/*  STATE NAME TABLE                                                          */
/* ========================================================================== */

static const char *STATE_NAMES[] = {
    "INIT",
    "SELF_TEST",
    "IDLE",
    "ARMED",
    "RECORDING",
    "POST_CRASH",
    "FAULT"
};

static const char *EVENT_NAMES[] = {
    "INIT_COMPLETE",
    "SELFTEST_PASS",
    "SELFTEST_FAIL",
    "ARM_CMD",
    "DISARM_CMD",
    "IMPACT_DET",
    "POSTCRASH_ENTRY",
    "RECORD_COMPLETE",
    "FAULT",
    "RECOVERY"
};

/* ========================================================================== */
/*  TRANSITION LOOKUP                                                         */
/* ========================================================================== */

/**
 * @brief Find a valid transition for given state and event.
 *
 * @param[in] current  Current state.
 * @param[in] event    Triggering event.
 * @return Pointer to matching transition, or NULL if invalid.
 */
static const state_transition_t *find_transition(sys_state_t current,
                                                  sys_state_event_t event)
{
    for (uint32_t i = 0U; i < TRANSITION_COUNT; i++) {
        if (TRANSITIONS[i].current == current &&
            TRANSITIONS[i].event == event &&
            TRANSITIONS[i].valid)
        {
            return &TRANSITIONS[i];
        }
    }
    return NULL;
}

/* ========================================================================== */
/*  STATE MACHINE EXECUTION                                                   */
/* ========================================================================== */

vista_error_t vista_state_machine_tick(firmware_context_t *ctx,
                                      sys_state_event_t event)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    /* If no event, check for automatic transitions */
    if (event >= STATE_EVT_COUNT) {
        /* Check for timeout-based transitions */
        uint32_t elapsed_us = vista_get_dwt_cycles() - ctx->state_entry_time_us;
        uint32_t elapsed_ms = vista_cycles_to_us(elapsed_us) / 1000U;

        switch (ctx->state) {
        case SYS_STATE_POST_CRASH:
            if (elapsed_ms > STATE_POSTCRASH_DURATION_MS) {
                event = STATE_EVT_RECORD_COMPLETE;
            }
            break;

        case SYS_STATE_RECORDING:
            /* Stay in RECORDING until explicit transition */
            break;

        default:
            break;
        }

        /* If still no event, return */
        if (event >= STATE_EVT_COUNT) {
            return VISTA_OK;
        }
    }

    /* Look up transition */
    const state_transition_t *trans = find_transition(ctx->state, event);
    if (trans == NULL) {
        /* Invalid transition — log and ignore */
        return VISTA_ERR_STATE;
    }

    /* Execute transition */
    sys_state_t old_state = ctx->state;
    ctx->state = trans->next;
    ctx->prev_state = old_state;

    /* Log the transition */
    vista_state_log(ctx, old_state, ctx->state, event);

    /* Execute enter action */
    if ((uint32_t)ctx->state < (uint32_t)SYS_STATE_COUNT) {
        ENTER_FUNCTIONS[ctx->state](ctx);
    }

    ctx->state_entry_time_us = vista_get_dwt_cycles();

    return VISTA_OK;
}

/* ========================================================================== */
/*  PUBLIC HELPERS                                                            */
/* ========================================================================== */

const char *vista_state_name(sys_state_t state)
{
    if ((uint32_t)state < (uint32_t)SYS_STATE_COUNT) {
        return STATE_NAMES[state];
    }
    return "UNKNOWN";
}

const char *vista_event_name(sys_state_event_t event)
{
    if ((uint32_t)event < (uint32_t)STATE_EVT_COUNT) {
        return EVENT_NAMES[event];
    }
    return "UNKNOWN";
}

void vista_state_log(firmware_context_t *ctx, sys_state_t from,
                     sys_state_t to, sys_state_event_t event)
{
    if (ctx == NULL) {
        return;
    }

    uint8_t idx = ctx->state_log_head;
    ctx->state_log[idx].from_state = from;
    ctx->state_log[idx].to_state = to;
    ctx->state_log[idx].event = event;
    ctx->state_log[idx].timestamp_us = vista_get_dwt_cycles();

    ctx->state_log_head = (uint8_t)((idx + 1U) % STATE_EVENT_LOG_SIZE);
    if (ctx->state_log_count < STATE_EVENT_LOG_SIZE) {
        ctx->state_log_count++;
    }
}

sys_state_t vista_get_current_state(const firmware_context_t *ctx)
{
    if (ctx == NULL) {
        return SYS_STATE_FAULT;
    }
    return ctx->state;
}

bool vista_can_transition(const firmware_context_t *ctx,
                          sys_state_event_t event)
{
    if (ctx == NULL) {
        return false;
    }
    return (find_transition(ctx->state, event) != NULL);
}
