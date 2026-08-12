# This file is used by MicroPython CMake-based builds such as the ESP32 and RP2 ports.
# For Make-based builds, see the .mk file in the same directory.

# Point USER_C_MODULES at this repo (or this file) directly, e.g.:
#     idf.py build -DUSER_C_MODULES=<path to lvgl-micropython>
# usermod.cmake also accepts a semicolon-separated list of module paths if you
# want this module plus others — no aggregator file required, e.g.:
#     -DUSER_C_MODULES="<path to lvgl-micropython>;<path to other_mod>"

set(LVMP_DIR ${CMAKE_CURRENT_LIST_DIR})
get_filename_component(WORKSPACE_DIR ${LVMP_DIR} DIRECTORY)
if(NOT DEFINED BINDINGS_DIR)
    set(BINDINGS_DIR ${WORKSPACE_DIR}/lvgl-bindings)
endif()
set(LVMP_C ${BINDINGS_DIR}/generated/lvgl_micropython.c)
set(LVGL_DIR ${BINDINGS_DIR}/lvgl)
file(GLOB_RECURSE SOURCES ${LVGL_DIR}/src/*.c)

# LVGL is available on every port, but its desktop/host-GUI and OS-specific
# driver backends plus the OpenGLES draw unit need host libraries and break the
# build. CMake ports here (esp32/rp2) are embedded, so drop those backends. This
# exclusion lives in the module's own config, not in the build tool.
list(FILTER SOURCES EXCLUDE REGEX "/src/drivers/(opengles|sdl|glfw|x11|wayland|evdev|libinput|qnx|uefi|nuttx|windows)/")
list(FILTER SOURCES EXCLUDE REGEX "/src/draw/opengles/")
list(APPEND SOURCES ${LVMP_DIR}/src/lv_mem_core_micropython.c)

if(NOT EXISTS ${LVMP_C})
    message(FATAL_ERROR "${LVMP_C} not found. Run ${BINDINGS_DIR}/regenerate_lvmp.sh after changing lvgl, lv_conf.h, or binding/")
endif()

add_library(lv_micropython INTERFACE)
target_sources(lv_micropython INTERFACE ${LVMP_C})
target_include_directories(lv_micropython INTERFACE ${BINDINGS_DIR} ${LVMP_DIR})
target_link_libraries(usermod INTERFACE lv_micropython)

add_library(lvgl INTERFACE)
target_sources(lvgl INTERFACE ${SOURCES})
# Match micropython.mk / CircuitPython: LV_USE_FLOAT upstream trips -Werror=float.
target_compile_options(lvgl INTERFACE
    -Wno-unused-function
    -Wno-double-promotion
    -Wno-float-conversion
)
target_link_libraries(lv_micropython INTERFACE lvgl)
