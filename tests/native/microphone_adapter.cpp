// SPDX-License-Identifier: GPL-3.0-or-later
#include "pre_roll_microphone.cpp"
#include "esp_timer.h"
#include <cassert>
#include <iostream>
#include <atomic>
#include <climits>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <type_traits>
#include "esphome/components/microphone/microphone_source.h"

static bool count_allocations = false;
static size_t allocations = 0;
void *operator new(std::size_t size) {
  if (count_allocations)
    ++allocations;
  if (void *memory = std::malloc(size))
    return memory;
  throw std::bad_alloc();
}
void operator delete(void *memory) noexcept { std::free(memory); }
void operator delete(void *memory, std::size_t) noexcept { std::free(memory); }
void *operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void *memory) noexcept { ::operator delete(memory); }
void operator delete[](void *memory, std::size_t) noexcept { ::operator delete(memory); }

using namespace esphome;
using namespace esphome::assist_live;
static void set_time(uint64_t now) { test_time_us = now * 1000; }
static void advance_time(uint64_t elapsed) { test_time_us += elapsed * 1000; }

class TimingComponent : public AssistLiveComponent {
public:
  Event take() {
    Event event{};
    assert(!queue_->items.empty() && "each logical turn emits its own timing event");
    xQueueReceive(queue_, &event, 0);
    return event;
  }
  bool empty() const { return queue_->items.empty(); }
};

class PhysicalMicrophone : public microphone::Microphone {
public:
  PhysicalMicrophone() { audio_stream_info_ = audio::AudioStreamInfo(32, 2, 16000); }
  void start() override { state_ = microphone::STATE_RUNNING; }
  void stop() override { state_ = microphone::STATE_STOPPED; }
  void send(const std::vector<uint8_t> &data) { data_callbacks_.call(data); }
};
class TestMicrophone : public PreRollMicrophone {
public:
  size_t historical_frames() const { return buffer_->history_remaining(); }
  size_t queued_frames() const { return buffer_->pending(); }
  unsigned listeners() const { return listeners_; }
  uint64_t detection_ms() const { return buffer_->detection_ms(); }
  size_t trimmed_frames() const { return buffer_->trimmed_frames(); }
};

template<typename T, typename = void> struct HasTurnHooks : std::false_type {};
template<typename T> struct HasTurnHooks<T, std::void_t<decltype(std::declval<T>().wake_started()),
    decltype(std::declval<T>().finish_turn()), decltype(std::declval<T>().finish_turn_if_idle())>> : std::true_type {};

