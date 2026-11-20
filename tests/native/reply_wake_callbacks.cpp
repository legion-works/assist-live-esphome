// SPDX-License-Identifier: GPL-3.0-or-later
#include "reply_wake_window.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <functional>
#include <iostream>
#include <vector>
namespace media_player {
enum State { MEDIA_PLAYER_STATE_IDLE, MEDIA_PLAYER_STATE_ANNOUNCING };
using MediaPlayerState = State;
}
struct Model {
  unsigned cutoff{0};
  void set_probability_cutoff(unsigned value) { cutoff = value; }
} okay_nabu, hey_jarvis, hey_mycroft;
struct Player {
  media_player::State state{media_player::MEDIA_PLAYER_STATE_IDLE};
  std::vector<std::function<void(media_player::MediaPlayerState)>> callbacks;
  void add_on_state_callback(std::function<void(media_player::MediaPlayerState)> callback) {
    callbacks.push_back(callback);
  }
  void publish(media_player::State value) {
    state = value;
    for (const auto &callback : callbacks) callback(state);
  }
} external_media_player;
struct VoiceAssistant {
  bool running{false};
  bool is_running() const { return running; }
} va;
struct Script {
  std::function<void()> body;
  unsigned executions{0};
  void execute() { ++executions; if (body) body(); }
  void stop() {}
} assist_live_apply_wake_cutoffs, assist_live_update_reply_wake, assist_live_reply_wake_tail;
esphome::assist_live::ReplyWakeWindow reply_wake_window;
uint32_t now{0};
uint32_t millis() { return now; }
std::vector<std::string> logs;
void log_line(const char *, const char *format, ...) {
  char buffer[128];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  logs.emplace_back(buffer);
}
#define id(value) value
#define ESP_LOGI log_line

void select_value(const std::string &x) {
  SELECT_BODY
}

int main() {
  assist_live_apply_wake_cutoffs.body = []() { APPLY_BODY };
  assist_live_update_reply_wake.body = []() { UPDATE_BODY };
  for (const auto *option : {"Moderately sensitive", "Slightly sensitive", "Very sensitive", "Moderately sensitive"})
    select_value(option);
  assert(external_media_player.callbacks.size() == 1 && "exactly one state callback");
  logs.clear();
  now = 100;
  va.running = true;
  external_media_player.publish(media_player::MEDIA_PLAYER_STATE_ANNOUNCING);
  external_media_player.publish(media_player::MEDIA_PLAYER_STATE_ANNOUNCING);
  assert(logs.size() == 3 && "one log per model at window start");
  assert(logs[0] == "okay_nabu reason=reply window start cutoff=143");
  select_value("Slightly sensitive");
  assert(external_media_player.callbacks.size() == 1 && logs.size() == 3);
  now = 500;
  va.running = false;
  external_media_player.publish(media_player::MEDIA_PLAYER_STATE_IDLE);
  assert(assist_live_reply_wake_tail.executions == 1);
  assert(logs.size() == 3 && okay_nabu.cutoff == 143);
  now = 1500;
  []() { EXPIRE_BODY }();
  assist_live_apply_wake_cutoffs.execute();
  assert(logs.size() == 6 && "one log per model at window end");
  assert(logs[3] == "okay_nabu reason=reply window end cutoff=217");
  assert(okay_nabu.cutoff == 217 && hey_jarvis.cutoff == 247 && hey_mycroft.cutoff == 253);
  std::cout << "PASS one callback and one log per model per edge\n";
}
