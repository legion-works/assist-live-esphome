// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
namespace esphome {
template <typename... Ts> class Action {
public:
  virtual void play(const Ts &...x) = 0;
};
template <typename T> struct TestTemplateValue {
  template <typename... Ts> T value(Ts...) { return T{}; }
};
} // namespace esphome
#define TEMPLATABLE_VALUE(type, name) esphome::TestTemplateValue<type> name##_;