template<typename T> static void retained_source_lifecycle() {
  if constexpr (!HasTurnHooks<T>::value) {
    assert(false && "logical turn hooks are required for retained sources");
  } else {
    std::cout << "BEGIN retained-source lifecycle\n";
    PhysicalMicrophone physical;
    switch_::Switch wake_sound;
    TimingComponent parent;
    voice_assistant::VoiceAssistant va;
    voice_assistant::global_voice_assistant = &va;
    T mic;
    mic.set_source(&physical);
    mic.set_wake_sound(&wake_sound);
    mic.set_parent(&parent);
    mic.set_length_ms(16);
    mic.setup();
    parent.set_pre_roll(&mic);
    parent.setup();
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
    sensor::Sensor history_sensor, gate_sensor, sent_sensor, expired_sensor;
    binary_sensor::BinarySensor passthrough_sensor, connected_sensor;
    parent.set_turn_sensor(PRE_ROLL_MS, &history_sensor);
    parent.set_turn_sensor(REPLAY_GATE_DELAY_MS, &gate_sensor);
    parent.set_counter_sensor(EVENTS_SENT, &sent_sensor);
    parent.set_counter_sensor(EXPIRED_GATES, &expired_sensor);
    parent.set_passthrough_sensor(&passthrough_sensor);
    parent.set_connected_sensor(&connected_sensor);
    auto publish = [&]() {
      test_publish_allowed = true;
      parent.loop();
      test_publish_allowed = false;
    };
    publish();
    assert(history_sensor.states.empty() && "no turn entity before a completed turn");
#endif
    microphone::MicrophoneSource left(&mic, 32, 1, false), right(&mic, 32, 1, false);
    left.add_channel(0);
    right.add_channel(1);
    std::vector<int32_t> received_left, received_right;
    auto collect = [](std::vector<int32_t> &out, const std::vector<uint8_t> &data) {
      for (size_t i = 0; i < data.size(); i += sizeof(int32_t)) {
        int32_t value;
        std::memcpy(&value, data.data() + i, sizeof(value));
        out.push_back(value);
      }
    };
    left.add_data_callback([&](const auto &data) { collect(received_left, data); });
    right.add_data_callback([&](const auto &data) { collect(received_right, data); });
    auto feed = [&](int first) {
      std::vector<uint8_t> data(256 * sizeof(StereoFrame));
      for (int i = 0; i < 256; ++i) {
        StereoFrame frame{(first + i) * 64, -(first + i) * 64};
        std::memcpy(data.data() + i * sizeof(frame), &frame, sizeof(frame));
      }
      physical.send(data);
    };
    auto wake = [&]() {
      mic.wake_detected();
      va.running = true;
      mic.wake_started();
      left.start();
      right.start();
    };
    for (int turn = 0; turn < 2; ++turn) {
      va.running = false;
      feed(turn * 1000);
      received_left.clear();
      received_right.clear();
      set_time(10000 + turn * 2000);
      wake();
      parent.command_stream_start();
      if (turn == 1) {
        advance_time(1);
        parent.command_stream_end();
        mic.finish_turn_if_idle();
        parent.command_stream_start();
      }
      feed(turn * 1000 + 256);
      mic.loop();
      assert(received_left.empty() && received_right.empty() && "nothing delivered before STT replay gate");
      assert(parent.empty() && "mic_open waits for actual history replay");
      advance_time(20);
      mic.listening();
      feed(turn * 1000 + 512);
      for (int block = 0; block < 3; ++block) {
        mic.loop();
        advance_time(8);
      }
      assert(received_left.size() == 768 && received_right.size() == 768 && "history bridge live have no duplicates");
      for (int i = 0; i < 768; ++i) {
        assert(received_left[i] == (turn * 1000 + i) * 64 && "history head precedes bridge and live");
        assert(received_right[i] == -received_left[i] && "both VA channels preserve ordering");
      }
      assert(mic.pre_roll_ms() == 32 && "each retained-source turn measures fresh history");
      auto event = parent.take();
      assert(event.seq == static_cast<uint64_t>(turn) && event.stage == Stage::MIC_OPEN &&
             event.device_ms == static_cast<uint64_t>(10000 + turn * 2000) &&
             std::string(event.data).find("\"pre_roll_ms\":32") != std::string::npos &&
             "delayed on_end cannot reassign the next turn timing event");
      assert(parent.empty() && "exactly one mic_open per logical turn");
      if (turn == 0) {
        mic.set_privacy_mute(true);
        assert(mic.pre_roll_ms() == 32 && "mute preserves history already sent this turn");
        mic.set_privacy_mute(false);
      }
      mic.finish_turn();
      mic.finish_turn();
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
      assert(history_sensor.states.size() == static_cast<size_t>(turn) && "finish snapshots without publishing");
      publish();
      publish();
      assert(history_sensor.states.size() == static_cast<size_t>(turn + 1) &&
             history_sensor.states.back() == 32 && "one fresh entity snapshot per completed turn");
      assert(gate_sensor.states.back() == (turn == 0 ? 20 : 21) && "replay gate entity has turn-local delay");
#endif
      assert(mic.queued_frames() == 0 && "turn end discards residual queue");
      assert(mic.listeners() == 2 && "logical finish preserves stock source pairing");
    }
    feed(3000);
    assert(received_left.back() == 3255 * 64 && "inter-turn live frames have no queue delay");
    received_left.clear();
    received_right.clear();
    parent.command_stream_start();
    mic.begin_turn();
    mic.listening();
    assert(mic.pre_roll_ms() == 0 && "unarmed follow-up has no stale history");
    auto followup = parent.take();
    assert(std::string(followup.data).find("\"pre_roll_ms\":0") != std::string::npos &&
           "follow-up timing event reports zero history");
    feed(4000);
    assert(received_left.front() == 4000 * 64 && "follow-up passes live audio directly");
    mic.finish_turn();
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
    publish();
    assert(history_sensor.states.back() == 0 && "follow-up entity reports zero history");
    const auto counter_updates = sent_sensor.states.size();
    publish();
    assert(sent_sensor.states.size() == counter_updates && "counter entities rate limit same-millisecond loops");
    advance_time(1000);
    publish();
    assert(sent_sensor.states.size() == counter_updates && "unchanged counter entities stay silent at one-second boundary");
#endif
    va.running = false;
    feed(5000);
    advance_time(100);
    wake();
    advance_time(20);
    mic.listening();
    feed(5256);
    assert(mic.queued_frames() != 0 && "abnormal turn has queued audio to discard");
    va.running = false;
    left.stop();
    right.stop();
    mic.finish_turn_if_idle();
    assert(mic.listeners() == 0 && mic.queued_frames() == 0 && "abnormal source stop closes turn once");
    voice_assistant::global_voice_assistant = nullptr;
    std::cout << "PASS retained-source lifecycle\n";
  }
}

