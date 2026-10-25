// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <functional>
#include <vector>
namespace esphome {
namespace media_player {
enum MediaPlayerState {
  MEDIA_PLAYER_STATE_IDLE,
  MEDIA_PLAYER_STATE_PLAYING,
  MEDIA_PLAYER_STATE_ANNOUNCING
};
class MediaPlayer {
public:
  template <typename F> void add_on_state_callback(F callback) {
    callbacks.emplace_back(callback);
  }
  void publish(MediaPlayerState state) {
    for (auto &callback : callbacks)
      callback(state);
  }
  std::vector<std::function<void(MediaPlayerState)>> callbacks;
};
} // namespace media_player
} // namespace esphome
