# Device timing events

The project is experimental and has no release.

## Server contract

The [server protocol](https://github.com/legion-works/assist-live-server/blob/a888c3b5cc34e14f3ee9efb0bf76156df908de35/docs/protocol.md) is the authority for encoding, authentication, and transport routes.
This document gives firmware configuration and signal limits, not a second protocol specification.
The firmware and server use the same `device-vectors.json` bytes.
Their SHA-256 is:

```text
b74cf28042f22e9bd85520a864f335e0f61fddbd99559ce458f78cd5b540bc89
```

## Configuration and credentials

Keep actual credentials in an external `secrets.yaml`.
Set `assist_live_device` to the provisioned anonymous satellite key.
Do not use the node name, a MAC address, or an HA entity name.
Set `assist_live_hmac_key` to the hexadecimal device secret from the server credential file.
The firmware decodes its 64 hexadecimal characters into 32 key bytes.

Do not use the different integration-access token as this key.
Only the trial probe uses `assist_live_device_token`.
That token is not necessary for the production example.

Set `assist_live_server` to an IPv4 address or a host name.
The worker resolves host names to IPv4 addresses, not the audio callback or the ESPHome loop.
The cache lasts 60 seconds. A send failure clears the cache.

A resolution or transport failure has a five-second retry interval.
The component drops events during that interval and counts the drops.

HTTP `503` uses retry intervals of 5, 10, 20, 40, and then 60 seconds.
The maximum interval stays at 60 seconds until a subsequent event receives transport confirmation.
Close codes `1008` and `1009` increment the refusal counter and write a warning.
They select a 60-second retry interval for subsequent events. The refused event is not sent again.

The `transport` option is necessary and has no default.
The example selects `udp`. The second compile fixture selects `websocket`.
Only a WebSocket build adds the `tcp_transport` IDF component.
The node name, local component path, and transport selection can be different in the example and base fixture.
All other settings must be the same.

The default port is `8765`. Set `port` if the server uses a different port.
Use an isolated network. The two candidates do not encrypt timing events.

Build output contains the key and the Wi-Fi password. A text search cannot always find them.
Keep C++ build output, logs with secrets enabled, and firmware images private.
Do not publish them. The key has no getter, entity, or diagnostic field.

The configuration dump prints the transport, drop count, refusal count, and sender initialization failure count.
The failure site updates the initialization counter directly, without a subsequent event.
The `_DeviceKey` value prints only `[redacted]`, with or without `--show-secrets`.
Its YAML representation applies only to that value type.

The stock ESPHome dumper can put Wi-Fi password bytes between terminal control codes after package loading.
These bytes stay in captured output. This upstream behavior does not follow the component's key-output rule.
Keep all stock configuration output private.

## Native signal connections

The configuration appends a timing `action` to the stock wake callback.
It keeps all stock wake `actions`, with mute, timer, and stop-word behavior.

`mic_open` uses the public `voice_assistant.on_start` callback as a `proxy`.
It occurs one time for each pipeline run, not for each microphone hardware start.
The component clears that guard at `voice_assistant.on_end`.
An always-running wake microphone does not cause a boot-time `mic_open` event.

The pinned ESPHome source sends command audio in `STREAMING_MICROPHONE` at lines 380 to 403.
Its `state_` has `protected` access, and it has no public getter for that state.
The public `on_start` callback comes from the deferred pipeline-start notification at line 785.
`data.source` names that callback. It does not claim a first-sample or first-packet measurement.
The device trial must measure the interval between this proxy and the actual command-audio stream start.

The component adds a state callback to the stock media player.
It sends playback boundaries only when the active state changes.
These events always have `quality: proxy` and `source: media_player.on_state`.
They do not measure the first or last output sample.

The `measured_sample_boundary(started, device_ms)` hook is for an externally validated sample callback.
No stock callback calls this hook.
Call it on the ESPHome main loop, with the initial sample timestamp from the device monotonic clock.
An audio-task callback must defer the call to that loop.
Calibration does not change a proxy to a measured event.

## Automation and runtime limits

`assist_live.emit_event` accepts `id`, `stage`, optional `device_ms`, and a static JSON object in `data`.
Without `device_ms`, it reads `esp_timer_get_time()` in monotonic milliseconds.
An explicit timestamp must use that same device clock, not host or UTC time.
Code generation sorts JSON object keys, keeps UTF-8, and refuses non-finite values and data above 256 bytes.

The automation cannot claim `quality: measured`.
Only the different sample hook supplies that quality.

C++ callers must run on the ESPHome main loop. `command_stream_end` can also run on the API task.
The turn guard uses an atomic state change because the API task can close a turn.
The sender worker parses `data`, sorts object keys, and compares the canonical bytes with the input.
It drops and counts malformed JSON, duplicate keys, and non-canonical values before signing.
Only JSON strings can contain whitespace.

Metadata can contain strings, null, booleans, 64-bit integers, objects, and arrays.
The maximum nesting depth is eight. Do not use floating-point metadata.
Python and ArduinoJson use different float formats. The configuration validator applies the same restrictions.
JSON parsing stays in the worker, not the audio path.

A sender initialization failure increments a different counter and writes a warning without packet or key bytes.
The worker retries initialization after five seconds. It drops events during that interval.
The two transport variants use this retry rule.

The authoritative public-data checker is in the assist-live integration repository.
It examines private paths, private addresses, and Git history. CI downloads that file from `main` and uses Python 3.14.
If `../assist-live/tools/check_public_tree.py` is a file, `task check` uses it.
Without it, the task prints `NOT CHECKED public tree`.

An external `PRIVATE_DENYLIST` is optional. An unset value gives `NOT CHECKED private denylist`.

Each start uses eight hardware-RNG bytes for a new boot identifier.
One sequence increases for all events in that boot, with dropped events.
Sequence exhaustion stops telemetry until restart. It does not use a sequence again in the same boot.
Callbacks copy events into a 16-item queue with 0 wait time.

The worker runs on core 0 at `priority` 0. It signs and sends the events, not on the audio path.
WebSocket connect and write calls have 250 ms and 50 ms timeouts in that worker.

WebSocket control-frame reads use a `0 ms` timeout and a 125-byte buffer.
Each poll reads at most four frames. More frames close the transport, as does a frame that is not full.
With no queued event, the WebSocket worker polls at intervals of at most 20 ms, subject to task scheduling.
After a close or error, the worker calls `esp_transport_destroy` for each transport.
The next connection uses new transport objects.

No event retry queue can increase without a limit.

The WebSocket sender keeps at most one event pending after a local write.
It sends an eight-byte ping after that event and waits for a pong with the same payload.
The read timeout stays at `0 ms`.
The server processes the event result before its next receive call. A refusal closes the connection before that pong.

A close, send failure, or one-second confirmation timeout drops and counts the pending event one time.
Other queued events stay in the bounded queue until confirmation or failure.
An event has no retry queue. The sender replies to server ping and close frames.
Transport confirmation is not a server acknowledgement or proof of durable storage.
With a missing pong, the counter can include an event that the server accepted.

The codec clears its HMAC digest after use, also after a signing failure.
The key setter clears its temporary copy.

`on_shutdown()` tells the worker to stop. `teardown()` stays `false` until the worker stops.
The worker closes its socket or transports and clears the stored key before it stops.
With no worker, the shutdown hook clears the key directly.
The two queue variants use a 20 ms receive timeout so shutdown can wake an empty worker.

`Application::safe_reboot()` waits through `teardown()`.
`Application::reboot()` does not wait for the worker.
A resolver wait or the shutdown deadline can stop cleanup before it is complete.

UDP has no server acknowledgement.
A local send alone cannot prove that the server accepted an event.
The counter includes queue overflow, unavailable workers, resolution failures, and local send failures.
It cannot count UDP packets missing at the server without a local error.

Device trial not run: no test device at this time.
Compile and native simulation results do not prove unchanged native-function latency on hardware.

## Sources

Access date: 2026-10-25 (UTC).

- [ESPHome 2026.10.0 command-audio streaming](https://github.com/esphome/esphome/blob/704551a6c93c29a311802f7ee97d67a9e9bce718/esphome/components/voice_assistant/voice_assistant.cpp#L380-L403), with the public start callback at line 785.
- [ESPHome 2026.10.0 voice-assistant state](https://github.com/esphome/esphome/blob/704551a6c93c29a311802f7ee97d67a9e9bce718/esphome/components/voice_assistant/voice_assistant.h#L329), with public callbacks at lines 198 to 218.
- [ESPHome 2026.10.0 secret output](https://github.com/esphome/esphome/blob/704551a6c93c29a311802f7ee97d67a9e9bce718/esphome/yaml_util.py#L1335-L1341): `represent_secret` sends the secret name, not its value.
- [ESPHome 2026.10.0 sensitive-value output](https://github.com/esphome/esphome/blob/704551a6c93c29a311802f7ee97d67a9e9bce718/esphome/yaml_util.py#L1364-L1375): `represent_sensitive` can write value bytes between terminal control codes.
- [ESP-IDF 5.5.6 hardware RNG](https://github.com/espressif/esp-idf/blob/880a203ae603d08a94d06aa01e0d6761958e5e9e/components/esp_hw_support/include/esp_random.h#L35-L43): `esp_fill_random` fills a buffer through the hardware RNG.
- [ESPHome 2026.10.0 lifecycle hooks](https://github.com/esphome/esphome/blob/704551a6c93c29a311802f7ee97d67a9e9bce718/esphome/core/component.h#L177-L191): `on_shutdown()` and `teardown()` are virtual lifecycle methods.
- [ESPHome 2026.10.0 restart paths](https://github.com/esphome/esphome/blob/704551a6c93c29a311802f7ee97d67a9e9bce718/esphome/core/application.cpp#L293-L315): `safe_reboot()` waits for teardown. `reboot()` does not.
- [ESP-IDF 5.5.6 WebSocket receive path](https://github.com/espressif/esp-idf/blob/880a203ae603d08a94d06aa01e0d6761958e5e9e/components/tcp_transport/transport_ws.c#L690-L748): the caller can receive control frames and select the read timeout.

The RNG source at lines 20 to 22 specifies enabled Wi-Fi or Bluetooth for values with physical entropy.
The component starts after Wi-Fi setup. The stock Voice PE package enables the radio.