static void muted_receive_does_not_allocate() {
  PhysicalMicrophone physical;
  switch_::Switch wake_sound;
  AssistLiveComponent parent;
  TestMicrophone microphone;
  microphone.set_source(&physical);
  microphone.set_wake_sound(&wake_sound);
  microphone.set_parent(&parent);
  microphone.setup();
  assert(!microphone.failed);
  microphone.start();
  microphone.set_privacy_mute(true);
  size_t sent = 0;
  microphone.add_data_callback([&](const std::vector<uint8_t> &data) {
    assert(data.size() <= 2048 && "silence handoff is at most 256 stereo frames");
    for (uint8_t byte : data)
      assert(byte == 0 && "muted handoff contains only silence");
    sent += data.size();
  });
  std::vector<uint8_t> input(4096, 0x5a);
  for (size_t size : {size_t{8}, size_t{1000}, size_t{2048}, size_t{4096}}) {
    input.resize(size);
    size_t before = allocations, sent_before = sent;
    count_allocations = true;
    physical.send(input);
    count_allocations = false;
    assert(allocations == before && "muted real receive path allocates nothing");
    assert(sent - sent_before == size && "silence chunking preserves every byte");
  }
  microphone.stop();
}

static void start_eligibility_is_bounded_and_chime_cannot_arm() {
  PhysicalMicrophone physical;
  switch_::Switch wake_sound;
  AssistLiveComponent parent;
  voice_assistant::VoiceAssistant va;
  voice_assistant::global_voice_assistant = &va;
  TestMicrophone microphone;
  microphone.set_source(&physical);
  microphone.set_wake_sound(&wake_sound);
  microphone.set_parent(&parent);
  microphone.setup();
  std::vector<uint8_t> input(4096, 0x5a);
  physical.send(input);
  set_time(1000);
  microphone.wake_detected();
  va.running = true;
  microphone.wake_started();
  microphone.start();
  set_time(2000);
  microphone.listening();
  assert(microphone.historical_frames() == 512 && "1000 ms gate remains eligible");
  microphone.stop();
  physical.send(input);
  set_time(3000);
  va.running = false;
  microphone.wake_detected();
  va.running = true;
  microphone.wake_started();
  microphone.start();
  set_time(4001);
  microphone.loop();
  physical.send(input);
  assert(microphone.queued_frames() == 0 && "expired gate drops retained PCM before listening");
  assert(!microphone.history_complete() && "expired gate cannot complete mic_open before STT");
  microphone.listening();
  assert(microphone.historical_frames() == 0 && "1001 ms gate fails closed to no history");
  microphone.stop();
  physical.send(input);
  set_time(5000);
  va.running = false;
  wake_sound.state = true;
  microphone.wake_detected();
  set_time(5010);
  wake_sound.state = false;
  va.running = true;
  microphone.wake_started();
  microphone.start();
  microphone.listening();
  assert(microphone.historical_frames() == 0 && "wake sound on never creates an arm");
  microphone.stop();
  va.running = false;
  physical.send(input);
  microphone.wake_detected();
  microphone.wake_started();
  assert(!microphone.turn_active() && microphone.queued_frames() == 0 &&
         "failed wake request cannot retain an armed turn");
  physical.send(input);
  microphone.wake_detected();
  va.running = true;
  microphone.start();
  microphone.begin_turn();
  microphone.listening();
  assert(microphone.pre_roll_ms() == 0 && microphone.historical_frames() == 0 &&
         "unpaired button start cannot consume a wake arm");
  microphone.stop();
  physical.send(input);
  microphone.wake_detected();
  microphone.wake_started();
  assert(!microphone.turn_active() && "running VA cannot accept delayed wake history");
  voice_assistant::global_voice_assistant = nullptr;
}

