# This file is used by MicroPython Make-based builds such as the Unix port.
# For CMake-based builds, see the .cmake file in the same directory.

# When building Micropython, the parent directory of this module is given as:
#     make USER_C_MODULES=<path to workspace root>

LVMP_DIR := $(USERMOD_DIR)
BINDINGS_DIR ?= $(abspath $(LVMP_DIR)/../lv_bindings)
LVMP_C := $(BINDINGS_DIR)/generated/lvgl_micropython.c
LVGL_DIR := $(BINDINGS_DIR)/lvgl
SOURCES = $(shell find $(LVGL_DIR)/src -type f -name "*.c")
SOURCES += $(LVMP_DIR)/lv_mem_core_micropython.c

$(if $(wildcard $(LVMP_C)),,$(error $(LVMP_C) not found. Run $(BINDINGS_DIR)/regenerate_lvmp.sh after changing lvgl, lv_conf.h, or binding/))

# -Wno-unused-function here is not enough on ports that append -Werror after py.mk
# (e.g. webassembly); those ports add -Wno-unused-function after -Werror too.
CFLAGS_USERMOD += -I$(BINDINGS_DIR) -I$(LVMP_DIR) -Wno-unused-function
SRC_USERMOD_LIB_C += $(SOURCES)
SRC_USERMOD_C += $(LVMP_C)
