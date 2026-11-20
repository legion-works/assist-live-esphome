// SPDX-License-Identifier: GPL-3.0-or-later
#include <cassert>
#include <iostream>
#include <string>
#if __has_include("reply_wake_window.h")
#include "reply_wake_window.h"
using esphome::assist_live::ReplyWakeWindow;

int main(int argc, char **argv) {
  assert(argc == 2);
  const std::string scenario = argv[1];
  ReplyWakeWindow window;
  auto cutoff = [&]() { return window.cutoffs()[0]; };
  if (scenario == "mapping") {
    for (const auto *option : {"Slightly sensitive", "Moderately sensitive", "Very sensitive"}) {
      window.select(option);
      const auto values = window.cutoffs();
      std::cout << unsigned(values[0]) << ' ' << unsigned(values[1]) << ' ' << unsigned(values[2]) << '\n';
    }
    return 0;
  }
  window.select("Moderately sensitive");
  assert(cutoff() == 176);
  window.take_change();
  window.observe(100, true, true);
  assert(cutoff() == 143 && "announcement must start reply window");
  if (scenario == "window_start_end") {
    window.observe(500, false, true);
    window.observe(2000, false, true);
    assert(cutoff() == 143 && "wait for VA idle after playback");
    window.observe(2100, false, false);
    window.observe(4100, false, false);
    assert(cutoff() == 176 && "restore selected cutoff after window");
  } else if (scenario == "tail_2000_ms") {
    window.observe(500, false, false);
    assert(cutoff() == 143 && "reply end must not end window");
    window.observe(2499, false, false);
    assert(cutoff() == 143 && "tail must last 2000 ms");
    window.observe(2500, false, false);
    assert(cutoff() == 176 && "2000 ms boundary restores selected cutoff");
  } else if (scenario == "select_inside_window") {
    window.select("Slightly sensitive");
    assert(cutoff() == 143 && "select must not override active reply window");
    window.observe(500, false, false);
    window.select("Very sensitive");
    window.select("Slightly sensitive");
    assert(cutoff() == 143 && "select must not override tail");
    window.observe(2500, false, false);
    assert(cutoff() == 217 && "restore latest selected option, not a fixed cutoff");
  } else if (scenario == "very_selected") {
    window.select("Very sensitive");
    window.take_change();
    window.observe(500, false, false);
    window.observe(2500, false, false);
    assert(cutoff() == 143 && !window.take_change() && "Very selection needs no cutoff changes");
  } else if (scenario == "mute_during_window") {
    // Mute has no input to this policy. The stock microphone and handler apply it.
    window.observe(500, false, true);
    window.observe(600, false, false);
    window.observe(2600, false, false);
    assert(cutoff() == 176 && "mute must not prevent restoration");
  } else if (scenario == "follow_up_listening") {
    window.observe(500, false, true);
    window.listening(501);
    window.observe(2500, false, true);
    assert(cutoff() == 143);
    window.observe(2501, false, true);
    assert(cutoff() == 176 && "follow-up listening must not hold previous reply window");
  } else if (scenario == "announcement") {
    window.observe(200, true, false);
    window.observe(500, false, false);
    window.observe(2500, false, false);
    assert(cutoff() == 176 && "standalone announcement restores without VA turn");
  } else if (scenario == "overlapping_reply") {
    window.observe(500, false, false);
    window.observe(1400, true, true);
    window.observe(1500, true, true);
    assert(cutoff() == 143);
    window.observe(2000, false, false);
    window.observe(3999, false, false);
    assert(cutoff() == 143 && "new reply must replace previous tail");
    window.observe(4000, false, false);
    assert(cutoff() == 176);
  } else if (scenario == "clock_wrap") {
    window.observe(0xffffff00, false, false);
    window.observe(1743, false, false);
    assert(cutoff() == 143);
    window.observe(1744, false, false);
    assert(cutoff() == 176 && "tail survives millis wrap");
  } else if (scenario == "change_reasons") {
    assert(window.take_change());
    assert(std::string(window.reason()) == "reply window start");
    assert(!window.take_change());
    window.observe(500, false, false);
    window.observe(2500, false, false);
    assert(window.take_change() && std::string(window.reason()) == "reply window end");
    window.select("Slightly sensitive");
    assert(window.take_change() && std::string(window.reason()) == "select changed");
    window.select("Slightly sensitive");
    assert(!window.take_change());
  } else if (scenario == "stuck_va_timeout") {
    window.observe(500, false, true);
    window.select("Slightly sensitive");
    window.expire_wait();
    assert(cutoff() == 217 && "bounded idle wait restores selected cutoff");
    assert(std::string(window.reason()) == "reply window end");
    window.observe(31000, false, true);
    assert(cutoff() == 217 && "stuck VA must not reopen reply window");
  } else {
    assert(false && "unknown scenario");
  }
  std::cout << "PASS " << scenario << '\n';
}
#else
int main() {
  std::cerr << "missing reply window policy\n";
  return 1;
}
#endif