#ifdef USE_ASSIST_LIVE_PRE_ROLL_BUFFER_FEEDBACK
static void feedback_drain_model(int drain_mode) {
  PhysicalMicrophone physical;
  switch_::Switch wake_sound;
  AssistLiveComponent parent;
  voice_assistant::VoiceAssistant va;
  voice_assistant::global_voice_assistant = &va;
  TestMicrophone mic;
  mic.set_source(&physical);
  mic.set_wake_sound(&wake_sound);
  mic.set_parent(&parent);
  mic.set_length_ms(512);
  mic.setup();
  std::vector<int32_t> received;
  size_t used = 0;
  mic.add_data_callback([&](const auto &data) {
    used += data.size() / 4;
    assert(used <= 8192 && "feedback preserves 256 ms per-channel reserve");
    for (size_t offset = 0; offset < data.size(); offset += sizeof(StereoFrame)) {
      StereoFrame frame;
      std::memcpy(&frame, data.data() + offset, sizeof(frame));
      assert(frame.right == -frame.left && "feedback stereo alignment");
      received.push_back(frame.left);
    }
  });
  int next = 0;
  auto feed = [&](size_t count) {
    std::vector<uint8_t> data(count * sizeof(StereoFrame));
    for (size_t i = 0; i < count; ++i) {
      StereoFrame frame{next, -next};
      ++next;
      std::memcpy(data.data() + i * sizeof(frame), &frame, sizeof(frame));
    }
    const auto reads = va.free_reads;
    va.in_audio_callback = true;
    physical.send(data);
    va.in_audio_callback = false;
    assert(va.free_reads == reads && "audio callback never reads buffer feedback");
  };
  feed(8192);
  set_time(1000);
  mic.wake_detected();
  va.running = true;
  mic.wake_started();
  mic.start();
  mic.listening();
  int passthrough_at = -1;
  size_t stalled_sent = 0;
  for (int elapsed = 0; elapsed < 1400; ++elapsed) {
    if (drain_mode == 0 || (drain_mode == 2 && elapsed >= 400))
      used = 0;
    else if (drain_mode == 1)
      used -= std::min(used, size_t{32});
    if (elapsed != 0)
      feed(16);
    va.free_bytes = 16384 - used;
    set_time(1000 + elapsed);
    const auto reads = va.free_reads;
    mic.loop();
    assert(va.free_reads - reads <= 1 && "one free-space read per main-loop block decision");
    if (passthrough_at < 0) {
      assert(received.size() <= static_cast<size_t>(elapsed / 8 + 1) * 256 &&
             "feedback replay is limited to twice real time");
      if (mic.queued_frames() == 0)
        passthrough_at = elapsed;
    }
    if (drain_mode == 2 && elapsed == 200)
      stalled_sent = received.size();
    if (drain_mode == 2 && elapsed == 399)
      assert(received.size() == stalled_sent && stalled_sent == 4096 &&
             "zero drain stops admission at the reserve without loss");
  }
  assert(va.free_reads != 0 && "enabled option uses actual buffer feedback");
  std::cout << "feedback model=" << drain_mode << " passthrough_ms=" << passthrough_at
            << " sent=" << received.size() << " queued=" << mic.queued_frames() << std::endl;
  if (drain_mode == 0)
    assert(passthrough_at >= 496 && passthrough_at <= 520 &&
           "ideal drain catches up in one history length instead of fallback credit");
  if (drain_mode == 2)
    assert(passthrough_at >= 400 && "stalled replay resumes to pass-through");
  assert(received.size() + mic.queued_frames() == static_cast<size_t>(next) &&
         "feedback retains every captured sample");
  for (size_t i = 0; i < received.size(); ++i)
    assert(received[i] == static_cast<int32_t>(i) && "feedback resumes without gaps or duplicates");
  mic.stop();
  voice_assistant::global_voice_assistant = nullptr;
}
#endif

