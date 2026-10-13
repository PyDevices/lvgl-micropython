# This file is used by MicroPython CMake-based builds such as the ESP32 and RP2 ports.
# For Make-based builds, see the .mk file in the same directory.

# Point USER_C_MODULES at this repo (or this file) directly, e.g.:
#     idf.py build -DUSER_C_MODULES=<path to lvgl-micropython>
# usermod.cmake also accepts a semicolon-separated list of module paths if you
# want this module plus others, e.g.:
#     -DUSER_C_MODULES="<path to lvgl-micropython>;<path to other_mod>"

set(LVMP_DIR ${CMAKE_CURRENT_LIST_DIR})
get_filename_component(WORKSPACE_DIR ${LVMP_DIR} DIRECTORY)
# Where lvgl-bindings comes from, first match wins:
#   1. BINDINGS_DIR, as a CMake variable or in the environment (a firmware
#      build that pins lvgl-bindings itself sets it);
#   2. an lvgl-bindings checkout beside this one;
#   3. the commit in LVGL_BINDINGS_COMMIT, fetched into .deps/ with only what
#      this module compiles (a clone on its own).
# The first two build the checkout as it is: if it isn't at the pinned commit,
# the build says so and carries on. Only the fetched copy must match the pin.
if(NOT DEFINED BINDINGS_DIR AND NOT "$ENV{BINDINGS_DIR}" STREQUAL "")
    set(BINDINGS_DIR $ENV{BINDINGS_DIR})
endif()
if(DEFINED BINDINGS_DIR)
    get_filename_component(BINDINGS_DIR ${BINDINGS_DIR} ABSOLUTE)
    set(LVMP_BINDINGS_FROM "BINDINGS_DIR")
    if(NOT EXISTS ${BINDINGS_DIR}/lv_conf.h)
        message(FATAL_ERROR "lvgl-micropython: BINDINGS_DIR=${BINDINGS_DIR} is not an lvgl-bindings checkout (no lv_conf.h)")
    endif()
elseif(EXISTS ${WORKSPACE_DIR}/lvgl-bindings/lv_conf.h)
    set(BINDINGS_DIR ${WORKSPACE_DIR}/lvgl-bindings)
    set(LVMP_BINDINGS_FROM "the lvgl-bindings beside lvgl-micropython")
else()
    set(BINDINGS_DIR ${LVMP_DIR}/.deps/lvgl-bindings)
    set(LVMP_BINDINGS_FROM "pin")
    execute_process(COMMAND bash ${LVMP_DIR}/scripts/fetch_bindings.sh RESULT_VARIABLE _lvmp_fetch_rc)
    if(NOT EXISTS ${BINDINGS_DIR}/lv_conf.h)
        message(FATAL_ERROR "lvgl-micropython: fetching lvgl-bindings failed (scripts/fetch_bindings.sh exit ${_lvmp_fetch_rc}); set BINDINGS_DIR to an lvgl-bindings checkout")
    endif()
