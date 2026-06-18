/**
 * @file main.c
 * @brief VISTA 2.0 Firmware Entry Point and Main Loop
 *
 * System initialization, main loop, state machine execution, and
 * interrupt vector table for STM32H743VIT6.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 */

#include "firmware.h"
#include <string.h>

/* ========================================================================== */
/*  STATIC DATA                                                               */
/* ========================================================================== */

/** @brief Global firmware context (allocated in D1 RAM) */
static firmware_context_t g_firmware;

/** @brief Main loop timing variables */
static volatile uint32_t g_systick_ms = 0U;
static volatile bool g_loop_tick = false;

/* ========================================================================== */
/*  VECTOR TABLE (placed in .isr_vector section)                              */
/* ========================================================================== */

/* Forward declarations for exception handlers */
void Reset_Handler(void);
void NMI_Handler(void);
void HardFault_Handler(void);
void MemManage_Handler(void);
void BusFault_Handler(void);
void UsageFault_Handler(void);
void SVC_Handler(void);
void DebugMon_Handler(void);
void PendSV_Handler(void);
void SysTick_Handler(void);

/* ISR handlers for peripherals */
void DMA1_Stream0_IRQHandler(void);  /* IMU0 SPI RX */
void DMA1_Stream1_IRQHandler(void);  /* IMU1 SPI RX */
void DMA1_Stream2_IRQHandler(void);  /* IMU2 SPI RX */
void DMA1_Stream3_IRQHandler(void);  /* Audio I2S2 */
void DMA1_Stream4_IRQHandler(void);  /* Audio I2S3 */
void DMA2_Stream0_IRQHandler(void);  /* Camera DCMI */
void SPI1_IRQHandler(void);
void SPI2_IRQHandler(void);
void SPI4_IRQHandler(void);
void SPI6_IRQHandler(void);
void FDCAN1_IT0_IRQHandler(void);
void FDCAN1_IT1_IRQHandler(void);
void FDCAN2_IT0_IRQHandler(void);
void FDCAN2_IT1_IRQHandler(void);
void DCMI_IRQHandler(void);
void EXTI9_5_IRQHandler(void);       /* IMU DRDY lines */
void ADC_IRQHandler(void);
void IWDG_IRQHandler(void);
void TIM6_DAC_IRQHandler(void);      /* System tick timer */

/* ========================================================================== */
/*  STARTUP CODE                                                              */
/* ========================================================================== */

/** @brief Stack pointer initial value (end of DTCM) */
extern uint32_t _estack;

/** @brief Linker script symbols */
extern uint32_t _sidata;    /* Start of .data initializers in Flash */
extern uint32_t _sdata;     /* Start of .data section in RAM */
extern uint32_t _edata;     /* End of .data section in RAM */
extern uint32_t _sbss;      /* Start of .bss section */
extern uint32_t _ebss;      /* End of .bss section */

/**
 * @brief Reset handler — C runtime initialization.
 *
 * Copies .data from Flash to RAM, zeros .bss, then calls main.
 * Placed in .isr_vector via linker script attribute.
 */
void Reset_Handler(void)
{
    uint32_t *src, *dst;

    /* Enable FPU (CP10 and CP11 full access) */
    /* SCB->CPACR |= ((3UL << 10*2) | (3UL << 11*2)); */

    /* Copy .data section from Flash to RAM */
    src = &_sidata;
    dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }

    /* Zero-fill .bss section */
    dst = &_sbss;
    while (dst < &_ebss) {
        *dst++ = 0UL;
    }

    /* Call main firmware entry */
    vista_main();

    /* Should never return — if it does, infinite loop */
    while (1) {
        /* Intentional infinite loop */
    }
}

/* ========================================================================== */
/*  DEFAULT / WEAK HANDLERS                                                   */
/* ========================================================================== */

/**
 * @brief Default handler for unimplemented interrupts.
 *
 * Infinite loop for debugging — can be overridden.
 */
__attribute__((weak))
void Default_Handler(void)
{
    while (1) {
        /* Trap — unhandled interrupt */
    }
}

/* Weak aliases — override in application as needed */
__attribute__((weak, alias("Default_Handler"))) void NMI_Handler(void);
__attribute__((weak, alias("Default_Handler"))) void MemManage_Handler(void);
__attribute__((weak, alias("Default_Handler"))) void BusFault_Handler(void);
__attribute__((weak, alias("Default_Handler"))) void UsageFault_Handler(void);
__attribute__((weak, alias("Default_Handler"))) void DebugMon_Handler(void);

/* ========================================================================== */
/*  FAULT HANDLERS                                                            */
/* ========================================================================== */

