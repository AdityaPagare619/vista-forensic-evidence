# =============================================================================
# VISTA 2.0 Firmware — Makefile for ARM Cortex-M7 Cross-Compilation
# =============================================================================
# Target: STM32H743VIT6 (Cortex-M7, FPU, DSP)
# Toolchain: arm-none-eabi-gcc
#
# Usage:
#   make            — Build release firmware
#   make debug      — Build debug firmware with symbols
#   make clean      — Remove build artifacts
#   make flash      — Flash via ST-Link (openocd)
#   make size       — Show firmware size breakdown
#   make disasm     — Generate disassembly listing
# =============================================================================

# ---------------------------------------------------------------------------
#  Toolchain
# ---------------------------------------------------------------------------
PREFIX  = arm-none-eabi-
CC      = $(PREFIX)gcc
AS      = $(PREFIX)gcc -x assembler-with-cpp
LD      = $(PREFIX)gcc
OBJCOPY = $(PREFIX)objcopy
OBJDUMP = $(PREFIX)objdump
SIZE    = $(PREFIX)size
GDB     = $(PREFIX)gdb

# ---------------------------------------------------------------------------
#  Target
# ---------------------------------------------------------------------------
TARGET  = vista_fw
BUILD   = build

# ---------------------------------------------------------------------------
#  MCU Flags
# ---------------------------------------------------------------------------
CPU     = -mcpu=cortex-m7
FPU     = -mfpu=fpv5-d16
FLOAT   = -mfloat-abi=hard
MCU     = $(CPU) -mthumb $(FPU) $(FLOAT)

# ---------------------------------------------------------------------------
#  Source Files
# ---------------------------------------------------------------------------
C_SRCS  = \
	src/main.c \
	src/imu_interface.c \
	src/eskf.c \
	src/detection.c \
	src/evidence.c \
	src/crash_state_machine.c \
	src/fram_storage.c

ASM_SRCS = \
	startup_stm32h743vitx.s

C_INCS  = \
	-Iinclude \
	-I$(CMSIS_DIR)/Include \
	-I$(HAL_DIR)/Inc

# ---------------------------------------------------------------------------
#  CMSIS and HAL Paths (adjust to your STM32CubeH7 installation)
# ---------------------------------------------------------------------------
CMSIS_DIR   = Drivers/CMSIS
HAL_DIR     = Drivers/STM32H7xx_HAL_Driver

# ---------------------------------------------------------------------------
#  Build Configuration
# ---------------------------------------------------------------------------
DEFS    = \
	-DSTM32H743xx \
	-DUSE_HAL_DRIVER \
	-DHSE_VALUE=25000000U

# Optimization levels: -Og (debug), -O2 (release), -Os (size)
OPT_DEBUG   = -Og -g3 -gdwarf-2
OPT_RELEASE = -O2 -flto

# Select release by default
OPT = $(OPT_RELEASE)

# ---------------------------------------------------------------------------
#  Compiler Flags
# ---------------------------------------------------------------------------
CFLAGS  = $(MCU) $(DEFS) $(C_INCS) $(OPT)
CFLAGS += -Wall -Wextra -Werror -Wno-unused-parameter
CFLAGS += -fdata-sections -ffunction-sections
CFLAGS += -fstack-usage
CFLAGS += -std=c11
CFLAGS += -MMD -MP -MF"$(@:%.o=%.d)"

# MISRA-C:2012 compliance flags (optional — enable with make misra)
ifdef MISRA
CFLAGS += --misra-port=all
endif

# ---------------------------------------------------------------------------
#  Assembler Flags
# ---------------------------------------------------------------------------
ASFLAGS = $(MCU) -Wall -fdata-sections -ffunction-sections

# ---------------------------------------------------------------------------
#  Linker Flags
# ---------------------------------------------------------------------------
LDSCRIPT = STM32H743VITx_FLASH.ld

LDFLAGS  = $(MCU) -specs=nano.specs -specs=nosys.specs
LDFLAGS += -T$(LDSCRIPT)
LDFLAGS += -Wl,-Map=$(BUILD)/$(TARGET).map,--cref
LDFLAGS += -Wl,--gc-sections
LDFLAGS += -Wl,--print-memory-usage
LDFLAGS += -lc -lm -lnosys

# ---------------------------------------------------------------------------
#  Build Rules
# ---------------------------------------------------------------------------

# Object files
C_OBJS     = $(addprefix $(BUILD)/,$(notdir $(C_SRCS:.c=.o)))
ASM_OBJS   = $(addprefix $(BUILD)/,$(notdir $(ASM_SRCS:.s=.o)))
OBJS       = $(C_OBJS) $(ASM_OBJS)

