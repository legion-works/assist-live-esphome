// SPDX-License-Identifier: GPL-3.0-or-later
#include "pre_roll_microphone.h"
#ifdef USE_ASSIST_LIVE_PRE_ROLL
#include "assist_live.h"
#include "esphome/components/api/api_connection.h"
#include "esphome/components/voice_assistant/voice_assistant.h"
#include "esphome/core/log.h"
#include <cinttypes>

namespace esphome::assist_live {
static const char *const TAG = "assist_live.pre_roll";

void PreRollMicrophone::setup() {
  audio_stream_info_ = source_->get_audio_stream_info();
  if (audio_stream_info_ != audio::AudioStreamInfo(32, 2, 16000)) {
    ESP_LOGE(TAG, "Pre-roll requires 16 kHz, 32-bit stereo PCM");
    mark_failed();
    return;
  }
  capacity_ = (length_ms_ + 1000) * 16;
  RAMAllocator<StereoFrame> allocator;
  memory_ = allocator.allocate(capacity_);
  if (memory_ == nullptr) {
    ESP_LOGE(TAG, "Pre-roll PCM allocation failed");
    mark_failed();
    return;
  }
  std::memset(memory_, 0, capacity_ * sizeof(StereoFrame));
  buffer_.reset(new PreRollBuffer(memory_, length_ms_ * 16, capacity_));
  output_.reserve(256 * sizeof(StereoFrame));
  silence_.resize(256 * sizeof(StereoFrame), 0);
  source_->add_data_callback([this](const std::vector<uint8_t> &data) { receive_(data); });
}

void PreRollMicrophone::update_mute_() {
  const bool muted = privacy_mute_ || source_->get_mute_state();
  if (muted == effective_mute_)
    return;
  effective_mute_ = muted;
  buffer_->mute(muted);
  if (muted)
    arm_pending_ = false;
  if (listeners_ != 0)
    passthrough_ = true;
}

void PreRollMicrophone::receive_(const std::vector<uint8_t> &data) {
  LockGuard lock(mutex_);
  if (!buffer_)
    return;
  update_mute_();
  if (listeners_ != 0 && (passthrough_ || effective_mute_)) {
    buffer_->account_passthrough(data.size() / sizeof(StereoFrame));
    if (effective_mute_) {
      // Reuse the setup allocation, also when a source supplies a larger block.
      constexpr size_t SILENCE_BYTES = 256 * sizeof(StereoFrame);
      for (size_t offset = 0; offset < data.size(); offset += SILENCE_BYTES) {
        silence_.resize(std::min(SILENCE_BYTES, data.size() - offset));
        data_callbacks_.call(silence_);
      }
    } else {
      data_callbacks_.call(data);
    }
    return;
  }
  if (data.size() % sizeof(StereoFrame) != 0) {
    // The stock I2S source delivers whole stereo frames.
    return;
  }
  // memcpy does not require the physical byte vector to have int32 alignment.
  for (size_t offset = 0; offset < data.size(); offset += sizeof(StereoFrame)) {
    StereoFrame frame;
    std::memcpy(&frame, data.data() + offset, sizeof(frame));
    buffer_->push(&frame, 1);
  }
}

void PreRollMicrophone::wake_detected() {
  LockGuard lock(mutex_);
  if (!buffer_)
    return;
  update_mute_();
  if (listeners_ != 0 || effective_mute_ || wake_sound_->state)
    return;
  arm_ms_ = AssistLiveComponent::monotonic_ms();
  arm_pending_ = true;
  buffer_->arm(arm_ms_);
  ESP_LOGD(TAG, "Wake detection device_ms=%" PRIu64, buffer_->detection_ms());
}

void PreRollMicrophone::start() {
  LockGuard lock(mutex_);
  if (!buffer_ || listeners_++ != 0)
    return;
  update_mute_();
  const uint64_t now = AssistLiveComponent::monotonic_ms();
  arm_to_start_ms_ = arm_pending_ ? now - arm_ms_ : 0;
  arm_expired_ = arm_pending_ && arm_to_start_ms_ > MAX_ARM_TO_START_MS;
  buffer_->start(now, wake_sound_->state || !arm_pending_ || arm_expired_);
  arm_pending_ = false;
  passthrough_ = false;
  reported_overflows_ = 0;
  source_->start();
  state_ = microphone::STATE_STARTING;
  fast_loop_.start();
  ESP_LOGD(TAG, "VA microphone start device_ms=%" PRIu64, buffer_->start_ms());
  if (buffer_->trimmed_frames() != 0)
    ESP_LOGD(TAG, "History trimmed_ms=%u (1000 ms total limit)",
             static_cast<unsigned>(buffer_->trimmed_frames() / 16));
}

void PreRollMicrophone::listening() {
  LockGuard lock(mutex_);
  if (buffer_ && listeners_ != 0)
    buffer_->listen();
}

void PreRollMicrophone::loop() {
  auto *va = voice_assistant::global_voice_assistant;
  auto *connection = va == nullptr ? nullptr : va->get_api_connection();
  const bool ready = connection != nullptr && connection->try_to_clear_buffer(false);
  bool complete = false;
  {
    LockGuard lock(mutex_);
    if (!buffer_)
      return;
    update_mute_();
    if (listeners_ != 0 && source_->is_running())
      state_ = microphone::STATE_RUNNING;
    StereoFrame frames[256];
    const auto count = buffer_->pop(AssistLiveComponent::monotonic_ms(), ready, frames, 256);
    if (count != 0) {
      output_.resize(count * sizeof(StereoFrame));
      std::memcpy(output_.data(), frames, output_.size());
      // Output and capture share the mutex to keep the pass-through splice ordered.
      data_callbacks_.call(output_);
      passthrough_ = buffer_->passthrough();
    }
    if (passthrough_)
      fast_loop_.stop();
    if (buffer_->overflows() != reported_overflows_) {
      reported_overflows_ = buffer_->overflows();
      ESP_LOGW(TAG, "Pre-roll overflow count=%u dropped_ms=%u dropped_history_ms=%u",
               static_cast<unsigned>(reported_overflows_),
               static_cast<unsigned>(buffer_->dropped_frames() / 16),
               static_cast<unsigned>(buffer_->dropped_history() / 16));
    }
    complete = buffer_->history_remaining() == 0;
  }
  if (complete)
    parent_->pre_roll_complete();
}

void PreRollMicrophone::log_turn_() {
  ESP_LOGD(TAG, "Turn wake_ms=%" PRIu64 " va_start_ms=%" PRIu64
           " history_samples=%u live_samples=%u overflow_count=%u dropped_ms=%u trimmed_ms=%u",
           buffer_->detection_ms(), buffer_->start_ms(),
           static_cast<unsigned>(buffer_->history_sent()),
           static_cast<unsigned>(buffer_->live_sent()),
           static_cast<unsigned>(buffer_->overflows()),
           static_cast<unsigned>(buffer_->dropped_frames() / 16),
           static_cast<unsigned>(buffer_->trimmed_frames() / 16));
  ESP_LOGD(TAG, "Turn queue first_live_ms=%" PRId32 " history_end_ms=%" PRId32
           " turn_end_ms=%u passthrough_reached=%u",
           buffer_->first_live_queue_ms(), buffer_->history_end_queue_ms(),
           static_cast<unsigned>(buffer_->queue_delay_ms()),
           static_cast<unsigned>(buffer_->passthrough_reached()));
  ESP_LOGD(TAG, "Turn arm_to_start_ms=%" PRIu64 " arm_expired=%u",
           arm_to_start_ms_, static_cast<unsigned>(arm_expired_));
}

void PreRollMicrophone::stop() {
  {
    LockGuard lock(mutex_);
    if (listeners_ == 0 || --listeners_ != 0)
      return;
    log_turn_();
    source_->stop();
    state_ = microphone::STATE_STOPPED;
    fast_loop_.stop();
    passthrough_ = false;
  }
  parent_->pre_roll_complete();
  clear();
}

void PreRollMicrophone::clear() {
  LockGuard lock(mutex_);
  if (buffer_)
    buffer_->stop();
  arm_pending_ = false;
  passthrough_ = listeners_ != 0;
}

void PreRollMicrophone::set_privacy_mute(bool muted) {
  LockGuard lock(mutex_);
  privacy_mute_ = muted;
  if (buffer_)
    update_mute_();
}

bool PreRollMicrophone::history_complete() {
  LockGuard lock(mutex_);
  return !buffer_ || buffer_->history_remaining() == 0;
}

uint32_t PreRollMicrophone::pre_roll_ms() {
  LockGuard lock(mutex_);
  return buffer_ ? buffer_->pre_roll_ms() : 0;
}

void PreRollMicrophone::dump_config() {
  ESP_LOGCONFIG(TAG, "Pre-roll: %u ms lookback, %u PCM bytes (PSRAM preferred)",
                static_cast<unsigned>(length_ms_),
                static_cast<unsigned>(capacity_ * sizeof(StereoFrame)));
}
}
#endif