/**
 * @brief Hard fault handler.
 *
 * Captures fault status registers and attempts emergency FRAM save
 * before system reset.
 */
void HardFault_Handler(void)
{
    /* Read fault status registers */
    volatile uint32_t cfsr  = *(volatile uint32_t *)0xE000ED28UL;
    volatile uint32_t hfsr  = *(volatile uint32_t *)0xE000ED2CUL;
    volatile uint32_t mmfar = *(volatile uint32_t *)0xE000ED34UL;
    volatile uint32_t bfar  = *(volatile uint32_t *)0xE000ED38UL;

    /* Suppress unused variable warnings */
    (void)cfsr;
    (void)hfsr;
    (void)mmfar;
    (void)bfar;

    /* Attempt emergency evidence save */
    vista_hardfault_handler(NULL);

    /* Reset system */
    while (1) {
        /* Wait for watchdog reset or external intervention */
    }
}

/* ========================================================================== */
/*  SYSTICK / TIMING                                                          */
/* ========================================================================== */

/**
 * @brief SysTick interrupt handler — 1 ms system tick.
 */
void SysTick_Handler(void)
{
    g_systick_ms++;
    g_loop_tick = true;
}

/* ========================================================================== */
/*  PERIPHERAL ISR ROUTING                                                    */
/* ========================================================================== */

/** @brief Firmware context pointer for ISR access */
static firmware_context_t *g_isr_ctx = NULL;

/**
 * @brief DMA1 Stream 0 — IMU0 SPI RX complete.
 */
void DMA1_Stream0_IRQHandler(void)
{
    /* TODO: Clear DMA TC flag, set IMU0 data_ready */
    if (g_isr_ctx != NULL) {
        imu_drdy_isr(0U);
    }
}

/**
 * @brief DMA1 Stream 1 — IMU1 SPI RX complete.
 */
void DMA1_Stream1_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        imu_drdy_isr(1U);
    }
}

/**
 * @brief DMA1 Stream 2 — IMU2 SPI RX complete.
 */
void DMA1_Stream2_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        imu_drdy_isr(2U);
    }
}

/**
 * @brief DMA1 Stream 3 — Audio I2S2.
 */
void DMA1_Stream3_IRQHandler(void)
{
    /* TODO: Determine HT/TC, call appropriate handler */
    if (g_isr_ctx != NULL) {
        audio_i2s2_tc_isr(&g_isr_ctx->audio);
    }
}

/**
 * @brief DMA1 Stream 4 — Audio I2S3.
 */
void DMA1_Stream4_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        audio_i2s3_tc_isr(&g_isr_ctx->audio);
    }
}

/**
 * @brief DMA2 Stream 0 — Camera DCMI.
 */
void DMA2_Stream0_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        camera_dma_tc_isr(&g_isr_ctx->camera);
    }
}

/**
 * @brief FDCAN1 interrupt handler (RX FIFO 0).
 */
void FDCAN1_IT0_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        can_rx_isr(&g_isr_ctx->can[0U]);
    }
}

/**
 * @brief FDCAN1 interrupt handler (RX FIFO 1 / errors).
 */
void FDCAN1_IT1_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        can_error_isr(&g_isr_ctx->can[0U]);
    }
}

/**
 * @brief FDCAN2 interrupt handler (RX FIFO 0).
 */
void FDCAN2_IT0_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        can_rx_isr(&g_isr_ctx->can[1U]);
    }
}

/**
 * @brief FDCAN2 interrupt handler (RX FIFO 1 / errors).
 */
void FDCAN2_IT1_IRQHandler(void)
{
    if (g_isr_ctx != NULL) {
        can_error_isr(&g_isr_ctx->can[1U]);
    }
}

/**
 * @brief EXTI lines 5-9 — IMU data-ready pins.
 */
void EXTI9_5_IRQHandler(void)
{
    /* TODO: Read EXTI PR to determine which IMU triggered, call imu_drdy_isr */
}

/* ========================================================================== */
/*  CLOCK CONFIGURATION                                                       */
/* ========================================================================== */