# Dependency files
DEPS = $(OBJS:.o=.d)

# VPATH for source lookup
vpath %.c $(sort $(dir $(C_SRCS)))
vpath %.s $(sort $(dir $(ASM_SRCS)))

# Default target
all: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).hex $(BUILD)/$(TARGET).bin
	@echo ""
	@echo "========================================="
	@echo "  Build complete: $(TARGET)"
	@echo "========================================="
	$(SIZE) $(BUILD)/$(TARGET).elf

# Compile C sources
$(BUILD)/%.o: %.c | $(BUILD)
	@echo "[CC]  $<"
	@$(CC) -c $(CFLAGS) $< -o $@

# Compile assembly sources
$(BUILD)/%.o: %.s | $(BUILD)
	@echo "[AS]  $<"
	@$(AS) -c $(ASFLAGS) $< -o $@

# Link
$(BUILD)/$(TARGET).elf: $(OBJS) $(LDSCRIPT)
	@echo "[LD]  $@"
	@$(LD) $(OBJS) $(LDFLAGS) -o $@

# Generate Intel HEX
$(BUILD)/$(TARGET).hex: $(BUILD)/$(TARGET).elf
	@echo "[HEX] $@"
	@$(OBJCOPY) -O ihex $< $@

# Generate raw binary
$(BUILD)/$(TARGET).bin: $(BUILD)/$(TARGET).elf
	@echo "[BIN] $@"
	@$(OBJCOPY) -O binary -S $< $@

# Create build directory
$(BUILD):
	@mkdir -p $@

# Clean
clean:
	@echo "[CLEAN]"
	@rm -rf $(BUILD)

# ---------------------------------------------------------------------------
#  Debug Build
# ---------------------------------------------------------------------------
debug: OPT = $(OPT_DEBUG)
debug: LDFLAGS += -Wl,--nmagic
debug: all

# ---------------------------------------------------------------------------
#  Flash via OpenOCD / ST-Link
# ---------------------------------------------------------------------------
flash: $(BUILD)/$(TARGET).elf
	@echo "[FLASH] Programming via ST-Link..."
	openocd -f interface/stlink.cfg \
	        -f target/stm32h7x.cfg \
	        -c "program $< verify reset exit"

# ---------------------------------------------------------------------------
#  Flash via STM32CubeProgrammer (CLI)
# ---------------------------------------------------------------------------
flash-cube: $(BUILD)/$(TARGET).bin
	@echo "[FLASH] Programming via STM32CubeProgrammer..."
	STM32_Programmer_CLI -c port=SWD -w $< 0x08000000 -v -rst

# ---------------------------------------------------------------------------
#  Debug with GDB + OpenOCD
# ---------------------------------------------------------------------------
gdb: $(BUILD)/$(TARGET).elf
	@echo "[GDB] Starting GDB session..."
	$(GDB) -tui $< -ex "target remote :3333" -ex "monitor reset halt"

# ---------------------------------------------------------------------------
#  Size Report
# ---------------------------------------------------------------------------
size: $(BUILD)/$(TARGET).elf
	$(SIZE) -A -d $<

# ---------------------------------------------------------------------------
#  Disassembly
# ---------------------------------------------------------------------------
disasm: $(BUILD)/$(TARGET).elf
	$(OBJDUMP) -d -S -C $< > $(BUILD)/$(TARGET).dis

# ---------------------------------------------------------------------------
#  MISRA Check (requires PC-lint or cppcheck)
# ---------------------------------------------------------------------------
misra:
	@echo "[MISRA] Running cppcheck with MISRA addon..."
	cppcheck --enable=all --addon=misra --std=c11 \
	         --suppress=missingIncludeSystem \
	         $(C_SRCS) include/

# ---------------------------------------------------------------------------
#  Static Analysis
# ---------------------------------------------------------------------------
analyze:
	@echo "[ANALYZE] Running cppcheck..."
	cppcheck --enable=all --std=c11 \
	         --suppress=missingIncludeSystem \
	         --error-exitcode=1 \
	         $(C_SRCS) include/

# ---------------------------------------------------------------------------
#  Documentation (Doxygen)
# ---------------------------------------------------------------------------
docs:
	@echo "[DOXY] Generating documentation..."
	doxygen Doxyfile

# ---------------------------------------------------------------------------
#  Include dependency files
# ---------------------------------------------------------------------------
-include $(DEPS)

# ---------------------------------------------------------------------------
#  Phony targets
# ---------------------------------------------------------------------------
.PHONY: all debug clean flash flash-cube gdb size disasm misra analyze docs
