// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <algorithm>
#include <cstring>

namespace esphome::assist_live {
struct StereoFrame { int32_t left, right; };
class PreRollBuffer {
public:
  // Keep replay backlog bounded. See the public design record:
  // https://github.com/legion-works/assist-live/blob/main/docs/design.md
  static constexpr uint32_t MAX_EXTRA_BACKLOG_MS = 256;
  PreRollBuffer(StereoFrame *memory, size_t history, size_t capacity,
                uint32_t sample_rate = 16000)
      : memory_(memory), history_(history), capacity_(capacity), rate_(sample_rate) {}

  // The caller serializes capture, turn hooks, and output with one mutex.
  void push(const StereoFrame *frames, size_t count) {
    if (muted_)
      return;
    for (size_t i = 0; i < count; ++i) {
      if (pending() == capacity_) {
        const size_t drop = std::min(pending(), block_frames());
        if (active_ || armed_) {
          dropped_ += drop;
          dropped_history_ += active_ ? std::min<uint64_t>(drop, history_remaining()) : drop;
          ++overflows_;
        }
        read_ += drop;
      }
      memory_[write_++ % capacity_] = frames[i];
      if (!active_ && !armed_ && pending() > history_)
        read_ = write_ - history_;
    }
  }

  void arm(uint64_t now) {
    if (muted_ || active_)
      return;
    read_ = write_ - std::min<size_t>(history_, pending());
    armed_ = true;
    detection_ms_ = now;
    dropped_ = dropped_history_ = overflows_ = trimmed_ = 0;
  }

  void start(uint64_t now, bool wake_sound) {
    if (!armed_ || wake_sound || muted_ || now - detection_ms_ > 1000) {
      read_ = write_;
      detection_ms_ = 0;
      dropped_ = dropped_history_ = overflows_ = trimmed_ = 0;
    }
    trimmed_ = pending() > rate_ ? pending() - rate_ : 0;
    read_ += trimmed_;
    history_end_ = write_;
    armed_ = false;
    active_ = true;
    listening_ = false;
    start_ms_ = next_ms_ = now;
    history_sent_ = live_sent_ = handed_ = 0;
    history_end_queue_ms_ = history_remaining() == 0 ? static_cast<int32_t>(queue_delay_ms()) : -1;
    first_live_queue_ms_ = -1;
    passthrough_reached_ = false;
  }

  void listen() { listening_ = true; }

  void stop() {
    std::memset(memory_, 0, capacity_ * sizeof(StereoFrame));
    read_ = write_ = history_end_ = 0;
    armed_ = active_ = listening_ = false;
  }

  void mute(bool muted) {
    if (muted)
      stop();
    muted_ = muted;
  }

  size_t pop(uint64_t now, bool ready, StereoFrame *out, size_t maximum) {
    if (!active_ || !listening_ || !ready || muted_ || now < next_ms_)
      return 0;
    // VA has 512 ms rings. At most 256 ms is extra backlog over 1x live audio.
    const uint64_t credit = (now - start_ms_ + MAX_EXTRA_BACKLOG_MS) * rate_ / 1000;
    if (handed_ >= credit)
      return 0;
    const size_t count = std::min<uint64_t>(
        std::min({pending(), maximum, block_frames()}), credit - handed_);
    if (count == 0)
      return 0;
    const size_t historical = std::min<uint64_t>(count, history_remaining());
    for (size_t i = 0; i < count; ++i)
      out[i] = memory_[read_++ % capacity_];
    history_sent_ += historical;
    live_sent_ += count - historical;
    handed_ += count;
    if (history_remaining() == 0 && history_end_queue_ms_ < 0)
      history_end_queue_ms_ = queue_delay_ms();
    if (count != historical && first_live_queue_ms_ < 0)
      first_live_queue_ms_ = queue_delay_ms();
    if (pending() == 0)
      passthrough_reached_ = true;
    next_ms_ = now + std::max<uint64_t>(1, (count * 1000 + 2 * rate_ - 1) / (2 * rate_));
    return count;
  }

  void account_passthrough(size_t frames) {
    live_sent_ += frames;
    handed_ += frames;
    if (first_live_queue_ms_ < 0)
      first_live_queue_ms_ = 0;
    passthrough_reached_ = true;
  }
  size_t pending() const { return static_cast<size_t>(write_ - read_); }
  size_t history_remaining() const { return read_ < history_end_ ? history_end_ - read_ : 0; }
  size_t history_sent() const { return history_sent_; }
  size_t live_sent() const { return live_sent_; }
  size_t dropped_frames() const { return dropped_; }
  size_t dropped_history() const { return dropped_history_; }
  size_t trimmed_frames() const { return trimmed_; }
  size_t overflows() const { return overflows_; }
  uint64_t handed_frames() const { return handed_; }
  uint32_t pre_roll_ms() const { return history_sent_ * 1000 / rate_; }
  bool passthrough() const { return active_ && listening_ && pending() == 0; }
  bool active() const { return active_; }
  int32_t history_end_queue_ms() const { return history_end_queue_ms_; }
  int32_t first_live_queue_ms() const { return first_live_queue_ms_; }
  uint32_t queue_delay_ms() const { return pending() * 1000 / rate_; }
  bool passthrough_reached() const { return passthrough_reached_; }
  uint64_t detection_ms() const { return detection_ms_; }
  uint64_t start_ms() const { return start_ms_; }
  size_t block_frames() const { return rate_ * 16 / 1000; }

private:
  StereoFrame *memory_;
  size_t history_, capacity_;
  uint32_t rate_;
  uint64_t read_{0}, write_{0}, history_end_{0};
  uint64_t detection_ms_{0}, start_ms_{0}, next_ms_{0}, handed_{0};
  size_t history_sent_{0}, live_sent_{0}, dropped_{0}, dropped_history_{0}, overflows_{0}, trimmed_{0};
  int32_t history_end_queue_ms_{-1}, first_live_queue_ms_{-1};
  bool passthrough_reached_{false};
  bool armed_{false}, active_{false}, listening_{false}, muted_{false};
};
}