endif()
set(LVMP_C ${BINDINGS_DIR}/generated/lvgl_micropython.c)
set(LVGL_DIR ${BINDINGS_DIR}/lvgl)
file(GLOB_RECURSE SOURCES ${LVGL_DIR}/src/*.c)

file(STRINGS ${LVMP_DIR}/LVGL_BINDINGS_COMMIT LV_BINDINGS_PIN LIMIT_COUNT 1)
execute_process(
    COMMAND git -C ${BINDINGS_DIR} cat-file -e ${LV_BINDINGS_PIN}^{commit}
    RESULT_VARIABLE LV_BINDINGS_HAS_PIN
    OUTPUT_QUIET ERROR_QUIET
)
set(LV_BINDINGS_COMMITTED_DIFF 1)
set(LV_BINDINGS_WORKTREE_DIFF 1)
if(LV_BINDINGS_HAS_PIN EQUAL 0)
    execute_process(
        COMMAND git -C ${BINDINGS_DIR} diff --quiet ${LV_BINDINGS_PIN} -- generated/lvgl_micropython.c lvgl lv_conf.h
        RESULT_VARIABLE LV_BINDINGS_COMMITTED_DIFF
    )
    execute_process(
        COMMAND git -C ${BINDINGS_DIR} diff --quiet -- generated/lvgl_micropython.c lvgl lv_conf.h
        RESULT_VARIABLE LV_BINDINGS_WORKTREE_DIFF
    )
endif()
if(NOT LV_BINDINGS_COMMITTED_DIFF EQUAL 0 OR NOT LV_BINDINGS_WORKTREE_DIFF EQUAL 0)
    if(LVMP_BINDINGS_FROM STREQUAL "pin")
        message(FATAL_ERROR "${BINDINGS_DIR} does not match pinned binding inputs ${LV_BINDINGS_PIN}; delete it and build again to refetch")
    endif()
    execute_process(
        COMMAND git -C ${BINDINGS_DIR} describe --always --dirty --abbrev=12
        OUTPUT_VARIABLE LV_BINDINGS_HEAD
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET)
    if(NOT LV_BINDINGS_HEAD)
        set(LV_BINDINGS_HEAD "not a git checkout")
    endif()
    message(NOTICE
        "lvgl-micropython: note: building lvgl-bindings from ${BINDINGS_DIR} "
        "(${LVMP_BINDINGS_FROM}) at ${LV_BINDINGS_HEAD}, whose generated binding, "
        "lvgl or lv_conf.h differ from LVGL_BINDINGS_COMMIT ${LV_BINDINGS_PIN}. "
        "Building it as it is.")
endif()

# LVGL is available on every port, but its desktop/host-GUI and OS-specific
# driver backends plus the OpenGLES draw unit need host libraries and break the
# build. CMake ports here (esp32/rp2) are embedded, so drop those backends. This
# exclusion lives in the module's own config, not in the build tool.
list(FILTER SOURCES EXCLUDE REGEX "/src/drivers/(opengles|sdl|glfw|x11|wayland|evdev|libinput|qnx|uefi|nuttx|windows)/")
list(FILTER SOURCES EXCLUDE REGEX "/src/draw/opengles/")
list(APPEND SOURCES ${LVMP_DIR}/src/lv_mem_core_micropython.c)

if(NOT EXISTS ${LVMP_C})
    message(FATAL_ERROR "${LVMP_C} not found. Sync an exact lvgl-bindings commit or release tag")
endif()

# jpegio Phase 2 moved the JPEG decoder out of LVGL: LV_USE_TJPGD is 0 in the
# bindings (lvgl-bindings aa6c6bc), and the jpegio module registers its own
# TJpgDec with LVGL instead, so a firmware carries one decoder rather than two.
# Built without jpegio (micropython-pydevices' modules/jpegio since 2026-10-06;
# displayif's before), this module decodes PNG and LVGL's BIN and draws nothing
# at all for a JPEG -- silently, at run time. Say so at build time instead (#11).
if(NOT "${USER_C_MODULES}" MATCHES "jpegio")
    message(NOTICE
        "lvgl-micropython: no jpegio in this build -- lv.image will not draw "
        "a JPEG. jpegio owns the TJpgDec decoder; PNG and LVGL BIN still "
        "decode. Name jpegio as well for JPEG (build_mp.py --modules "
        "jpegio,lvgl-micropython).")
endif()

add_library(lv_micropython INTERFACE)
target_sources(lv_micropython INTERFACE ${LVMP_C} ${LVMP_DIR}/src/lvgl_micropython_build.c)

# --- which lvmp this firmware was built from ----------------------
# Computed at build time from this repo's own git, never stored; "unknown" when
# there is no git (a tarball). Read on a target as <module>.__revision__.
execute_process(
    COMMAND git -C ${LVMP_DIR} describe --always --dirty --abbrev=7
    OUTPUT_VARIABLE LVMP_REVISION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET)
if(NOT LVMP_REVISION)
    set(LVMP_REVISION "unknown")
endif()
target_compile_definitions(lv_micropython INTERFACE LVMP_REVISION=\"${LVMP_REVISION}\")
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
