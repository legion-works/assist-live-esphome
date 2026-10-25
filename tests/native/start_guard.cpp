// SPDX-License-Identifier: GPL-3.0-or-later
#include <cassert>
#include <cstdio>
#include <string>

int calls = 0, logs = 0, deleted = 0;
void *active = nullptr;
int fail_until = 1;
struct Address {};
struct Probe {
  std::string token, server, revision, run_id, boot, device_id;
  Address address;
  void run() {}
  ~Probe() { ++deleted; }
};
namespace esphome {
struct Application {
  std::string get_name() { return "test-node"; }
} App;
}  // namespace esphome

using BaseType_t = int;
constexpr int pdPASS = 1;
#define ESP_LOGE(tag, format, attempt) \
  do {                               \
    ++logs;                          \
    (void) (attempt);                \
  } while (false)
void vTaskDelete(void *) {}
int xTaskCreatePinnedToCore(void (*)(void *), const char *, int, void *arg, int,
                            void *, int) {
  ++calls;
  if (calls <= fail_until)
    return -1;
  active = arg;
  return pdPASS;
}

#include "probe_start.inc"

int main(int argc, char **) {
  fail_until = argc == 1 ? 1 : 10;
  for (int i = 0; i < 10; ++i)
    start("token", "server", "revision", "run");
  if (fail_until == 1) {
    assert(calls == 2 && logs == 1 && deleted == 1);
    assert(static_cast<Probe *>(active)->device_id == "test-node");
    delete static_cast<Probe *>(active);
  } else {
    assert(calls == 3 && logs == 3 && deleted == 3 && active == nullptr);
  }
}
