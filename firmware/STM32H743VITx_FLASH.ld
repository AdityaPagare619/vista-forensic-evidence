/*
 * =============================================================================
 * VISTA 2.0 Firmware — Linker Script for STM32H743VITx
 * =============================================================================
 * Memory layout for STM32H743VIT6 (1 MB Flash, 1 MB RAM)
 *
 * Memory Regions:
 *   FLASH  : 2 MB (dual-bank) at 0x08000000
 *   RAM_D1 : 512 KB (AXI SRAM) at 0x24000000 — main application RAM
 *   RAM_D2 : 288 KB (SRAM1+SRAM2+SRAM3) at 0x30000000 — DMA buffers
 *   RAM_D3 :  64 KB (SRAM4) at 0x38000000 — D3 domain
 *   ITCM   :  64 KB at 0x00000000 — instruction TCM (fast code)
 *   DTCM   : 128 KB at 0x20000000 — data TCM (fast data, stack)
 *
 * Sections:
 *   .isr_vector  — Vector table (placed at Flash start)
 *   .text        — Code
 *   .rodata      — Constants
 *   .data        — Initialized variables (Flash -> RAM copy)
 *   .bss         — Zero-initialized variables
 *   ._user_heap — Heap (for malloc)
 *   ._user_stack — Main stack (DTCM for best performance)
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 */

/* Entry point */
ENTRY(Reset_Handler)

/* Highest address of the main stack (end of DTCM) */
_estack = ORIGIN(DTCM) + LENGTH(DTCM);

/* Minimum heap and stack sizes (linker checks) */
_Min_Heap_Size  = 0x2000;  /* 8 KB heap */
_Min_Stack_Size = 0x4000;  /* 16 KB stack */

/* =============================================================================
 *  Memory Definitions
 * ============================================================================= */
