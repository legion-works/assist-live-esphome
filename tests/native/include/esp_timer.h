// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
inline int64_t test_time_us = 123456789000;
inline int64_t esp_timer_get_time() { return test_time_us; }
