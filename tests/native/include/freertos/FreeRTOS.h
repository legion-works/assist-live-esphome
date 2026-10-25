// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
using BaseType_t = int;
constexpr int pdPASS = 1, pdTRUE = 1, portMAX_DELAY = 0x7fffffff;
inline int pdMS_TO_TICKS(int milliseconds) { return milliseconds; }
