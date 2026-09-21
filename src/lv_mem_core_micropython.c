/**
 * @file lv_malloc_core.c
 */

/*********************
 *      INCLUDES
 *********************/
#include "lvgl/src/stdlib/lv_mem.h"
#if LV_USE_STDLIB_MALLOC == LV_STDLIB_MICROPYTHON_OVERRIDE
#include <py/mpconfig.h>
#include <py/misc.h>
#include <py/gc.h>
/*********************
 *      DEFINES
 *********************/

/**********************
 *      TYPEDEFS
 **********************/

/**********************
 *  STATIC PROTOTYPES
 **********************/

/**********************
 *  STATIC VARIABLES
 **********************/

/**********************
 *      MACROS
 **********************/

/**********************
 *   GLOBAL FUNCTIONS
 **********************/

void lv_mem_init(void)
{
    return; /*Nothing to init*/
}

void lv_mem_deinit(void)
{
    return; /*Nothing to deinit*/

}

lv_mem_pool_t lv_mem_add_pool(void * mem, size_t bytes)
{
    /*Not supported*/
    LV_UNUSED(mem);
    LV_UNUSED(bytes);
    return NULL;
}

void lv_mem_remove_pool(lv_mem_pool_t pool)
{
    /*Not supported*/
    LV_UNUSED(pool);
    return;
}

void * lv_malloc_core(size_t size)
{
#if MICROPY_MALLOC_USES_ALLOCATED_SIZE
    // 0, not true: gc_alloc()'s second argument is alloc_flags, and 1 is
    // GC_ALLOC_FLAG_HAS_FINALISER. An LVGL struct is not an mp_obj_base_t, so
    // flagging it made gc_sweep_run_finalisers read its first word as a type
    // pointer and call mp_load_method_maybe() on whatever that happened to be
    // -- SIGBUS in gc.collect() after an lv.deinit()/lv.init() cycle, once a
    // block freed in the first lifetime came back with a different first word
    // (PyDevices/lvgl-micropython#10).
    return gc_alloc(size, 0);
#else
    return m_malloc(size);
#endif
}

void * lv_realloc_core(void * p, size_t new_size)
{

#if MICROPY_MALLOC_USES_ALLOCATED_SIZE
    // true here is gc_realloc()'s allow_move, which is what we want -- unlike
    // the flags argument to gc_alloc() above, it is not a finaliser bit.
    return gc_realloc(p, new_size, true);
#else
    return m_realloc(p, new_size);
#endif
}

void lv_free_core(void * p)
{

#if MICROPY_MALLOC_USES_ALLOCATED_SIZE
    gc_free(p);

#else
    m_free(p);
#endif
}

void lv_mem_monitor_core(lv_mem_monitor_t * mon_p)
{
    /*Not supported*/
    LV_UNUSED(mon_p);
    return;
}

lv_result_t lv_mem_test_core(void)
{
    /*Not supported*/
    return LV_RESULT_OK;
}

/**********************
 *   STATIC FUNCTIONS
 **********************/

#endif /*LV_STDLIB_MICROPYTHON*/