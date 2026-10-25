// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdio>
#define ESP_LOGCONFIG(tag, ...)                                                \
  do {                                                                         \
    std::printf("%s: ", tag);                                                  \
    std::printf(__VA_ARGS__);                                                  \
    std::puts("");                                                             \
  } while (false)
