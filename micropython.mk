# This file is used by MicroPython Make-based builds such as the Unix port.
# For CMake-based builds, see the .cmake file in the same directory.

# When building Micropython, the parent directory of this module is given as:
#     make USER_C_MODULES=<path to workspace root>

LVMP_DIR := $(USERMOD_DIR)
BINDINGS_DIR ?= $(abspath $(LVMP_DIR)/../lvgl-bindings)
LVMP_C := $(BINDINGS_DIR)/generated/lvgl_micropython.c
LVGL_DIR := $(BINDINGS_DIR)/lvgl
SOURCES = $(shell find $(LVGL_DIR)/src -type f -name "*.c")
LV_BINDINGS_PIN := $(strip $(shell cat $(LVMP_DIR)/LVGL_BINDINGS_COMMIT 2>/dev/null))
LV_BINDINGS_DIRTY := $(shell \
	git -C $(BINDINGS_DIR) cat-file -e $(LV_BINDINGS_PIN)^{commit} 2>/dev/null && \
	git -C $(BINDINGS_DIR) diff --quiet $(LV_BINDINGS_PIN) -- generated/lvgl_micropython.c lvgl lv_conf.h && \
	git -C $(BINDINGS_DIR) diff --quiet -- generated/lvgl_micropython.c lvgl lv_conf.h || echo 1)

ifeq ($(LV_BINDINGS_PIN),)
$(error Missing $(LVMP_DIR)/LVGL_BINDINGS_COMMIT)
endif
ifneq ($(LV_BINDINGS_DIRTY),)
$(error $(BINDINGS_DIR) does not match pinned binding inputs $(LV_BINDINGS_PIN); check out that commit/tag or run scripts/sync_from_lvgl_bindings.sh with an exact ref)
endif

# LVGL is available on every port, but its desktop/host-GUI and OS-specific
# driver backends (OpenGL/SDL/GLFW/X11/Wayland/evdev/libinput/qnx/uefi/nuttx/
# windows) plus the OpenGLES draw unit need host libraries and break cross
# builds (e.g. lv_opengles_shader.c fails -Werror). This exclusion lives in the
# module's own config: only desktop ports (unix/webassembly/windows) keep the
# full source sweep; every other (embedded) port drops these backends.
LVMP_PORT_DIR := $(abspath $(CURDIR))
LVMP_IS_DESKTOP := $(findstring /ports/unix,$(LVMP_PORT_DIR))$(findstring /ports/webassembly,$(LVMP_PORT_DIR))$(findstring /ports/windows,$(LVMP_PORT_DIR))
ifeq ($(LVMP_IS_DESKTOP),)
LVMP_EXCLUDE_DIRS := \
    $(LVGL_DIR)/src/drivers/opengles \
    $(LVGL_DIR)/src/drivers/sdl \
    $(LVGL_DIR)/src/drivers/glfw \
    $(LVGL_DIR)/src/drivers/x11 \
    $(LVGL_DIR)/src/drivers/wayland \
    $(LVGL_DIR)/src/drivers/evdev \
    $(LVGL_DIR)/src/drivers/libinput \
    $(LVGL_DIR)/src/drivers/qnx \
    $(LVGL_DIR)/src/drivers/uefi \
    $(LVGL_DIR)/src/drivers/nuttx \
    $(LVGL_DIR)/src/drivers/windows \
    $(LVGL_DIR)/src/draw/opengles \
    $(LVGL_DIR)/src/libs/gltf
SOURCES := $(foreach s,$(SOURCES),$(if $(strip $(foreach d,$(LVMP_EXCLUDE_DIRS),$(findstring $(d)/,$(s)))),,$(s)))
endif

SOURCES += $(LVMP_DIR)/src/lv_mem_core_micropython.c

$(if $(wildcard $(LVMP_C)),,$(error $(LVMP_C) not found. Run $(BINDINGS_DIR)/regenerate_lvmp.sh after changing lvgl, lv_conf.h, or binding/))

# -Wno-unused-function here is not enough on ports that append -Werror after py.mk
# (e.g. webassembly); those ports add -Wno-unused-function after -Werror too.
CFLAGS_USERMOD += -I$(BINDINGS_DIR) -I$(LVMP_DIR) -Wno-unused-function
SRC_USERMOD_LIB_C += $(SOURCES)
SRC_USERMOD_C += $(LVMP_C)

# With LV_USE_FLOAT=1, upstream LVGL trips -Werror=double-promotion / float-conversion.
# Port Makefiles (unix/webassembly) append -Wdouble-promotion after CFLAGS_USERMOD,
# so put the suppress on the LVGL object rules (same idea as circuitpython.mk).
LVMP_FLOAT_CFLAGS := -Wno-double-promotion -Wno-float-conversion
$(foreach s,$(SOURCES),\
	$(eval $(BUILD)/$(patsubst $(USER_C_MODULES)/%,%,$(s:.c=.o)): CFLAGS += $(LVMP_FLOAT_CFLAGS)))
$(eval $(BUILD)/$(patsubst $(USER_C_MODULES)/%,%,$(LVMP_C:.c=.o)): CFLAGS += $(LVMP_FLOAT_CFLAGS))
$(eval $(BUILD)/$(patsubst $(USER_C_MODULES)/%,%,$(LVMP_DIR)/src/lv_mem_core_micropython.o): CFLAGS += $(LVMP_FLOAT_CFLAGS))
