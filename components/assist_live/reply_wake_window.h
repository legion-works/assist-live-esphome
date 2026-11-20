// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <string>

namespace esphome::assist_live {
class ReplyWakeWindow {
public:
  static constexpr uint32_t REPLY_TAIL_MS = 2000;
  static constexpr uint32_t REPLY_CHECK_MS = 25;
  void select(const std::string &option) {
    if (option == "Slightly sensitive")
      selected_ = 0;
    else if (option == "Moderately sensitive")
      selected_ = 1;
    else if (option == "Very sensitive")
      selected_ = 2;
    apply_("select changed");
  }

  bool observe(uint32_t now, bool announcing) {
    const bool started = announcing && !announcing_;
    announcing_ = announcing;
    if (started) {
      active_ = true;
      tail_ = false;
      apply_("reply window start");
    }
    if (active_ && !announcing_) {
      if (!tail_) {
        tail_ = true;
        idle_ms_ = now;
      }
      if (tail_ && static_cast<uint32_t>(now - idle_ms_) >= REPLY_TAIL_MS) {
        active_ = false;
        tail_ = false;
        apply_("reply window end");
      }
    }
    return started;
  }

  bool announcing() const { return announcing_; }
  bool active() const { return active_; }
  std::array<uint8_t, 3> cutoffs() const { return applied_; }
  const char *reason() const { return reason_; }
  bool take_change() {
    const bool changed = changed_;
    changed_ = false;
    return changed;
  }

protected:
  void apply_(const char *reason) {
    // The resolved-config test checks this table against the pinned stock select.
    static constexpr std::array<std::array<uint8_t, 3>, 3> CUTOFFS{{
        {217, 247, 253}, {176, 235, 242}, {143, 212, 237}}};
    const auto next = CUTOFFS[active_ ? 2 : selected_];
    if (next != applied_) {
      applied_ = next;
      reason_ = reason;
      changed_ = true;
    }
  }
  std::array<uint8_t, 3> applied_{};
  uint32_t idle_ms_{0};
  uint8_t selected_{0};
  bool active_{false}, announcing_{false}, tail_{false}, changed_{false};
  const char *reason_{"select changed"};
};
}
