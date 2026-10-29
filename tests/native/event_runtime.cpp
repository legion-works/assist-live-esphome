// SPDX-License-Identifier: GPL-3.0-or-later
#include "assist_live.cpp"
#include "mbedtls/platform_util.h"
#include <barrier>
#include <cassert>
#include <iostream>
#include <thread>

using namespace esphome::assist_live;
class Resolver : public AddressResolver {
public:
  int calls{0};
  bool succeeds{true};
  bool loopback{false};
  bool resolve(const std::string &host, in_addr &address) override {
    assert(host == "timing-server.invalid");
    ++calls;
    address.s_addr = htonl(loopback ? INADDR_LOOPBACK : 0xc0000201);
    return succeeds;
  }
};
class TestComponent : public AssistLiveComponent {
public:
  ~TestComponent() {
    if (queue_ != nullptr)
      vQueueDelete(queue_);
  }
  Event take() {
    Event result{};
    assert(xQueueReceive(queue_, &result, 0));
    return result;
  }
  bool empty() const { return queue_ == nullptr || queue_->items.empty(); }
  void force_sequence(uint64_t seq) { next_seq_ = seq; }
  void drain_worker() {
    try {
      run_();
    } catch (const std::runtime_error &) {
    }
  }
};
static TestComponent *shutdown_component = nullptr;
static size_t expected_shutdown_wipes = 0;
static int expected_shutdown_closes = 0;
static void check_cleanup_before_task_delete() {
  assert(shutdown_component->teardown());
  assert(test_zeroized_sizes.size() == expected_shutdown_wipes);
#ifdef USE_ASSIST_LIVE_WEBSOCKET
  assert(test_destroy_calls == expected_shutdown_closes);
#else
  assert(test_socket_closes == expected_shutdown_closes);
#endif
}

