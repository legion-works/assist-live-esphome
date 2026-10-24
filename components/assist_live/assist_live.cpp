// SPDX-License-Identifier: GPL-3.0-or-later
#include "assist_live.h"

#include "esphome/core/log.h"

namespace esphome {
namespace assist_live {

static const char *const TAG = "assist_live";

void AssistLiveComponent::setup() {}

void AssistLiveComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "Assist Live: placeholder component (no runtime functions)");
}

}  // namespace assist_live
}  // namespace esphome
