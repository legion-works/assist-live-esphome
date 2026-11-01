// SPDX-License-Identifier: GPL-3.0-or-later
#if __has_include("diagnostic_state.h")
#include "diagnostic_state.h"
#include "diagnostic_publisher.h"
#include <cassert>
#include <cmath>
#include <iostream>
using namespace esphome::assist_live;

int main() {
  DiagnosticState state;
  TurnDiagnostics turn;
  assert(!state.take_turn(turn) && "no fabricated turn before stop");
  assert(state.counters_due(0) && "initial counter snapshot");
  assert(!state.counters_due(999) && "counter publication limited to one second");
  assert(state.counters_due(1000) && "counter boundary is inclusive");
  assert(!state.counters_due(1000) && "no duplicate counter publication");
  StereoFrame memory[64]{};
  PreRollBuffer buffer(memory, 16, 64, 1000);
  StereoFrame input[16]{};
  buffer.push(input, 16);
  buffer.arm(100);
  buffer.start(110, false);
  buffer.listen();
  buffer.push(input, 16);
  StereoFrame output[16]{};
  buffer.pop(110, true, output, 16);
  buffer.pop(118, true, output, 16);
  state.finish_turn(buffer, 10, false);
  buffer.stop();
  buffer.start(200, true);
  assert(state.take_turn(turn) && "turn survives buffer clear and next start");
  assert(turn.values[PRE_ROLL_MS] == 16 && "snapshot counts history sent");
  assert(turn.values[REPLAY_GATE_DELAY_MS] == 10 && "snapshot preserves replay gate delay");
  assert(turn.values[HISTORY_END_QUEUE_MS] == 16 && "history end queue snapshot");
  assert(turn.values[FIRST_LIVE_QUEUE_MS] == 0 && "first live queue snapshot");
  assert(turn.values[TURN_END_QUEUE_MS] == 0 && "turn end queue snapshot");
  assert(turn.passthrough && "pass-through snapshot");
  assert(!state.take_turn(turn) && "one publication per completed turn");
  state.finish_turn(buffer, 33, true);
  assert(state.take_turn(turn));
  assert(turn.expired_gates == 1 && "expired gate increments once");
  assert(std::isnan(turn.values[FIRST_LIVE_QUEUE_MS]) && "unreached first live is unknown");
  assert(!turn.passthrough && "pass-through resets each turn");
  state.finish_turn(buffer, 0, false);
  assert(state.take_turn(turn));
  assert(turn.expired_gates == 1 && "expired gate counter persists");
  state.finish_turn(buffer, 34, true);
  assert(state.take_turn(turn));
  assert(turn.expired_gates == 2 && "expired gate counter accumulates");
  state.finish_turn(buffer, 0, false, false);
  assert(state.take_turn(turn));
  assert(turn.values[PRE_ROLL_MS] == 0 && std::isnan(turn.values[REPLAY_GATE_DELAY_MS]) &&
         "unreached replay gate is unknown and history is zero");
  StereoFrame large_memory[20000]{};
  PreRollBuffer measured(large_memory, 17000, 20000);
  for (int i = 0; i < 17000; ++i)
    measured.push(input, 1);
  measured.arm(1);
  measured.start(2, false);
  state.finish_turn(measured, 1, false);
  assert(state.take_turn(turn));
  assert(turn.values[HISTORY_TRIMMED_MS] == 62 && "trimmed frames convert to whole milliseconds");
  for (int i = 0; i < 10000; ++i)
    measured.push(input, 1);
  state.finish_turn(measured, 1, false);
  assert(state.take_turn(turn));
  assert(turn.values[OVERFLOWS] == 24 && turn.values[DROPPED_MS] == 384 &&
         turn.values[TURN_END_QUEUE_MS] == 1241 && "overflow snapshot uses measured counters and queue");
  DiagnosticPublisher publisher;
  std::array<esphome::sensor::Sensor, COUNTER_SENSOR_COUNT> counters;
  for (size_t i = 0; i < COUNTER_SENSOR_COUNT; ++i)
    publisher.set_counter_sensor(i, &counters[i]);
  esphome::binary_sensor::BinarySensor connected;
  publisher.set_connected(&connected);
  test_publish_allowed = true;
  publisher.publish_turn(turn);
  publisher.loop(0, {11, 7, 3, 2, 1, 99}, true);
  assert(counters[EVENTS_SENT].states.back() == 11 && counters[EVENTS_CONFIRMED].states.back() == 7 &&
         counters[EVENTS_DROPPED].states.back() == 3 && counters[EVENTS_REFUSED].states.back() == 2 &&
         counters[SENDER_INITIALIZATION_FAILURES].states.back() == 1 && counters[EXPIRED_GATES].states.back() == 2 &&
         "counter entities preserve distinct measured values");
  publisher.loop(999, {12, 8, 4, 3, 2, 99}, false);
  assert(connected.states.size() == 1 && counters[EVENTS_SENT].states.size() == 1 &&
         "counter and connectivity entities limited to once per second");
  publisher.loop(1000, {12, 8, 4, 3, 2, 99}, false);
  assert(!connected.states.back() && counters[EVENTS_SENT].states.back() == 12 &&
         "counter and connectivity entities refresh on boundary");
  test_publish_allowed = false;
  std::cout << "PASS diagnostics\n";
}
#else
#include <iostream>
int main() {
  std::cerr << "FAIL missing diagnostic snapshot and publish schedule\n";
  return 1;
}
#endif
