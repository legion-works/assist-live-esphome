// SPDX-License-Identifier: GPL-3.0-or-later
#include "pre_roll_microphone.cpp"
#include "esp_timer.h"
#include <cassert>
#include <iostream>
#include <new>
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

int main() {
  retained_source_lifecycle<TestMicrophone>();
  muted_receive_does_not_allocate();
  start_eligibility_is_bounded_and_chime_cannot_arm();
  std::cout << "PASS microphone adapter\n";
}