template<typename T, typename = void> struct HasReplyWake : std::false_type {};
template<typename T> struct HasReplyWake<T, std::void_t<decltype(std::declval<T>().capture_reply_wake()),
    decltype(std::declval<T>().reply_wake_ready())>> : std::true_type {};

template<typename T> static void reply_wake_history(int history_ms) {
  if constexpr (!HasReplyWake<T>::value) {
    assert(false && "reply wake must retain history across stop and idle");
  } else {
    PhysicalMicrophone physical;
    switch_::Switch wake_sound;
    TimingComponent parent;
    voice_assistant::VoiceAssistant va;
    voice_assistant::global_voice_assistant = &va;
    T mic;
    mic.set_source(&physical);
    mic.set_wake_sound(&wake_sound);
    mic.set_parent(&parent);
    mic.set_length_ms(history_ms);
    mic.setup();
    parent.set_pre_roll(&mic);
    parent.setup();
    mic.start();
    va.running = true;
    std::vector<StereoFrame> received;
    mic.add_data_callback([&](const auto &data) {
      const auto first = received.size();
      received.resize(first + data.size() / sizeof(StereoFrame));
      std::memcpy(received.data() + first, data.data(), data.size());
    });
    auto feed = [&](int first, int count = 256) {
      std::vector<uint8_t> data(count * sizeof(StereoFrame));
      for (int i = 0; i < count; ++i) {
        StereoFrame frame{first + i, -first - i};
        std::memcpy(data.data() + i * sizeof(frame), &frame, sizeof(frame));
      }
      physical.send(data);
    };
    const int lookback = history_ms * 16;
    feed(0, lookback);
    received.clear();
    set_time(100);
    parent.emit_event(Stage::WAKE_DETECTED, 100);
    mic.capture_reply_wake();
    assert(!mic.reply_wake_ready() && "busy VA cannot consume pending history");
    feed(lookback, 2400);
    mic.stop();
    feed(lookback + 2400, 2400);
    assert(received.empty() && "stop wait must not send command audio to the old turn");
    set_time(400);
    va.running = false;
    mic.finish_turn_if_idle();
    assert(mic.reply_wake_ready() && "idle VA can consume pending reply wake");
    mic.wake_detected();
    assert(mic.detection_ms() == 100 && "reply wake keeps original detection time at pre-start arm");
    va.running = true;
    mic.wake_started();
    mic.start();
    mic.begin_turn();
    parent.command_stream_start();
    feed(lookback + 4800);
    set_time(416);
    mic.listening();
    const int history_frames = lookback + 5056;
    feed(history_frames);
    const int trimmed = std::max(0, history_frames - 16000);
    const int output_frames = history_frames - trimmed + 256;
    for (int i = 0; i < 300 && mic.queued_frames() != 0; ++i) {
      mic.loop();
      advance_time(8);
    }
    assert(received.size() == static_cast<size_t>(output_frames) && "reply turn keeps lookback, stop bridge, start bridge and live audio");
    for (int i = 0; i < output_frames; ++i)
      assert(received[i].left == i + trimmed && received[i].right == -i - trimmed && "reply wake has no missing or duplicate frame");
    assert(mic.pre_roll_ms() == static_cast<uint32_t>((history_frames - trimmed) / 16) &&
           "reply wake history includes the 300 ms stop-to-start bridge");
    assert(mic.trimmed_frames() == static_cast<size_t>(trimmed) && "reply wake counts oldest-end trim at 1000 ms cap");
    const auto detection = parent.take();
    assert(detection.stage == Stage::WAKE_DETECTED && detection.device_ms == 100);
    const auto opened = parent.take();
    assert(opened.stage == Stage::MIC_OPEN && opened.device_ms == 400);
    mic.finish_turn();
    va.running = true;
    feed(2000);
    mic.capture_reply_wake();
    mic.set_privacy_mute(true);
    va.running = false;
    assert(!mic.reply_wake_ready() && "mute cancels pending reply history");
    mic.set_privacy_mute(false);
    assert(!mic.reply_wake_ready() && "unmute cannot revive pending reply history");
    va.running = true;
    mic.capture_reply_wake();
    mic.clear();
    va.running = false;
    assert(!mic.reply_wake_ready() && "error or disconnect cancels pending reply history");
    voice_assistant::global_voice_assistant = nullptr;
    std::cout << "PASS reply wake history\n";
  }
}