vista_error_t vista_clock_config(void)
{
    /* TODO: Full implementation using HAL RCC or register-level:
     *
     * 1. Enable HSE (25 MHz crystal)
     * 2. Configure PLL1:
     *    - M = 5 (HSE / 5 = 5 MHz VCO input)
     *    - N = 192 (5 MHz × 192 = 960 MHz VCO output)
     *    - P = 2 (960 / 2 = 480 MHz SYSCLK)
     *    - Q = 4 (960 / 4 = 240 MHz for peripherals)
     *    - R = 2 (960 / 2 = 480 MHz for DSI)
     * 3. Set Flash latency to 4 wait states (for 480 MHz)
     * 4. Set HPRE = /2 -> AHB = 240 MHz
     * 5. Set D1PPRE = /2 -> APB3 = 120 MHz
     * 6. Set D2PPRE1 = /2 -> APB1 = 120 MHz
     * 7. Set D2PPRE2 = /2 -> APB2 = 120 MHz
     * 8. Set D3PPRE = /2 -> APB4 = 120 MHz
     * 9. Select PLL1 as SYSCLK source
     * 10. Enable I/D caches
     */

    return VISTA_OK;
}

/* ========================================================================== */
/*  PERIPHERAL INITIALIZATION                                                 */
/* ========================================================================== */

vista_error_t vista_periph_init(firmware_context_t *ctx)
{
    vista_error_t ret = VISTA_OK;

    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    /* 1. Initialize GPIO clocks and pins */

    /* 2. Initialize DMA controllers (DMA1, DMA2, BDMA) */

    /* 3. Initialize SPI buses for IMUs */
    for (uint8_t i = 0U; i < VISTA_IMU_COUNT; i++) {
        ret = imu_init(i, &ctx->imu[i]);
        if (ret != VISTA_OK) {
            break;
        }
    }

    /* 4. Initialize CAN peripherals */
    for (uint8_t i = 0U; i < VISTA_CAN_CHANNEL_COUNT; i++) {
        ret = can_init((can_channel_t)i, &ctx->can[i], true);
        if (ret != VISTA_OK) {
            break;
        }
    }

    /* 5. Initialize audio I2S */
    if (ret == VISTA_OK) {
        ret = audio_init(&ctx->audio);
    }

    /* 6. Initialize camera DCMI */
    if (ret == VISTA_OK) {
        ret = camera_init(&ctx->camera);
    }

    /* 7. Initialize FRAM SPI */
    if (ret == VISTA_OK) {
        ret = fram_init();
    }

    /* 8. Initialize ADC for supercapacitor voltage */
    if (ret == VISTA_OK) {
        /* TODO: ADC init for VCAP measurement */
    }

    /* 9. Initialize independent watchdog */
    if (ret == VISTA_OK) {
        /* TODO: IWDG init with VISTA_IWDG_TIMEOUT_MS */
    }

    /* 10. Configure NVIC interrupts */

    return ret;
}

/* ========================================================================== */
/*  SYSTEM INITIALIZATION                                                     */
/* ========================================================================== */

vista_error_t vista_system_init(firmware_context_t *ctx)
{
    vista_error_t ret;

    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    /* Zero out context */
    (void)memset(ctx, 0, sizeof(firmware_context_t));

    /* Store ISR context pointer */
    g_isr_ctx = ctx;

    /* Determine reset reason */
    ctx->reset_reason = 0U;  /* TODO: Read RCC_CSR for reset flags */

    /* Configure system clock */
    ret = vista_clock_config();
    if (ret != VISTA_OK) {
        return ret;
    }

    /* Initialize DWT cycle counter for microsecond timing */
    /* TODO: Enable DWT->CYCCNT */

    /* Initialize all peripherals */
    ret = vista_periph_init(ctx);
    if (ret != VISTA_OK) {
        ctx->state = SYS_STATE_FAULT;
        return ret;
    }

    /* Initialize ESKF */
    ret = eskf_init(ctx);
    if (ret == VISTA_OK) {
        ctx->fusion_initialized = true;
    }

    /* Initialize PDTSA detection */
    ret = detection_init(ctx);
    if (ret != VISTA_OK) {
        return ret;
    }

    /* Initialize evidence chain */
    ret = evidence_init(ctx);
    if (ret != VISTA_OK) {
        return ret;
    }

    /* Run built-in self-test */
    ctx->state = SYS_STATE_SELF_TEST;
    for (uint8_t i = 0U; i < VISTA_IMU_COUNT; i++) {
        ret = imu_self_test(i, &ctx->imu[i]);
        if (ret != VISTA_OK) {
            ctx->state = SYS_STATE_FAULT;
            return ret;
        }
    }

    /* Transition to IDLE */
    ctx->state = SYS_STATE_IDLE;

    return VISTA_OK;
}

/* ========================================================================== */
/*  MAIN FIRMWARE ENTRY                                                       */
/* ========================================================================== */

