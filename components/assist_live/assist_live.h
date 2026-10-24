// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "esphome/core/component.h"

namespace esphome {
namespace assist_live {

class AssistLiveComponent : public Component {
 public:
  void setup() override;
  void dump_config() override;
};

}  // namespace assist_live
}  // namespace esphome