static void allocation_failure_passes_audio_through() {
  PhysicalMicrophone physical;
  switch_::Switch wake_sound;
  TimingComponent parent;
  voice_assistant::VoiceAssistant va;
  voice_assistant::global_voice_assistant = &va;
  PreRollMicrophone mic;
  mic.set_source(&physical);
  mic.set_wake_sound(&wake_sound);
  mic.set_parent(&parent);
  test_allocation_fails = true;
  mic.setup();
  test_allocation_fails = false;
  assert(!mic.failed && "a failed component gets no loop and VA waits for is_running without a limit");
  parent.set_pre_roll(&mic);
  parent.setup();
  microphone::MicrophoneSource left(&mic, 32, 1, false), right(&mic, 32, 1, false);
  left.add_channel(0);
  right.add_channel(1);
  std::vector<int32_t> received_left, received_right;
  auto collect = [](std::vector<int32_t> &out, const std::vector<uint8_t> &data) {
    for (size_t i = 0; i < data.size(); i += sizeof(int32_t)) {
      int32_t value;
      std::memcpy(&value, data.data() + i, sizeof(value));
      out.push_back(value);
    }
  };
  left.add_data_callback([&](const auto &data) { collect(received_left, data); });
  right.add_data_callback([&](const auto &data) { collect(received_right, data); });
  auto feed = [&](int first) {
    std::vector<uint8_t> data(256 * sizeof(StereoFrame));
    for (int i = 0; i < 256; ++i) {
      StereoFrame frame{(first + i) * 64, -(first + i) * 64};
      std::memcpy(data.data() + i * sizeof(frame), &frame, sizeof(frame));
    }
    physical.send(data);
  };
  for (int turn = 0; turn < 2; ++turn) {
    received_left.clear();
    received_right.clear();
    va.running = false;
    set_time(1000 + turn * 1000);
    mic.wake_detected();
    va.running = true;
    mic.wake_started();
    left.start();
    right.start();
    assert(physical.is_running() && "start reaches the physical microphone without a history buffer");
    mic.loop();
    assert(mic.is_running() && "VA leaves STARTING_MICROPHONE without a history buffer");
    parent.command_stream_start();
    mic.begin_turn();
    mic.listening();
    feed(turn * 1000 + 1);
    assert(received_left.size() == 256 && received_right.size() == 256 && "live audio passes straight through");
    for (int i = 0; i < 256; ++i)
      assert(received_left[i] == (turn * 1000 + 1 + i) * 64 && received_right[i] == -received_left[i]);
    assert(mic.pre_roll_ms() == 0 && "a turn without a buffer has no history");
    const auto event = parent.take();
    assert(event.stage == Stage::MIC_OPEN && std::string(event.data).find("\"pre_roll_ms\":0") != std::string::npos);
    mic.set_privacy_mute(true);
    feed(turn * 1000 + 300);
    for (size_t i = 256; i < received_left.size(); ++i)
      assert(received_left[i] == 0 && "privacy mute sends silence also without a buffer");
    mic.set_privacy_mute(false);
    mic.finish_turn();
    va.running = false;
    parent.command_stream_end();
    mic.finish_turn_if_idle();
    left.stop();
    right.stop();
    mic.loop();
    assert(!physical.is_running() && !mic.is_running() && "stop reaches the physical microphone");
  }
  assert(mic.passthrough_starts() == 2 && "each start without a buffer is counted");
  voice_assistant::global_voice_assistant = nullptr;
  std::cout << "PASS allocation failure pass-through\n";
}