void vista_main(void)
{
    /* Initialize system */
    vista_error_t ret = vista_system_init(&g_firmware);
    if (ret != VISTA_OK) {
        /* System failed to initialize — enter fault state */
        g_firmware.state = SYS_STATE_FAULT;
    }

    /* Enable interrupts */
    /* __enable_irq(); */

    /* Main loop — never returns */
    while (1) {
        vista_loop();
    }
}

/* ========================================================================== */
/*  MAIN LOOP                                                                 */
/* ========================================================================== */

void vista_loop(void)
{
    /* Wait for 1 ms tick */
    while (!g_loop_tick) {
        /* Low-power hint: __WFI(); */
    }
    g_loop_tick = false;

    g_firmware.loop_count++;
    g_firmware.uptime_ms = g_systick_ms;

    /* --- 1. Process IMU data --- */
    for (uint8_t i = 0U; i < VISTA_IMU_COUNT; i++) {
        if (imu_dma_poll(i, &g_firmware.imu[i])) {
            /* Convert and feed to ESKF + detection */
            imu_sample_t sample;
            if (g_firmware.imu[i].type == IMU_TYPE_IAM20680HP) {
                imu_convert_6axis(
                    (const imu_raw_sample_6axis_t *)g_firmware.imu[i].rx_buf,
                    &g_firmware.imu[i].calibration, i, &sample);
            } else {
                imu_convert_3axis(
                    (const imu_raw_sample_3axis_t *)g_firmware.imu[i].rx_buf,
                    &g_firmware.imu[i].calibration, i, &sample);
            }

            /* ESKF update (use IMU0 as primary) */
            if (i == 0U) {
                eskf_predict(&g_firmware, &sample.gyro_rads, 0.001f);
                eskf_update_accel(&g_firmware, &sample.accel_ms2);
            }

            /* PDTSA detection (feed all IMUs) */
            if (g_firmware.state == SYS_STATE_ARMED) {
                detection_result_t det_result;
                detection_feed(&g_firmware, &sample, &det_result);

                if (det_result.impact_detected) {
                    g_firmware.detection = det_result;
                    vista_state_machine_tick(&g_firmware,
                                             STATE_EVT_IMPACT_DET);
                }
            }

            /* Start next DMA transfer */
            imu_read_dma_start(i, &g_firmware.imu[i]);
        }
    }

    /* --- 2. Process audio data --- */
    {
        audio_frame_t *audio_frame;
        if (audio_frame_get(&g_firmware.audio, &audio_frame) == VISTA_OK) {
            /* Audio processing would go here */
            audio_frame_release(&g_firmware.audio, audio_frame);
        }
    }

    /* --- 3. Process camera data --- */
    {
        camera_frame_t *cam_frame;
        if (camera_frame_get(&g_firmware.camera, &cam_frame) == VISTA_OK) {
            /* Camera frame processing would go here */
            camera_frame_release(&g_firmware.camera, cam_frame);
        }
    }

    /* --- 4. Process CAN messages --- */
    for (uint8_t i = 0U; i < VISTA_CAN_CHANNEL_COUNT; i++) {
        can_frame_t can_frame;
        while (can_receive(&g_firmware.can[i], &can_frame) == VISTA_OK) {
            /* CAN message processing would go here */
        }
        can_tx_process_queue(&g_firmware.can[i]);
    }

    /* --- 5. Power management --- */
    power_read_vcap(&g_firmware, &g_firmware.vcap_mv);
    g_firmware.supercap_ready = power_supercap_ready(&g_firmware);

    /* Check for power failure during post-crash */
    if (g_firmware.state == SYS_STATE_POST_CRASH) {
        if (g_firmware.vcap_mv < VISTA_SUPERCAP_CRIT_MV) {
            g_firmware.crash.power_failing = true;
            /* Save evidence chain to FRAM before power loss */
            if (!g_firmware.crash.evidence_saved) {
                evidence_verify_chain(&g_firmware);
                g_firmware.crash.evidence_saved = true;
            }
        }
    }

    /* --- 6. State machine tick --- */
    vista_state_machine_tick(&g_firmware, STATE_EVT_COUNT);

    /* --- 7. Feed watchdog --- */
    /* TODO: IWDG_Refresh() */
    g_firmware.watchdog_fed = true;
}

/* ========================================================================== */
/*  STATE MACHINE                                                             */
/* ========================================================================== */

