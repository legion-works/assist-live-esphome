// SPDX-License-Identifier: GPL-3.0-or-later
#include "pre_roll_buffer.h"
#include <cassert>
#include <iostream>
#include <vector>

using namespace esphome::assist_live;

static void feed(PreRollBuffer &buffer, int first, int count) {
  for (int i = first; i < first + count; ++i) {
    StereoFrame frame{i, -i};
    buffer.push(&frame, 1);
  }
}

static void ring_wrap_snapshot_and_splice() {
  StereoFrame memory[1100]{};
  PreRollBuffer buffer(memory, 100, 1100, 1000);
  feed(buffer, 0, 1500);
  buffer.arm(1500);
  feed(buffer, 1500, 32);
  buffer.start(1532, false);
  buffer.listen();
  feed(buffer, 1532, 32);
  std::vector<StereoFrame> result;
  StereoFrame out[16];
  for (uint64_t now = 1532; buffer.pending(); now += 8) {
    auto count = buffer.pop(now, true, out, 16);
    result.insert(result.end(), out, out + count);
  }
  assert(result.size() == 164 && "snapshot includes detection-to-start bridge");
  for (size_t i = 0; i < result.size(); ++i) {
    assert(result[i].left == 1400 + static_cast<int>(i) && "left splice continuity");
    assert(result[i].right == -result[i].left && "stereo frame alignment");
  }
  assert(buffer.history_sent() == 132 && buffer.live_sent() == 32);
  assert(buffer.pre_roll_ms() == 132 && "mic_open reports actual history");
  assert(buffer.dropped_frames() == 0);
  assert(buffer.passthrough() && "catch-up reaches live pass-through");
  assert(buffer.history_end_queue_ms() == 20 && "history-end delay is captured at the splice");
  assert(buffer.first_live_queue_ms() == 20 && "first-live delay is captured at handoff");
  assert(buffer.queue_delay_ms() == 0 && buffer.passthrough_reached());
}

static void eligibility_and_mute() {
  StereoFrame memory[1100]{};
  PreRollBuffer buffer(memory, 100, 1100, 1000);
  StereoFrame out[16];
  for (bool sound : {false, true}) {
    buffer.stop();
    feed(buffer, 0, 100);
    if (sound)
      buffer.arm(100);
    buffer.start(100, sound);
    buffer.listen();
    assert(buffer.pop(100, true, out, 16) == 0 && "button and chime have no history");
    assert(buffer.pre_roll_ms() == 0);
  }
  buffer.stop();
  feed(buffer, 0, 100);
  buffer.arm(100);
  buffer.mute(true);
  feed(buffer, 100, 100);
  assert(buffer.pending() == 0 && "mute clears and prevents retention");
  for (const auto &frame : memory)
    assert(frame.left == 0 && frame.right == 0 && "mute wipes PCM RAM");
  buffer.mute(false);
  buffer.start(200, false);
  buffer.listen();
  assert(buffer.pop(200, true, out, 16) == 0 && "unmute cannot replay stale history");
  buffer.stop();
  feed(buffer, 0, 100);
  buffer.arm(100);
  buffer.start(2000, false);
  assert(buffer.pending() == 0 && "stale wake arm expires");
}

static void readiness_and_counted_overflow() {
  StereoFrame memory[1100]{};
  PreRollBuffer buffer(memory, 100, 1100, 1000);
  feed(buffer, 0, 100);
  buffer.arm(100);
  buffer.start(100, false);
  buffer.listen();
  StereoFrame out[16];
  for (int now = 100; now < 1300; now += 16) {
    feed(buffer, now, 16);
    assert(buffer.pop(now, false, out, 16) == 0 && "full consumer gets no writes");
  }
  assert(buffer.handed_frames() == 0);
  assert(buffer.dropped_frames() > 0 && "queue overflow is counted");
  assert(buffer.dropped_history() == 100 && "dropped history reduces event length");
  assert(buffer.pre_roll_ms() == 0);
  auto count = buffer.pop(1300, true, out, 16);
  assert(count == 16 && out[0].right == -out[0].left);
}

static void pacing_and_readiness_toggle() {
  StereoFrame memory[2000]{};
  PreRollBuffer buffer(memory, 1000, 2000, 1000);
  feed(buffer, 0, 1000);
  buffer.arm(1000);
  buffer.start(1000, false);
  buffer.listen();
  StereoFrame out[16];
  int expected = 0;
  for (uint64_t now = 1000; now < 4000; ++now) {
    if ((now - 1000) % 16 == 0)
      feed(buffer, static_cast<int>(now), 16);
    auto count = buffer.pop(now, now % 7 != 0, out, 16);
    assert(count <= 16 && "one output block is at most 16 ms");
    assert(buffer.handed_frames() <= now - 1000 + 256 && "extra VA backlog is at most 256 ms");
    for (size_t i = 0; i < count; ++i, ++expected)
      assert(out[i].left == expected && out[i].right == -expected && "toggle continuity");
  }
  assert(buffer.dropped_frames() == 0);
  assert(buffer.history_sent() == 1000 && "all maximum history survives pacing");
  buffer.stop();
  feed(buffer, 0, 1000);
  buffer.arm(5000);
  buffer.start(5000, false);
  buffer.listen();
  for (uint64_t now = 5000; now < 7000; now += 16) {
    feed(buffer, static_cast<int>(now - 4000), 16);
    assert(buffer.pop(now, true, out, 16) == 16 && "1x consumer stays continuous");
  }
  assert(buffer.dropped_frames() == 0 && buffer.pending() == 1000);
}

static void total_history_includes_bridge_and_has_one_second_limit() {
  StereoFrame memory[2000]{};
  PreRollBuffer buffer(memory, 1000, 2000, 1000);
  feed(buffer, 0, 1000);
  buffer.arm(1000);
  feed(buffer, 1000, 200);
  buffer.start(1200, false);
  buffer.listen();
  feed(buffer, 1200, 16);
  StereoFrame out[16];
  std::vector<StereoFrame> result;
  for (uint64_t now = 1200; buffer.pending(); now += 8) {
    auto count = buffer.pop(now, true, out, 16);
    result.insert(result.end(), out, out + count);
  }
  assert(result.size() == 1016 && "total history including bridge is capped at 1000 ms");
  for (size_t i = 0; i < result.size(); ++i)
    assert(result[i].left == 200 + static_cast<int>(i) && result[i].right == -result[i].left && "trim keeps the newest continuous history and live frames");
  assert(buffer.pre_roll_ms() == 1000);
  assert(buffer.trimmed_frames() == 200 && "oldest history trim is counted");
}

int main() {
  ring_wrap_snapshot_and_splice();
  eligibility_and_mute();
  readiness_and_counted_overflow();
  pacing_and_readiness_toggle();
  total_history_includes_bridge_and_has_one_second_limit();
  std::cout << "PASS pre-roll\n";
}
