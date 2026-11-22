// Host stand-in for the Renesas FSP timer: it only remembers the callback; the test calls the ISR itself.
#pragma once
#include <cstdint>

typedef struct { int unused; } timer_callback_args_t;
typedef void (*timer_cb_t)(timer_callback_args_t*);
enum { GPT_TIMER = 0, AGT_TIMER = 1 };
typedef enum { TIMER_MODE_PERIODIC = 0 } timer_mode_t;

class FspTimer {
 public:
  timer_cb_t cb = nullptr;
  float freq = 0;
  static int8_t get_available_timer(uint8_t&, bool = false) { return 0; }
  bool begin(timer_mode_t, uint8_t, uint8_t, float f, float, timer_cb_t c) { cb = c; freq = f; return true; }
  bool setup_overflow_irq() { return true; }
  bool open() { return true; }
  bool start() { return true; }
};