vista_error_t vista_state_machine_tick(firmware_context_t *ctx,
                                      sys_state_event_t event)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    sys_state_t old_state = ctx->state;

    switch (ctx->state) {
    case SYS_STATE_INIT:
        /* Transitions handled externally during vista_system_init */
        break;

    case SYS_STATE_SELF_TEST:
        /* Transitions handled externally after BIST */
        break;

    case SYS_STATE_IDLE:
        if (event == STATE_EVT_ARM_CMD) {
            ctx->state = SYS_STATE_ARMED;
            /* Start IMU DMA captures */
            for (uint8_t i = 0U; i < VISTA_IMU_COUNT; i++) {
                imu_read_dma_start(i, &ctx->imu[i]);
            }
            /* Start audio capture */
            audio_start(&ctx->audio);
            /* Start camera capture */
            camera_start(&ctx->camera);
        }
        break;

    case SYS_STATE_ARMED:
        if (event == STATE_EVT_DISARM_CMD) {
            ctx->state = SYS_STATE_IDLE;
            audio_stop(&ctx->audio);
            camera_stop(&ctx->camera);
        } else if (event == STATE_EVT_IMPACT_DET) {
            ctx->state = SYS_STATE_RECORDING;
            ctx->crash.impact_detected = true;
            ctx->crash.impact_timestamp_us = vista_get_dwt_cycles();
            /* Log detection event as evidence */
            evidence_add(ctx, EVIDENCE_TYPE_IMPACT_DET,
                         (const uint8_t *)&ctx->detection,
                         sizeof(detection_result_t));
        }
        break;

    case SYS_STATE_RECORDING:
        if (event == STATE_EVT_POSTCRASH_ENTRY) {
            ctx->state = SYS_STATE_POST_CRASH;
            ctx->crash.postcrash_start_us = vista_get_dwt_cycles();
        } else if (event == STATE_EVT_RECORD_COMPLETE) {
            ctx->state = SYS_STATE_IDLE;
            ctx->crash.impact_detected = false;
            detection_reset(ctx);
        }
        break;

    case SYS_STATE_POST_CRASH:
        /* Stay in this state until power failure or timeout */
        {
            uint32_t elapsed_ms = vista_cycles_to_us(
                vista_get_dwt_cycles() - ctx->crash.postcrash_start_us) / 1000U;
            if (elapsed_ms > STATE_POSTCRASH_DURATION_MS) {
                ctx->state = SYS_STATE_IDLE;
                ctx->crash.impact_detected = false;
                detection_reset(ctx);
            }
        }
        break;

    case SYS_STATE_FAULT:
        if (event == STATE_EVT_RECOVERY) {
            ctx->state = SYS_STATE_INIT;
        }
        break;

    default:
        ctx->state = SYS_STATE_FAULT;
        break;
    }

    /* Log state transition */
    if (ctx->state != old_state) {
        vista_state_log(ctx, old_state, ctx->state, event);
        ctx->state_entry_time_us = vista_get_dwt_cycles();
    }

    return VISTA_OK;
}

const char *vista_state_name(sys_state_t state)
{
    static const char *names[] = {
        "INIT", "SELF_TEST", "IDLE", "ARMED",
        "RECORDING", "POST_CRASH", "FAULT"
    };

    if ((uint32_t)state < (uint32_t)SYS_STATE_COUNT) {
        return names[state];
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

/* ========================================================================== */
/*  UTILITY FUNCTIONS                                                         */
/* ========================================================================== */

uint32_t vista_get_uptime_ms(void)
{
    return g_systick_ms;
}

uint32_t vista_get_dwt_cycles(void)
{
    /* TODO: Read DWT->CYCCNT register */
    return 0U;
}

uint32_t vista_cycles_to_us(uint32_t cycles)
{
    /* DWT runs at SYSCLK / DWT_DIVIDER */
    return cycles / (VISTA_SYSCLK_HZ / 1000000UL);
}

void vista_hardfault_handler(void *stack_frame)
{
    (void)stack_frame;

    /* Attempt to save critical evidence to FRAM */
    /* This is best-effort — FRAM writes may fail if SPI is corrupted */

    /* Log the fault event */
    evidence_block_t fault_block;
    (void)memset(&fault_block, 0, sizeof(fault_block));
    fault_block.header.type = EVIDENCE_TYPE_FAULT_LOG;
    fault_block.header.timestamp_us = vista_get_dwt_cycles();
    fault_block.header.payload_size = 4U;

    /* Store reset reason as evidence payload */
    uint32_t fault_code = 0xDEAD0001UL;
    (void)memcpy(fault_block.payload, &fault_code, sizeof(fault_code));

    /* Best-effort FRAM write */
    /* evidence_add() may fail if SPI is broken — that's acceptable */
}

void vista_system_reset(void)
{
    /* TODO: NVIC_SystemReset() or direct RCC register write */
    while (1) {
        /* Wait for reset */
    }
}