MEMORY
{
    FLASH  (rx)  : ORIGIN = 0x08000000, LENGTH = 1024K
    RAM_D1 (rwx) : ORIGIN = 0x24000000, LENGTH = 512K
    RAM_D2 (rwx) : ORIGIN = 0x30000000, LENGTH = 288K
    RAM_D3 (rwx) : ORIGIN = 0x38000000, LENGTH = 64K
    ITCM   (rx)  : ORIGIN = 0x00000000, LENGTH = 64K
    DTCM   (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}

/* =============================================================================
 *  Section Allocation
 * ============================================================================= */
SECTIONS
{
    /* ---------------------------------------------------------------------- */
    /*  Vector table — must be first in Flash                                 */
    /* ---------------------------------------------------------------------- */
    .isr_vector :
    {
        . = ALIGN(4);
        KEEP(*(.isr_vector))  /* Startup code and interrupt vector table */
        . = ALIGN(4);
    } >FLASH

    /* ---------------------------------------------------------------------- */
    /*  Code and read-only data                                               */
    /* ---------------------------------------------------------------------- */
    .text :
    {
        . = ALIGN(4);
        *(.text)
        *(.text*)
        *(.glue_7)         /* ARM-to-Thumb glue code */
        *(.glue_7t)        /* Thumb-to-ARM glue code */
        *(.eh_frame)

        KEEP(*(.init))
        KEEP(*(.fini))

        . = ALIGN(4);
        _etext = .;
    } >FLASH

    /* ---------------------------------------------------------------------- */
    /*  Read-only data (constants, string literals)                           */
    /* ---------------------------------------------------------------------- */
    .rodata :
    {
        . = ALIGN(4);
        *(.rodata)
        *(.rodata*)
        . = ALIGN(4);
    } >FLASH

    /* ---------------------------------------------------------------------- */
    /*  ARM exception unwinding tables                                        */
    /* ---------------------------------------------------------------------- */
    .ARM.extab :
    {
        *(.ARM.extab* .gnu.linkonce.armextab.*)
    } >FLASH

    .ARM :
    {
        __exidx_start = .;
        *(.ARM.exidx*)
        __exidx_end = .;
    } >FLASH

    /* ---------------------------------------------------------------------- */
    /*  Initialized data (copied from Flash to RAM_D1 at startup)             */
    /* ---------------------------------------------------------------------- */
    _sidata = LOADADDR(.data);

    .data :
    {
        . = ALIGN(4);
        _sdata = .;
        *(.data)
        *(.data*)
        *(.RamFunc)        /* Functions that must run from RAM */
        *(.RamFunc*)
        . = ALIGN(4);
        _edata = .;
    } >RAM_D1 AT> FLASH

    /* ---------------------------------------------------------------------- */
    /*  Zero-initialized data (BSS)                                           */
    /* ---------------------------------------------------------------------- */
    .bss :
    {
        . = ALIGN(4);
        _sbss = .;
        __bss_start__ = _sbss;
        *(.bss)
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
        __bss_end__ = _ebss;
    } >RAM_D1

    /* ---------------------------------------------------------------------- */
    /*  User heap (for malloc/newlib)                                         */
    /* ---------------------------------------------------------------------- */
    ._user_heap_stack :
    {
        . = ALIGN(8);
        PROVIDE(end = .);
        PROVIDE(_end = .);
        . = . + _Min_Heap_Size;
        . = . + _Min_Stack_Size;
        . = ALIGN(8);
    } >RAM_D1

    /* ---------------------------------------------------------------------- */
    /*  Main stack — placed in DTCM for fastest access (Cortex-M7 TCM port)   */
    /* ---------------------------------------------------------------------- */
    /* Note: Stack pointer is set to _estack (end of DTCM) by Reset_Handler   */
    /* DTCM is NOT explicitly sectioned — it's used via linker address only.   */

    /* ---------------------------------------------------------------------- */
    /*  DMA buffers — placed in D2 SRAM (accessible by DMA1/DMA2)             */
    /* ---------------------------------------------------------------------- */
    .dma_buffers (NOLOAD) :
    {
        . = ALIGN(32);  /* Cache-line aligned for Cortex-M7 */
        *(.dma_buffer)
        *(.dma_buffer*)
        . = ALIGN(32);
    } >RAM_D2

    /* ---------------------------------------------------------------------- */
    /*  Camera frame buffers — placed in D2 SRAM (large contiguous)           */
    /* ---------------------------------------------------------------------- */
    .camera_buf (NOLOAD) :
    {
        . = ALIGN(32);
        *(.camera_buffer)
        *(.camera_buffer*)
        . = ALIGN(32);
    } >RAM_D2

    /* ---------------------------------------------------------------------- */
    /*  Audio DMA buffers — placed in D2 SRAM                                 */
    /* ---------------------------------------------------------------------- */
    .audio_buf (NOLOAD) :
    {
        . = ALIGN(32);
        *(.audio_buffer)
        *(.audio_buffer*)
        . = ALIGN(32);
    } >RAM_D2

    /* ---------------------------------------------------------------------- */
    /*  SRAM4 (D3 domain) — can be used for BDMA-accessible data              */
    /* ---------------------------------------------------------------------- */
    .sram4 (NOLOAD) :
    {
        . = ALIGN(4);
        *(.sram4)
        *(.sram4*)
        . = ALIGN(4);
    } >RAM_D3

    /* ---------------------------------------------------------------------- */
    /*  discard debug sections in release                                     */
    /* ---------------------------------------------------------------------- */
    /DISCARD/ :
    {
        libc.a(*)
        libm.a(*)
        libgcc.a(*)
    }

    /* ---------------------------------------------------------------------- */
    /*  ARM attributes                                                        */
    /* ---------------------------------------------------------------------- */
    .ARM.attributes 0 : { *(.ARM.attributes) }
}

/* =============================================================================
 *  End of symbols for heap/stack checking
 * ============================================================================= */
PROVIDE(_heap_start = _end);
PROVIDE(_heap_end = _estack - _Min_Stack_Size);
