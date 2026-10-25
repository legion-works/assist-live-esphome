// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "esp_timer.h"
#include <cassert>
inline void (*test_delay_hook)() = nullptr;
inline void vTaskDelay(int ticks) {
  assert(ticks == 10);
  test_time_us += ticks * 1000;
  if (test_delay_hook != nullptr)
    test_delay_hook();
}
inline bool fail_task = false;
inline void (*test_task_delete_hook)() = nullptr;
inline void vTaskDelete(void *) {
  if (test_task_delete_hook != nullptr)
    test_task_delete_hook();
}
inline int xTaskCreatePinnedToCore(void (*)(void *), const char *, int, void *,
                                   int priority, void *, int core) {
  assert(priority == 0 && core == 0);
  return fail_task ? 0 : 1;
}