// A reply restart with the wake sound on gets no history, so the history age limit must not block it.
static void reply_wake_chime_after_history_limit(bool wake_sound_on) {
  PhysicalMicrophone physical;
  switch_::Switch wake_sound;
  TimingComponent parent;
  voice_assistant::VoiceAssistant va;
  voice_assistant::global_voice_assistant = &va;
  TestMicrophone mic;
  mic.set_source(&physical);
  mic.set_wake_sound(&wake_sound);
  mic.set_parent(&parent);
  mic.setup();
  parent.set_pre_roll(&mic);
  parent.setup();
  wake_sound.state = wake_sound_on;
  mic.start();
  std::vector<uint8_t> input(256 * sizeof(StereoFrame), 0x11);
  physical.send(input);
  va.running = true;
  set_time(100);
  mic.capture_reply_wake();
  mic.stop();
  // Idle after 480 ms of the 500 ms stop wait.
  set_time(580);
  va.running = false;
  mic.finish_turn_if_idle();
  assert(mic.reply_wake_ready() && "first check inside the history limit");
  // The 300 ms chime delay plus a 250 ms main-loop stall puts the second check at 1030 ms after detection.
  set_time(1130);
  if (!wake_sound_on) {
    assert(!mic.reply_wake_ready() && "a history turn keeps the 1000 ms detection-to-start limit");
    mic.clear();
    voice_assistant::global_voice_assistant = nullptr;
    std::cout << "PASS reply wake chime limit sound=0\n";
    return;
  }
  assert(mic.reply_wake_ready() && "wake sound on: the age limit cannot cancel a turn without history");
  mic.wake_detected();
  va.running = true;
  mic.wake_started();
  mic.start();
  parent.command_stream_start();
  mic.begin_turn();
  mic.listening();
  assert(mic.pre_roll_ms() == 0 && mic.historical_frames() == 0 && "wake sound turn has no history");
  mic.finish_turn();
  mic.stop();
  voice_assistant::global_voice_assistant = nullptr;
  std::cout << "PASS reply wake chime limit sound=1\n";
}

