// SPDX-License-Identifier: GPL-3.0-or-later
#include "pre_roll_microphone.cpp"
#include <cassert>
#include <iostream>
#include <new>

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
static uint64_t now_ms = 0;
uint64_t AssistLiveComponent::monotonic_ms() { return now_ms; }
void AssistLiveComponent::pre_roll_complete() {}
void AssistLiveComponent::setup() {}
void AssistLiveComponent::dump_config() {}
void AssistLiveComponent::on_shutdown() {}

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
};

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
  TestMicrophone microphone;
  microphone.set_source(&physical);
  microphone.set_wake_sound(&wake_sound);
  microphone.set_parent(&parent);
  microphone.setup();
  std::vector<uint8_t> input(4096, 0x5a);
  physical.send(input);
  now_ms = 1000;
  microphone.wake_detected();
  now_ms = 1032;
  microphone.start();
  assert(microphone.historical_frames() == 512 && "32 ms arm remains eligible");
  microphone.stop();
  physical.send(input);
  now_ms = 2000;
  microphone.wake_detected();
  now_ms = 2033;
  microphone.start();
  assert(microphone.historical_frames() == 0 && "33 ms arm fails closed to no history");
  microphone.stop();
  physical.send(input);
  now_ms = 3000;
  wake_sound.state = true;
  microphone.wake_detected();
  now_ms = 3010;
  wake_sound.state = false;
  microphone.start();
  assert(microphone.historical_frames() == 0 && "wake sound on never creates an arm");
  microphone.stop();
}

int main() {
  muted_receive_does_not_allocate();
  start_eligibility_is_bounded_and_chime_cannot_arm();
  std::cout << "PASS microphone adapter\n";
}
