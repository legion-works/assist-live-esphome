// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
inline bool fail_task = false;
inline int xTaskCreatePinnedToCore(void (*)(void *), const char *, int, void *,
                                   int priority, void *, int core) {
  assert(priority == 0 && core == 0);
  return fail_task ? 0 : 1;
}
