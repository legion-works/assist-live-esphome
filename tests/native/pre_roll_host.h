// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <mutex>
#include <memory>
#include <cstring>
#include <vector>

namespace esphome {
template<typename T> T clamp(T value, T low, T high) { return std::min(high, std::max(low, value)); }
namespace setup_priority { constexpr float AFTER_WIFI = 200; }
class Component {
public:
  virtual void setup() {}
  virtual void loop() {}
  virtual void dump_config() {}
  virtual void on_shutdown() {}
  virtual bool teardown() { return true; }
  virtual float get_setup_priority() const { return 0; }
  void mark_failed() { failed = true; }
  bool failed{false};
};
using Mutex = std::mutex;
using LockGuard = std::lock_guard<Mutex>;
class HighFrequencyLoopRequester {
public:
  void start() {}
  void stop() {}
};
template <typename Signature> class CallbackManager;
template <typename... Args> class CallbackManager<void(Args...)> {
public:
  template <typename F> void add(F callback) { callbacks_.emplace_back(callback); }
  void call(Args... args) { for (auto &callback : callbacks_) callback(args...); }
private:
  std::vector<std::function<void(Args...)>> callbacks_;
};
template <typename T> class RAMAllocator {
public:
  T *allocate(size_t count) { return static_cast<T *>(std::malloc(count * sizeof(T))); }
};
namespace audio {
class AudioStreamInfo {
public:
  AudioStreamInfo(uint8_t bits = 16, uint8_t channels = 1, uint32_t rate = 16000)
      : bits_(bits), channels_(channels), rate_(rate) {}
  bool operator!=(const AudioStreamInfo &other) const {
    return bits_ != other.bits_ || channels_ != other.channels_ || rate_ != other.rate_;
  }
  uint32_t get_sample_rate() const { return rate_; }
  uint8_t get_channels() const { return channels_; }
  size_t samples_to_bytes(size_t samples) const { return samples * bits_ / 8; }
  size_t frames_to_bytes(size_t frames) const { return samples_to_bytes(frames) * channels_; }
  size_t bytes_to_frames(size_t bytes) const { return bytes / frames_to_bytes(1); }
private:
  uint8_t bits_, channels_;
  uint32_t rate_;
};
inline int32_t unpack_audio_sample_to_q31(const uint8_t *data, size_t size) {
  int32_t value = 0;
  std::memcpy(&value, data, size);
  return value;
}
inline void pack_q31_as_audio_sample(int32_t value, uint8_t *data, size_t size) {
  std::memcpy(data, &value, size);
}
}
namespace switch_ { class Switch { public: bool state{false}; }; }
namespace api { class APIConnection { public: bool try_to_clear_buffer(bool) { return true; } }; }
namespace voice_assistant {
class VoiceAssistant {
public:
  api::APIConnection *get_api_connection() { return &connection_; }
  bool is_running() const { return running; }
  bool running{false};
private:
  api::APIConnection connection_;
};
inline VoiceAssistant *global_voice_assistant = nullptr;
}
}
