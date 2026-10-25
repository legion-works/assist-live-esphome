// SPDX-License-Identifier: GPL-3.0-or-later
#include "assist_live.h"

#include "esp_random.h"
#include "esp_timer.h"
#include "esphome/core/log.h"
#include "freertos/task.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "mbedtls/md.h"
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <memory>
#ifdef USE_ASSIST_LIVE_WEBSOCKET
#include "esp_transport_tcp.h"
#include "esp_transport_ws.h"
#endif

namespace esphome {
namespace assist_live {

static const char *const TAG = "assist_live";

class AddressResolver {
public:
  virtual ~AddressResolver() = default;
  virtual bool resolve(const std::string &host, in_addr &address) = 0;
};

class LwipResolver : public AddressResolver {
public:
  bool resolve(const std::string &host, in_addr &address) override {
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo *result = nullptr;
    if (getaddrinfo(host.c_str(), nullptr, &hints, &result) != 0 ||
        result == nullptr)
      return false;
    address = reinterpret_cast<sockaddr_in *>(result->ai_addr)->sin_addr;
    freeaddrinfo(result);
    return true;
  }
};

class ResolvedEndpoint {
public:
  ResolvedEndpoint(const std::string &server, uint16_t port,
                   AddressResolver &resolver)
      : server_(server), resolver_(resolver) {
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
  }
  bool ready(uint64_t now) {
    if (valid_ && now < expires_)
      return true;
    if (now < retry_at_)
      return false;
    retry_at_ = now + 5000;
    valid_ = resolver_.resolve(server_, address.sin_addr);
    if (valid_)
      expires_ = now + 60000;
    return valid_;
  }
  void failed(uint64_t now) {
    valid_ = false;
    retry_at_ = now + 5000;
  }
  sockaddr_in address{};

protected:
  std::string server_;
  AddressResolver &resolver_;
  uint64_t expires_{0}, retry_at_{0};
  bool valid_{false};
};

class EventSender {
public:
  virtual ~EventSender() = default;
  virtual bool send(const std::string &packet) = 0;
};

class UdpSender : public EventSender {
public:
  explicit UdpSender(ResolvedEndpoint &endpoint) : endpoint_(endpoint) {
    fd_ = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (fd_ >= 0 && fcntl(fd_, F_SETFL, O_NONBLOCK) < 0) {
      close(fd_);
      fd_ = -1;
    }
  }
  ~UdpSender() override {
    if (fd_ >= 0)
      close(fd_);
  }
  bool send(const std::string &packet) override {
    const auto now = AssistLiveComponent::monotonic_ms();
    if (fd_ < 0 || !endpoint_.ready(now))
      return false;
    if (sendto(fd_, packet.data(), packet.size(), MSG_DONTWAIT,
               reinterpret_cast<const sockaddr *>(&endpoint_.address),
               sizeof(endpoint_.address)) == static_cast<int>(packet.size()))
      return true;
    endpoint_.failed(now);
    return false;
  }

protected:
  ResolvedEndpoint &endpoint_;
  int fd_{-1};
};

#ifdef USE_ASSIST_LIVE_WEBSOCKET
class WebSocketSender : public EventSender {
public:
  explicit WebSocketSender(ResolvedEndpoint &endpoint) : endpoint_(endpoint) {
    tcp_ = esp_transport_tcp_init();
    if (tcp_ != nullptr)
      ws_ = esp_transport_ws_init(tcp_);
    if (ws_ != nullptr)
      esp_transport_ws_set_path(ws_, "/v1/device");
  }
  ~WebSocketSender() override {
    if (ws_ != nullptr)
      esp_transport_destroy(ws_);
    if (tcp_ != nullptr)
      esp_transport_destroy(tcp_);
  }
  bool send(const std::string &packet) override {
    if (ws_ == nullptr)
      return false;
    const auto now = AssistLiveComponent::monotonic_ms();
    if (!connected_) {
      if (now < retry_at_)
        return false;
      retry_at_ = now + 5000;
      if (!endpoint_.ready(now))
        return false;
      char address[INET_ADDRSTRLEN];
      if (inet_ntop(AF_INET, &endpoint_.address.sin_addr, address,
                    sizeof(address)) == nullptr)
        return false;
      connected_ =
          esp_transport_connect(ws_, address, ntohs(endpoint_.address.sin_port),
                                250) >= 0;
      if (!connected_) {
        esp_transport_close(ws_);
        endpoint_.failed(now);
        return false;
      }
    }
    int sent = esp_transport_ws_send_raw(
        ws_,
        static_cast<ws_transport_opcodes_t>(WS_TRANSPORT_OPCODES_TEXT |
                                            WS_TRANSPORT_OPCODES_FIN),
        packet.data(), packet.size(), 50);
    if (sent == static_cast<int>(packet.size()))
      return true;
    connected_ = false;
    endpoint_.failed(now);
    esp_transport_close(ws_);
    return false;
  }

protected:
  ResolvedEndpoint &endpoint_;
  esp_transport_handle_t tcp_{nullptr}, ws_{nullptr};
  uint64_t retry_at_{0};
  bool connected_{false};
};
#endif

static bool sign_hmac(const uint8_t *key, size_t key_size, const uint8_t *data,
                      size_t size, uint8_t *digest) {
  return mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key,
                         key_size, data, size, digest) == 0;
}

uint64_t AssistLiveComponent::monotonic_ms() {
  return static_cast<uint64_t>(esp_timer_get_time()) / 1000;
}

void AssistLiveComponent::setup() {
  if (queue_ != nullptr)
    return;
  esp_fill_random(&boot_, sizeof(boot_));
  queue_ = xQueueCreate(16, sizeof(Event));
  if (queue_ == nullptr) {
    mark_failed();
    return;
  }
  // Socket waits stay on core 0 at priority 0, not on the native audio path.
  auto result = xTaskCreatePinnedToCore(
      [](void *arg) { static_cast<AssistLiveComponent *>(arg)->run_(); },
      "assist_live", 8192, this, 0, nullptr, 0);
  if (result != pdPASS) {
    vQueueDelete(queue_);
    queue_ = nullptr;
    mark_failed();
  }
  if (player_ != nullptr)
    player_->add_on_state_callback(
        [this](media_player::MediaPlayerState state) {
          this->playback_state(
              state == media_player::MEDIA_PLAYER_STATE_PLAYING ||
              state == media_player::MEDIA_PLAYER_STATE_ANNOUNCING);
        });
}

void AssistLiveComponent::emit_event(Stage stage, uint64_t device_ms,
                                     const char *canonical_data) {
  if (queue_ == nullptr || exhausted_ || std::strlen(canonical_data) > 256) {
    ++dropped_;
    return;
  }
  Event event{};
  event.boot = boot_;
  event.seq = next_seq_++;
  if (event.seq == std::numeric_limits<uint64_t>::max())
    exhausted_ = true;
  event.device_ms = device_ms;
  event.stage = stage;
  std::strcpy(event.data, canonical_data);
  if (xQueueSend(queue_, &event, 0) != pdTRUE)
    ++dropped_;
}

void AssistLiveComponent::command_stream_start() {
  if (command_open_)
    return;
  command_open_ = true;
  emit_event(Stage::MIC_OPEN, monotonic_ms(),
             "{\"quality\":\"proxy\",\"source\":\"voice_assistant.on_start\"}");
}

void AssistLiveComponent::playback_state(bool active) {
  if (active == playback_active_)
    return;
  playback_active_ = active;
  emit_event(active ? Stage::PLAYBACK_START : Stage::PLAYBACK_END,
             monotonic_ms(),
             "{\"quality\":\"proxy\",\"source\":\"media_player.on_state\"}");
}

void AssistLiveComponent::measured_sample_boundary(bool started,
                                                   uint64_t device_ms) {
  emit_event(
      started ? Stage::PLAYBACK_START : Stage::PLAYBACK_END, device_ms,
      "{\"quality\":\"measured\",\"source\":\"validated_sample_callback\"}");
}

void AssistLiveComponent::run_() {
  LwipResolver resolver;
  ResolvedEndpoint endpoint(server_, port_, resolver);
  std::unique_ptr<EventSender> sender;
#ifdef USE_ASSIST_LIVE_WEBSOCKET
  if (websocket_)
    sender.reset(new WebSocketSender(endpoint));
#endif
  if (!sender)
    sender.reset(new UdpSender(endpoint));
  Event event;
  while (true) {
    if (xQueueReceive(queue_, &event, portMAX_DELAY) != pdTRUE)
      continue;
    auto packet =
        encode_event(device_, event, key_.data(), key_.size(), sign_hmac);
    if (packet.empty() || !sender->send(packet))
      ++dropped_;
  }
}

void AssistLiveComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "Assist Live timing: %s",
                websocket_ ? "WebSocket" : "UDP");
  ESP_LOGCONFIG(TAG, "Dropped timing events: %u",
                static_cast<unsigned>(dropped_.load()));
}

} // namespace assist_live
} // namespace esphome