// The I2S task calls receive_ while the main loop runs the turn hooks.
// A ThreadSanitizer build of this scenario finds a hook that does not take the shared mutex.
static void concurrent_receive_and_hooks() {
  PhysicalMicrophone physical;
  switch_::Switch wake_sound;
  TimingComponent parent;
  voice_assistant::VoiceAssistant va;
  voice_assistant::global_voice_assistant = &va;
  TestMicrophone mic;
  mic.set_source(&physical);
  mic.set_wake_sound(&wake_sound);
  mic.set_parent(&parent);
  mic.set_length_ms(16);
  mic.setup();
  parent.set_pre_roll(&mic);
  parent.setup();
  constexpr int32_t MARKER = INT32_MIN;
  std::mutex received_mutex;
  std::vector<int32_t> received;
  // The sources start before the capture thread, because upstream MicrophoneSource
  // changes its enabled flag outside the microphone lock.
  microphone::MicrophoneSource left(&mic, 32, 1, false), right(&mic, 32, 1, false);
  left.add_channel(0);
  right.add_channel(1);
  std::vector<int32_t> right_values;
  left.add_data_callback([&](const std::vector<uint8_t> &data) {
    std::lock_guard<std::mutex> lock(received_mutex);
    for (size_t i = 0; i < data.size(); i += sizeof(int32_t)) {
      int32_t value;
      std::memcpy(&value, data.data() + i, sizeof(value));
      received.push_back(value);
    }
  });
  right.add_data_callback([&](const std::vector<uint8_t> &data) {
    std::lock_guard<std::mutex> lock(received_mutex);
    for (size_t i = 0; i < data.size(); i += sizeof(int32_t)) {
      int32_t value;
      std::memcpy(&value, data.data() + i, sizeof(value));
      right_values.push_back(value);
    }
  });
  left.start();
  right.start();
  auto marker = [&]() {
    std::lock_guard<std::mutex> lock(received_mutex);
    received.push_back(MARKER);
    right_values.push_back(MARKER);
  };
  std::atomic<bool> done{false}, hooks_started{false};
  constexpr int BLOCKS = 3000;
  std::thread capture([&]() {
    while (!hooks_started)
      std::this_thread::yield();
    std::vector<uint8_t> data(256 * sizeof(StereoFrame));
    for (int block = 0; block < BLOCKS; ++block) {
      for (int i = 0; i < 256; ++i) {
        const int32_t value = (block * 256 + i + 1) * 64;
        StereoFrame frame{value, -value};
        std::memcpy(data.data() + i * sizeof(frame), &frame, sizeof(frame));
      }
      physical.send(data);
      std::this_thread::yield();
    }
    done = true;
  });
  uint64_t now = 1000;
  int cycle = 0;
  hooks_started = true;
  while (!done || cycle < 8) {
    set_time(now);
    va.running = false;
    mic.loop();
    switch (cycle++ % 4) {
      case 0:
        mic.wake_detected();
        va.running = true;
        mic.wake_started();
        break;
      case 1:
        va.running = true;
        mic.begin_turn();
        break;
      case 2:
        va.running = true;
        mic.capture_reply_wake();
        mic.reply_wake_ready();
        va.running = false;
        mic.reply_wake_ready();
        mic.wake_detected();
        va.running = true;
        mic.wake_started();
        break;
      default:
        mic.set_privacy_mute(true);
        mic.set_privacy_mute(false);
        mic.wake_detected();
        break;
    }
    marker();
    parent.command_stream_start();
    now += 20;
    set_time(now);
    mic.listening();
    for (int i = 0; i < 4; ++i) {
      mic.loop();
      now += 8;
      set_time(now);
    }
    if (cycle % 3 == 0)
      mic.set_privacy_mute(true);
    mic.history_complete();
    mic.pre_roll_ms();
    mic.set_privacy_mute(false);
    if (cycle % 2 == 0)
      mic.clear();
    else
      mic.finish_turn();
    mic.finish_turn_if_idle();
    marker();
    std::this_thread::yield();
  }
  capture.join();
  left.stop();
  right.stop();
  // A marker can fall between the two channel callbacks of one block, so compare the channels without markers.
  auto without_markers = [&](const std::vector<int32_t> &values) {
    std::vector<int32_t> result;
    for (int32_t value : values)
      if (value != MARKER)
        result.push_back(value);
    return result;
  };
  const auto left_values = without_markers(received), right_only = without_markers(right_values);
  assert(left_values.size() == right_only.size() && "both channels get each block");
  for (size_t i = 0; i < left_values.size(); ++i)
    assert(right_only[i] == -left_values[i] && "channels stay aligned under concurrent capture");
  int32_t last = 0;
  size_t samples = 0;
  for (int32_t value : received) {
    if (value == MARKER) {
      last = 0;
      continue;
    }
    if (value == 0)
      continue;
    assert(value > last && "no duplicate or reordered frame inside one segment");
    last = value;
    ++samples;
  }
  assert(samples != 0 && "audio and hooks ran at the same time");
  voice_assistant::global_voice_assistant = nullptr;
  std::cout << "PASS concurrent receive cycles=" << cycle << "\n";
}

int main(int argc, char **argv) {
  if (argc == 2 && std::string(argv[1]) == "concurrent") {
    concurrent_receive_and_hooks();
    return 0;
  }
  allocation_failure_passes_audio_through();
  reply_wake_chime_after_history_limit(true);
  reply_wake_chime_after_history_limit(false);
  concurrent_receive_and_hooks();
  reply_wake_history<TestMicrophone>(16);
  reply_wake_history<TestMicrophone>(900);
#ifdef USE_ASSIST_LIVE_PRE_ROLL_BUFFER_FEEDBACK
  feedback_drain_model(0);
  feedback_drain_model(1);
  feedback_drain_model(2);
  std::cout << "PASS feedback drain models\n";
#endif
  retained_source_lifecycle<TestMicrophone>();
  muted_receive_does_not_allocate();
  start_eligibility_is_bounded_and_chime_cannot_arm();
  std::cout << "PASS microphone adapter\n";
}