int main() {
  Resolver resolver;
  ResolvedEndpoint endpoint("timing-server.invalid", 8765, resolver);
  assert(resolver.calls == 0);
  assert(endpoint.ready(0) && resolver.calls == 1);
  assert(endpoint.ready(100) && resolver.calls == 1);
  endpoint.failed(100);
  assert(!endpoint.ready(101) && resolver.calls == 1);
  resolver.succeeds = false;
  assert(!endpoint.ready(5100) && resolver.calls == 2);
  assert(!endpoint.ready(5101) && resolver.calls == 2);
  resolver.succeeds = true;
  assert(endpoint.ready(10100) && resolver.calls == 3);
  assert(endpoint.ready(70100) && resolver.calls == 4);
  Resolver local;
  local.loopback = true;
  int receiver = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  assert(receiver >= 0);
  sockaddr_in local_address{};
  local_address.sin_family = AF_INET;
  local_address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  assert(bind(receiver, reinterpret_cast<sockaddr *>(&local_address),
              sizeof(local_address)) == 0);
  socklen_t address_size = sizeof(local_address);
  assert(getsockname(receiver, reinterpret_cast<sockaddr *>(&local_address),
                     &address_size) == 0);
  ResolvedEndpoint udp_endpoint("timing-server.invalid",
                                ntohs(local_address.sin_port), local);
  UdpSender udp(udp_endpoint);
  EventSender *sender = &udp;
  const std::string packet = "{\"version\":1,\"tag\":\"public-test-tag\"}";
  assert(sender->send(packet));
  char datagram[256];
  int received = recv(receiver, datagram, sizeof(datagram), MSG_DONTWAIT);
  assert(received == static_cast<int>(packet.size()) &&
         std::string(datagram, received) == packet);
  {
    UdpSender recovering(udp_endpoint);
    fail_socket_attempts = 1;
    auto before = test_socket_calls;
    assert(!recovering.send(packet) &&
           recovering.initialization_failures() == 1);
    assert(!recovering.send(packet) && test_socket_calls == before + 1);
    test_time_us += 5000000;
    assert(recovering.send(packet) && test_socket_calls == before + 2);
    assert(recv(receiver, datagram, sizeof(datagram), MSG_DONTWAIT) ==
           static_cast<int>(packet.size()));
    test_time_us = 123456789000;
  }
  close(receiver);
#ifdef USE_ASSIST_LIVE_WEBSOCKET
  Resolver ws_resolver;
  ResolvedEndpoint ws_endpoint("timing-server.invalid", 8765, ws_resolver);
  WebSocketSender websocket(ws_endpoint);
  sender = &websocket;
  test_connect_result = 0;
  assert(sender->send(packet) && test_ws_packet == packet &&
         ws_resolver.calls == 1);
  test_write_success = false;
  assert(!sender->send(packet));
  test_write_success = true;
  assert(!sender->send(packet) && ws_resolver.calls == 1);
  test_time_us += 5000000;
  assert(sender->send(packet) && ws_resolver.calls == 2);
  {
    WebSocketSender recovering(ws_endpoint);
    fail_tcp_attempts = 1;
    auto before = test_tcp_calls;
    assert(!recovering.send(packet) &&
           recovering.initialization_failures() == 1);
    assert(!recovering.send(packet) && test_tcp_calls == before + 1);
    test_time_us += 5000000;
    assert(recovering.send(packet) && test_tcp_calls == before + 2);
  }
  {
    WebSocketSender recovering(ws_endpoint);
    fail_ws_attempts = 1;
    assert(!recovering.send(packet) &&
           recovering.initialization_failures() == 1);
    test_time_us += 5000000;
    assert(recovering.send(packet));
  }
  test_connect_result = -1;
  {
    test_connect_result = 0;
    WebSocketSender closed(ws_endpoint);
    assert(closed.send(packet));
    int writes = test_text_writes;
    int destroyed = test_destroy_calls;
    test_frames.push_back({8, std::string{"\x03\xf0", 2}});
    assert(!closed.send(packet) && test_text_writes == writes);
    assert(test_destroy_calls == destroyed + 2);
    test_time_us += 60000000;
    assert(closed.send(packet));
    test_close_after_write = 1009;
    assert(!closed.send(packet));
    test_frames.clear();
  }
  {
    ResolvedEndpoint cap_endpoint("timing-server.invalid", 8765, ws_resolver);
    WebSocketSender capped(cap_endpoint);
    test_connect_result = -1;
    test_http_status = 503;
    for (uint64_t delay : {5000, 10000, 20000, 40000, 60000, 60000}) {
      int calls = test_connect_calls;
      assert(!capped.send(packet) && test_connect_calls == calls + 1);
      test_time_us += (delay - 1) * 1000;
      assert(!capped.send(packet) && test_connect_calls == calls + 1);
      test_time_us += 1000;
    }
    test_http_status = 0;
  }
  assert(test_propagate_control);
  test_connect_result = -1;
  test_time_us = 123456789000;
#endif
  TestComponent component;
  std::array<uint8_t, 32> key{};
  const char canary[] = "fake-secret-byte-array-1234567890";
  std::memcpy(key.data(), canary, 32);
  component.set_device("anonymous-satellite");
  auto wipes = test_zeroized_sizes.size();
  component.set_hmac_key(key);
  assert(test_zeroized_sizes.size() == wipes + 1 &&
         test_zeroized_sizes.back() == 32);
  assert(std::memcmp(key.data(), canary, 32) == 0);
  {
    auto before = test_zeroized_sizes.size();
    {
      TestComponent cleanup;
      cleanup.set_hmac_key(key);
      cleanup.on_shutdown();
    }
    assert(test_zeroized_sizes.size() == before + 2);
  }
  component.set_server("192.0.2.1");
  esphome::media_player::MediaPlayer player;
  int stock_calls = 0;
  player.add_on_state_callback(
      [&stock_calls](esphome::media_player::MediaPlayerState) {
        ++stock_calls;
      });
  component.set_media_player(&player);
  component.setup();
  assert(component.empty());
  uint64_t boot = 0;
  for (int turn = 0; turn < 2; ++turn) {
    component.emit_event(Stage::WAKE_DETECTED, component.monotonic_ms());
    component.command_stream_start();
    component.command_stream_start();
    component.command_stream_end();
    auto wake = component.take();
    auto mic = component.take();
    assert(wake.stage == Stage::WAKE_DETECTED && mic.stage == Stage::MIC_OPEN);
    assert(wake.seq == static_cast<uint64_t>(turn * 2) &&
           mic.seq == wake.seq + 1);
    assert(wake.boot == mic.boot && (turn == 0 || wake.boot == boot));
    assert(wake.device_ms == 123456789 && mic.device_ms == wake.device_ms);
    assert(std::strstr(mic.data, "proxy") &&
           std::strstr(mic.data, "voice_assistant.on_start"));
    assert(std::strstr(mic.data, "\"pre_roll_ms\":0") &&
           "a turn without history reports integer zero inside signed data");
    assert(component.empty());
    boot = wake.boot;
  }
  component.setup();
  player.publish(esphome::media_player::MEDIA_PLAYER_STATE_IDLE);
  player.publish(esphome::media_player::MEDIA_PLAYER_STATE_PLAYING);
  player.publish(esphome::media_player::MEDIA_PLAYER_STATE_ANNOUNCING);
  player.publish(esphome::media_player::MEDIA_PLAYER_STATE_IDLE);
  assert(stock_calls == 4);
  auto start = component.take(), end = component.take();
  assert(start.stage == Stage::PLAYBACK_START &&
         end.stage == Stage::PLAYBACK_END);
  assert(start.seq == 4 && end.seq == 5 && start.boot == boot);
  assert(std::strstr(start.data, "proxy") && std::strstr(end.data, "proxy"));
  assert(!std::strstr(start.data, "measured") &&
         !std::strstr(end.data, "measured"));
  assert(component.empty());
  for (int i = 0; i < 17; ++i)
    component.emit_event(Stage::WAKE_DETECTED, component.monotonic_ms());
  assert(component.dropped_events() == 1);
  for (int i = 0; i < 16; ++i)
    assert(component.take().seq == static_cast<uint64_t>(6 + i));
  component.emit_event(Stage::WAKE_DETECTED, component.monotonic_ms());
  assert(component.take().seq == 23);
  component.dump_config();
  assert(test_dns_calls == 0);
  TestComponent restarted;
  restarted.setup();
  restarted.command_stream_start();
  auto first = restarted.take();
  assert(first.seq == 0 && first.boot != boot);
  restarted.measured_sample_boundary(true, 42);
  assert(std::strstr(restarted.take().data, "measured"));
  fail_task = true;
  TestComponent failed;
  failed.setup();
  failed.emit_event(Stage::MIC_OPEN, 10);
  assert(failed.failed && failed.dropped_events() == 1);
  fail_task = false;
  fail_queue = true;
  TestComponent no_queue;
  no_queue.setup();
  assert(no_queue.failed);
  fail_queue = false;
  TestComponent overflow;
  overflow.setup();
  overflow.force_sequence(std::numeric_limits<uint64_t>::max());
  overflow.emit_event(Stage::WAKE_DETECTED, 1);
  overflow.emit_event(Stage::WAKE_DETECTED, 2);
  assert(overflow.take().seq == std::numeric_limits<uint64_t>::max());
  assert(overflow.empty() && overflow.dropped_events() == 1);
#ifdef USE_ASSIST_LIVE_WEBSOCKET
  component.set_websocket(true);
#endif
  for (int i = 0; i < 16; ++i)
    component.emit_event(Stage::WAKE_DETECTED, component.monotonic_ms());
  component.drain_worker();
  assert(test_zeroized_sizes.size() >= wipes + 17);
  assert(component.dropped_events() == 17);
  assert(test_dns_calls == 1);
  component.dump_config();
  std::cout << "PASS runtime\n";
  EmitEventAction<std::string> automation(&component);
  automation.play(std::string("synthetic-wake"));
  assert(component.take().stage == Stage::WAKE_DETECTED);
  TestComponent invalid;
  invalid.setup();
  for (const char *data :
       {"{broken}", "[]", "{\"z\":1,\"a\":2}", "{\"a\":1,\"a\":2}",
        "{\"a\": 1}", "{\"a\":1.0}", "{\"a\":NaN}", "{\"a\":-0}"}) {
    assert(!valid_event_data(data));
    invalid.emit_event(Stage::WAKE_DETECTED, 1, data);
  }
  auto dns_before = test_dns_calls;
  invalid.drain_worker();
  assert(invalid.dropped_events() == 8 && test_dns_calls == dns_before);
  assert(valid_event_data("{\"a\":\"é\",\"b\":[null,true,2],\"z\":1}"));
  assert(!valid_event_data("{\"a\":\"\xc0\xaf\"}"));
  assert(valid_event_data("{\"n\":-9223372036854775808}"));
  assert(valid_event_data("{\"n\":18446744073709551615}"));
  assert(!valid_event_data("{\"n\":18446744073709551616}"));
  std::string nested = "null";
  for (int i = 0; i < 8; ++i)
    nested = "[" + nested + "]";
  nested = "{\"a\":" + nested + "}";
  assert(!valid_event_data(nested.c_str()));

  TestComponent concurrent;
  concurrent.setup();
  std::barrier phase(2);
  auto turns = [&](int index) {
    for (uint64_t turn = 0; turn < 100; ++turn) {
      phase.arrive_and_wait();
      concurrent.command_stream_start();
      phase.arrive_and_wait();
      if (index == 0) {
        auto event = concurrent.take();
        assert(event.stage == Stage::MIC_OPEN && event.seq == turn);
        assert(concurrent.empty());
      }
      phase.arrive_and_wait();
      concurrent.command_stream_end();
      phase.arrive_and_wait();
    }
  };
  std::thread first_thread(turns, 0), second_thread(turns, 1);
  first_thread.join();
  second_thread.join();
  assert(concurrent.dropped_events() == 0);

  TestComponent initialization_failure;
  initialization_failure.set_hmac_key(key);
  initialization_failure.set_device("anonymous-satellite");
  initialization_failure.setup();
#ifdef USE_ASSIST_LIVE_WEBSOCKET
  initialization_failure.set_websocket(true);
  fail_tcp_attempts = 1;
#else
  fail_socket_attempts = 1;
#endif
  initialization_failure.emit_event(Stage::WAKE_DETECTED, 1);
  initialization_failure.drain_worker();
  assert(initialization_failure.sender_initialization_failures() == 1);
  initialization_failure.dump_config();
#ifdef USE_ASSIST_LIVE_WEBSOCKET
  test_connect_result = 0;
  for (int code : {1008, 1009}) {
    Resolver refusing_resolver;
    ResolvedEndpoint refusing_endpoint("timing-server.invalid", 8765,
                                       refusing_resolver);
    WebSocketSender refusing(refusing_endpoint);
    test_close_after_write = code;
    int writes = test_text_writes, handles = test_handle_id;
    assert(!refusing.send(packet) && !refusing.pending());
    assert(refusing.refused_events() == 1 && test_text_writes == writes + 1);
    test_frames.clear();
    test_time_us += 59999000;
    assert(!refusing.send(packet) && test_text_writes == writes + 1);
    test_time_us += 1000;
    assert(refusing.send(packet) && test_handle_id == handles + 4);
  }
  {
    Resolver pending_resolver;
    ResolvedEndpoint pending_endpoint("timing-server.invalid", 8765,
                                      pending_resolver);
    WebSocketSender waiting(pending_endpoint);
    test_auto_pong = false;
    assert(!waiting.send(packet) && waiting.pending());
    test_frames.push_back({10, "mismatch"});
    assert(!waiting.poll() && waiting.pending());
    test_frames.push_back({9, "server-ping"});
    assert(!waiting.poll() && waiting.pending());
    assert(test_last_pong == "server-ping");
    test_time_us += 1000000;
    assert(!waiting.poll() && !waiting.pending());
    test_auto_pong = true;
  }
  for (bool close_pending : {false, true}) {
    test_dns_success = true;
    TestComponent pending;
    pending.set_device("anonymous-satellite");
    pending.set_hmac_key(key);
    pending.set_server("192.0.2.1");
    pending.set_websocket(true);
    pending.setup();
    test_auto_pong = false;
    if (close_pending) {
      test_delay_hook = []() {
        test_frames.push_back({8, std::string{"\x03\xf0", 2}});
        test_delay_hook = nullptr;
      };
    }
    int writes = test_text_writes;
    pending.emit_event(Stage::WAKE_DETECTED, 1);
    pending.drain_worker();
    assert(pending.dropped_events() == 1 && test_text_writes == writes + 1);
    assert(pending.refused_events() == (close_pending ? 1 : 0));
    pending.dump_config();
    test_auto_pong = true;
  }
  test_dns_success = false;
  {
    TestComponent shutdown;
    shutdown.set_device("anonymous-satellite");
    shutdown.set_hmac_key(key);
    shutdown.set_server("192.0.2.1");
    shutdown.set_websocket(true);
    shutdown.setup();
    test_dns_success = true;
    test_auto_pong = false;
    auto wipes_before = test_zeroized_sizes.size();
    int destroyed = test_destroy_calls;
    expected_shutdown_wipes = wipes_before + 2;
    expected_shutdown_closes = destroyed + 2;
    test_task_delete_hook = check_cleanup_before_task_delete;
    shutdown_component = &shutdown;
    test_delay_hook = []() {
      shutdown_component->on_shutdown();
      assert(!shutdown_component->teardown());
      test_delay_hook = nullptr;
    };
    shutdown.emit_event(Stage::WAKE_DETECTED, 1);
    shutdown.drain_worker();
    test_task_delete_hook = nullptr;
    assert(shutdown.teardown());
    assert(test_destroy_calls == destroyed + 2);
    assert(test_zeroized_sizes.size() == wipes_before + 2);
    assert(shutdown.dropped_events() == 1);
    shutdown.emit_event(Stage::WAKE_DETECTED, 2);
    assert(shutdown.empty() && shutdown.dropped_events() == 2);
    test_auto_pong = true;
    test_dns_success = false;
  }
  {
    Resolver read_resolver;
    ResolvedEndpoint read_endpoint("timing-server.invalid", 8765,
                                   read_resolver);
    WebSocketSender reader(read_endpoint);
    assert(reader.send(packet));
    int destroyed = test_destroy_calls;
    test_read_error = true;
    assert(!reader.send(packet) && test_destroy_calls == destroyed + 2);
    test_read_error = false;
    test_time_us += 4999000;
    int calls = test_connect_calls;
    assert(!reader.send(packet) && test_connect_calls == calls);
    test_time_us += 1000;
    assert(reader.send(packet));
    for (int i = 0; i < 4; ++i)
      test_frames.push_back({10, "unsolicited"});
    assert(!reader.poll());
  }
  {
    Resolver failure_resolver;
    ResolvedEndpoint failure_endpoint("timing-server.invalid", 8765,
                                      failure_resolver);
    std::atomic<uint32_t> failures{0};
    WebSocketSender live_counter(failure_endpoint, &failures);
    fail_tcp_attempts = 1;
    assert(!live_counter.send(packet) && failures.load() == 1);
  }
  assert(test_handle_id == test_destroy_calls + 2);
#else
  {
    TestComponent shutdown;
    shutdown.set_device("anonymous-satellite");
    shutdown.set_hmac_key(key);
    shutdown.set_server("192.0.2.1");
    shutdown.setup();
    shutdown_component = &shutdown;
    test_empty_queue_hook = []() {
      shutdown_component->on_shutdown();
      assert(!shutdown_component->teardown());
      test_empty_queue_hook = nullptr;
    };
    auto wipes_before = test_zeroized_sizes.size();
    int closed_before = test_socket_closes;
    expected_shutdown_wipes = wipes_before + 2;
    expected_shutdown_closes = closed_before + 1;
    test_task_delete_hook = check_cleanup_before_task_delete;
    shutdown.emit_event(Stage::WAKE_DETECTED, 1);
    shutdown.drain_worker();
    test_task_delete_hook = nullptr;
    assert(shutdown.teardown() && test_socket_closes == closed_before + 1);
    assert(test_zeroized_sizes.size() == wipes_before + 2);
  }
  {
    std::atomic<uint32_t> failures{0};
    UdpSender live_counter(udp_endpoint, &failures);
    fail_socket_attempts = 1;
    assert(!live_counter.send(packet) && failures.load() == 1);
  }
#endif
}
