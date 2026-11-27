// SPDX-License-Identifier: GPL-3.0-or-later
#include <algorithm>
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
std::vector<std::string> events, logs;
std::vector<uint32_t> wake_times;
uint64_t now{100};
uint32_t reply_wake_detected_ms{0}, tick_lag{0};
bool announcing{true}, reply_wake_pending{false};
int voice_assistant_phase{5};
std::string injection;
bool expired{false};
void detect(const std::string &wake_word);
void restart(const std::string &wake_word);
void cancel();
void on_error();
void chime_wait();
uint32_t millis() { return static_cast<uint32_t>(now) - tick_lag; }
uint64_t millis_64() { return now; }
struct Switch { bool state{false}; } master_mute_switch, timer_ringing, wake_sound;
namespace media_player { enum State { MEDIA_PLAYER_STATE_ANNOUNCING }; }
struct Player { int state{media_player::MEDIA_PLAYER_STATE_ANNOUNCING}; } external_media_player;
struct VoiceAssistant {
  bool running{true};
  unsigned starts{0}, stops{0};
  bool is_running() const { return running; }
  void stop() { ++stops; events.push_back("stop"); }
  void start() {
    assert(!running && "reply restart must wait for idle");
    running = true;
    ++starts;
    events.push_back("start");
  }
} va;
struct Microphone {
  bool captured{false};
  void capture_reply_wake() { captured = true; events.push_back("capture"); }
  bool reply_wake_ready() const { return captured && !master_mute_switch.state && !va.running; }
  void wake_detected() { assert(!va.running); events.push_back("arm"); }
  void wake_started() { events.push_back("bound"); }
  void clear() { captured = false; events.push_back("cancel history"); }
} pre_roll_mic;
struct RestartScript {
  void execute(const std::string &word) { restart(word); }
  void stop() {}
} assist_live_restart_reply_wake;
struct CancelScript { void execute() { cancel(); } } assist_live_cancel_reply_wake;
template<typename F> void wait_for_idle(F ready) {
  const auto detected_at = now;
  assert(!ready() && "stop must remain asynchronous in test");
  if (!injection.empty()) {
    now += 100;
    if (injection == "mute") {
      master_mute_switch.state = true;
      cancel();
    } else if (injection == "error") {
      on_error();
    } else if (injection == "timer") {
      timer_ringing.state = true;
      detect("Hey Jarvis");
    } else {
      detect(injection);
    }
  }
  now = detected_at + 300;
  if (tick_lag) tick_lag = 37;
  if (!expired) {
    va.running = false;
    announcing = false;
    external_media_player.state = -1;
  } else {
    now = detected_at + 500;
  }
}
void log_line(const char *, const char *format, ...) {
  char buffer[160];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  logs.emplace_back(buffer);
}
#define id(value) value
#define ESP_LOGI log_line
#define ESP_LOGW log_line
void cancel() { CANCEL_BODY }
void restart(const std::string &wake_word) { (void)wake_word; RESTART_BODY }
void detect(const std::string &wake_word) { HANDLER_BODY }
void on_error() { ERROR_BODY }
std::string scenario;
void chime_wait() {
  now += 300;
  if (tick_lag) tick_lag = 73;
  if (scenario.find("stop_during_chime") == 0 && std::count(events.begin(), events.end(), "chime") == 1) {
    assert(reply_wake_pending && !va.running && !announcing);
    if (scenario == "stop_during_chime_with_announcement") announcing = true;
    if (scenario == "stop_during_chime_with_timer") timer_ringing.state = true;
    detect("Stop");
  }
  if (scenario == "timer_during_chime") timer_ringing.state = true;
  if (scenario == "announcement_during_chime") {
    announcing = true;
    external_media_player.state = media_player::MEDIA_PLAYER_STATE_ANNOUNCING;
  }
}
int main(int argc, char **argv) {
  assert(argc == 2);
  scenario = argv[1];
  const bool split_clock = scenario.find("split_clock") == 0;
  if (split_clock) tick_lag = 13;
  if (scenario == "split_clock_wrap") now = (uint64_t{1} << 32) - 16;
  const auto detected_at = static_cast<uint32_t>(now);
  if (scenario == "chime" || scenario == "split_clock_chime" ||
      scenario.find("during_chime") != std::string::npos)
    wake_sound.state = true;
  if (scenario == "timer") timer_ringing.state = true;
  if (scenario == "muted") master_mute_switch.state = true;
  if (scenario == "listening") voice_assistant_phase = 2;
  if (scenario == "thinking") voice_assistant_phase = 4;
  if (scenario == "announcement") va.running = false;
  if (scenario == "timeout") expired = true;
  if (scenario == "pending_stop") injection = "Stop";
  if (scenario == "pending_wake") injection = "Hey Jarvis";
  if (scenario == "pending_mute") injection = "mute";
  if (scenario == "pending_error") injection = "error";
  if (scenario == "pending_timer") injection = "timer";
  detect(scenario == "stop" ? "Stop" : "Okay Nabu");
  assert(!events.empty() && events.front() == "wake" && wake_times.front() == detected_at && "timing first at detection");
  const bool starts = scenario == "reply" || scenario == "pending_wake" || scenario == "chime" || split_clock;
  assert(va.starts == unsigned(starts) && "only named reply wake starts a replacement turn");
  if (starts) {
    assert(events[1] == "capture" && events[2] == "stop");
    const auto arm = std::find(events.begin(), events.end(), "arm");
    assert(arm != events.end() && *(arm + 1) == "start" && *(arm + 2) == "bound");
    assert(std::find(logs.begin(), logs.end(), "Reply wake detection_to_idle_ms=300") != logs.end());
    assert(std::find(logs.begin(), logs.end(), wake_sound.state ?
                    "Reply wake detection_to_start_ms=600" : "Reply wake detection_to_start_ms=300") != logs.end());
  }
  if (scenario == "stop" || scenario == "listening" || scenario == "thinking")
    assert(va.stops == 1 && events.size() == 2);
  if (scenario == "timer") assert(!timer_ringing.state && va.stops == 0);
  if (scenario == "muted") assert(va.stops == 0);
  if (scenario == "timeout")
    assert(std::any_of(logs.begin(), logs.end(), [](const auto &line) { return line.find("idle wait expired") != std::string::npos; }));
  if (scenario == "pending_stop" || scenario == "pending_mute" || scenario == "pending_error")
    assert(!pre_roll_mic.captured && !reply_wake_pending);
  if (scenario == "pending_stop") assert(va.stops == 2 && "Stop still stops a running assistant");
  if (scenario == "pending_error")
    assert(va.starts == 0 && "an error during the stop wait cancels the restart");
  if (scenario == "pending_timer") {
    assert(!timer_ringing.state && "a wake word stops a timer that rings during the stop wait");
    assert(!pre_roll_mic.captured && !reply_wake_pending && va.starts == 0 && va.stops == 1 &&
           "the timer stop cancels the pending restart");
  }
  if (scenario.find("during_chime") != std::string::npos) {
    assert(!pre_roll_mic.captured && !reply_wake_pending);
    assert(va.starts == 0 && "chime races must cancel the pending restart");
  }
  if (scenario == "stop_during_chime")
    assert(va.stops == 1 && std::count(events.begin(), events.end(), "chime") == 1 &&
           "Stop cancels without starting a second chime");
  if (scenario == "stop_during_chime_with_announcement")
    assert(!announcing && "Stop still stops an announcement");
  if (scenario == "stop_during_chime_with_timer")
    assert(!timer_ringing.state && "Stop still stops a ringing timer");
  std::cout << "PASS " << scenario << '\n';
}
