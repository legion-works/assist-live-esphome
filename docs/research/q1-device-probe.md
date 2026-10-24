# Device transport probe

Date: 2026-10-24 (UTC).

Device trial: not run (no test device at this time).

The project is experimental and has no release.
No transport selection or hardware performance result is available.

## Firmware

`tests/probes/transport.yaml` extends stock Voice PE `26.9.0` at commit `2644f4c794271d735d182ca7ebf899ed46164f4e`.
Its package, sound URLs, and `voice_kit` source use the same pins as the compile fixture.
It does not replace native audio, wake words, timers, or the media player.

The first ESPHome loop call starts the probe one time through `esphome.on_loop`.
The probe does not add to or change the stock `esphome.on_boot` automation.
Its worker runs at FreeRTOS `priority` 0 on core 0, below the `priority` 1 ESPHome loop on core 1.
Only a device test can measure its effect on native functions.

Source: ESPHome `2026.10.0`, `esphome/components/esp32/core.cpp:24-28,41-45`.
The static start guard prevents one more worker after the first loop call.
Stock `on_boot` keeps `priority: 375` and its initial sequence of steps.
The probe start does not wait for the stock `delay: 1s` and `delay: 10min`.

The device sends an authenticated `ready` datagram until an armed receiver gives it a signed command.
The command includes the random 64-bit boot identifier and the run identifier.
It cannot start a different boot or run.
After that command, the device tries these operations one time:

- Send 1000 UDP events, with sequence numbers 0 to 999, at nominal 10 ms intervals.
- Close and reopen the UDP socket 10 times. Send reconnect events 1000 to 1009.
- Send 1000 WebSocket events, with sequence numbers 1010 to 2009, at nominal 10 ms intervals.
- Close and reconnect the WebSocket 10 times. Send reconnect events 2010 to 2019.

Each reconnect trial has a 100 ms pause before it opens the socket again.
The signed reconnect time measures the open or connect operation after that pause.
UDP has no connection handshake. Its reconnect time measures socket setup, not peer availability.

These trials reopen transport sockets. They do not disconnect Wi-Fi or restart the device.
An unsuccessful send does not use its sequence number again.
The receiver reports missing events, out-of-order events, and reconnect times.

## Event authentication and time

Each event has this canonical ASCII byte order, without a newline:

```text
version|device_id|boot_id|seq|t_device_ms|stage|event_data|tag
```

`version` is `1`. The device identifier is `voice-pe-probe`.
The boot identifier has 16 lowercase hexadecimal characters.
Use unsigned decimal integers for `seq` and `t_device_ms`.

Device time comes from `esp_timer_get_time() / 1000`, not a host clock.
The `stage` field is `ready`, `probe_event`, or `reconnect`.
These synthetic probe events do not claim to measure actual voice callbacks.

`event_data` has these comma-separated fields:

```text
device,voice-pe-probe,firmware_revision,run_id,transport,trial,reconnect_ms
```

The sender and device-origin marker are explicit fields.
The firmware revision is `sha256-` plus the digest of the reviewed YAML and header before the file copy.

The run identifier has 32 lowercase hexadecimal characters.
The transport is `udp` or `websocket`.
Trial 0 identifies the numbered events. Trials 1 to 10 identify reconnect operations.

HMAC-SHA256 calculates the tag from all bytes before the last separator.
The external `assist_live_device_token` is the key. The token itself is not an event field.
The trial reader checks the tag, run, transport, device fields, and sequence range.
It refuses duplicate measurement boot/sequence pairs.

The trial reader rejects a boot identifier or firmware revision change during a trial.
One trial must contain measurements from one boot of one firmware revision.
This measurement rule is not the production server's event protocol rule.

The production server accepts an authenticated new boot identifier as a new sequence and a new clock window.
It continues to refuse incorrect tags and duplicate boot/sequence pairs.
Source: `docs/design.md` in the `legion-works/assist-live` repository.
Its device event section states: "A new boot ID starts a new sequence and clock window."
The server-side transport probe must test post-restart events with a new boot identifier.
It must check acceptance of the new sequence and a new clock window.

The `ready` handshake and the first UDP measurement share `(boot_id, seq 0)`.
The `ready` check stops before measurement collection and does not add the packet's pair to the replay set.
It does not set the trial identity or count a measurement for that handshake.
This probe-only exemption keeps sequence 0 available for the first measurement.
Tag, transport, and replay checks apply before the `ready` exemption.

Unit tests change signed fields, send events again, and send a different boot identifier.
Out-of-order unique events stay available for the order measurement.

The device-origin marker is not hardware attestation.
A party with the disposable token can make a packet.
The operator must control the flashed source and sender during the device trial.
Host-generated samples are unit-test inputs only. They are not device data.

Host arrival time uses a monotonic clock.
The report subtracts device time and uses the smallest arrival offset as the base value.
The `delay_spread_ms` value is the largest offset minus the smallest offset.
This is not absolute one-way latency. It includes scheduling and clock uncertainty.

## External secrets and file copy

The external secrets file must have five non-empty string values:

- `wifi_ssid`
- `wifi_password`
- `assist_live_device_token`: a disposable token for each run, with 32 to 128 ASCII letters, digits, hyphens, or underscores.
- `assist_live_server`: the numeric IPv4 address of the isolated receiver.
- `probe_run_id`: a new 32-character lowercase hexadecimal identifier for each run.

The `stage` command refuses repository secrets and the committed compile fixture, also a copy with the same content.
It copies the reviewed YAML, header, and external secrets into a new external directory.
The secrets copy has mode `0600`. The output directory has mode `0700`.
The command does not change repository secret files.
A new output directory is necessary.

Use an external build root:

```sh
RUNROOT="<external scratch directory>"
DEVICE_SECRETS="<external secrets file>"
uv run python tools/probe_device.py stage \
  --config tests/probes/transport.yaml --secrets "$DEVICE_SECRETS" \
  --output "$RUNROOT/q1-config"
export ESPHOME_DATA_DIR="$RUNROOT/data"
export ESPHOME_BUILD_PATH="$RUNROOT/build"
export ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT=2
uv run esphome config "$RUNROOT/q1-config/transport.yaml" >"$RUNROOT/config.log" 2>&1
uv run esphome compile "$RUNROOT/q1-config/transport.yaml" >"$RUNROOT/compile.log" 2>&1
uv run python tools/check_release.py \
  --config-log "$RUNROOT/config.log" --compile-log "$RUNROOT/compile.log"
```

The compile-only secrets in this check are obviously fake.
They use a documentation-only receiver address and a test token.
They are external scratch files, not repository files.
No upload, flash, or device connection occurred.

WARNING: Do not flash the compile-only configuration. Its network credentials and token are fake.

Results for the commands above:

```text
PASS probe staged; no upload or device connection
INFO Configuration is valid!
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS config warnings: new_warnings=0
```

The initial repository gate gave exit code 0, with 75 unit tests and a clean stock-fixture compile.
The initial Python 3.12 test run gave `75 passed`.
The initial probe test run gave `29 passed`.
Gitleaks found no leaks in the probe's source output.

The first clean probe configuration and the clean stock compile gave the same two CMake notices:

```text
CMake Warning at ESP-IDF 5.5.6 tools/cmake/build.cmake:631 (message):
CMake Warning at ESP-IDF 5.5.6 tools/cmake/project.cmake:765 (message):
  Missing kconfig option.  Re-run the build process...
```

The first notice has no message body.
The two logs also show the same legacy stack-memory key mapping below.
The same notices occur with the stock configuration, without the probe settings.
The warning checker does not check CMake notices.
The incremental probe compile gave exit code 0, with no CMake notices or compiler warnings.

## Build configuration

ESPHome `2026.10.0` selects ESP-IDF `5.5.6` for this package.
ESPHome does not include `tcp_transport` in the default component set.
The probe explicitly includes that built-in component through `framework.advanced.include_builtin_idf_components`.
Without it, the first compile stopped at this line:

```text
fatal error: esp_transport_tcp.h: No such file or directory
```

The probe explicitly sets `CONFIG_WS_TRANSPORT=y` because the WebSocket transport is necessary.
ESP-IDF `5.5.6` also enables that key by default.
Source: `components/tcp_transport/Kconfig:4-8`.

The probe sets `CONFIG_LWIP_MAX_SOCKETS=15` for the stock configuration's 13 sockets and two probe sockets.
Source: `components/lwip/Kconfig:128-134`, with a permitted range of 1 to 253.
Measure the actual heap cost of these sockets in a device test.

ESP-IDF maps `CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY` to `CONFIG_FREERTOS_TASK_CREATE_ALLOW_EXT_MEM`.
Source: `components/freertos/sdkconfig.rename:8` in `5.5.6`.
The probe does not set these keys.

The WebSocket sender explicitly sets the FIN bit with the text opcode.
The IDF `esp_transport_ws_send_raw` function does not add FIN.
Source: `transport_ws.c:98-101,372-385,440-449` in the API source below.

## Resolved configuration contract

Two tests run the pinned ESPHome configuration loader for the fixture and the probe.
They compare the resolved startup automation and all resolved configuration fields.
They also reject a top-level probe `on_boot` with the stock `priority` value.
Package resolution uses the public sources or their external cache.
The tests use the locked ESPHome package and the current Python interpreter, not a different external tool.

Only these fixture-only fields can be missing from the probe:

```text
substitutions.test_device
substitutions.assist_live_device_token
substitutions.assist_live_server
assist_live.id
external_components[2].source.type
external_components[2].source.path
external_components[2].components[0]
external_components[2].refresh
esphome.includes
esp32.framework.advanced.include_builtin_idf_components
```

The fixture's local component is a placeholder that is not active. The probe does not use it.
The last two fields are empty lists in the fixture. The probe adds their entries below.
The probe can add only these fields:

```text
substitutions.probe_revision
substitutions.probe_token
substitutions.probe_server
substitutions.probe_run_id
esphome.includes[0]
esphome.on_loop[0].then[0].lambda
esp32.framework.advanced.include_builtin_idf_components[0]
esp32.framework.sdkconfig_options.CONFIG_WS_TRANSPORT
esp32.framework.sdkconfig_options.CONFIG_LWIP_MAX_SOCKETS
```

Only these shared fields can have different values:

```text
esphome.name
esphome.build_path
wifi.networks[0].ssid
wifi.networks[0].password
wifi.use_address
```

The names and build paths identify the probe. The Wi-Fi values come from the external test credentials.
All other resolved fields must agree, also empty lists and mappings.
The stock `on_boot` mappings must agree without changes.

The startup check used a new external build root and the fake compile-only credentials.
The commands in the file-copy section gave these results with the loop start:

```text
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS config warnings: new_warnings=0
INF no leaks found
```

The current firmware revision is `sha256-c483c3d7bd2cb1e0fd2e40ce4f79b20cb7ca8791ade325ad9d200184a2087463`.
The unmodified tests and complete repository gate gave:

```text
probe suite: 31 passed in 12.81s
task check: 77 passed in 19.14s
Python 3.12: 77 passed in 17.91s
```

The source output contains `StartupTrigger(375.0f)` and a different `LoopTrigger` for the probe start.
The SDK configuration output has `CONFIG_FREERTOS_NUMBER_OF_CORES=2`.
The stock boot `delay` steps are not in the probe's loop automation.
Device trial: not run (no test device at this time).

## Subsequent device trial

- [ ] Supply a test Voice PE and an isolated receiver network.
- [ ] Make disposable credentials for each run in an external secrets file.
- [ ] Copy and compile that configuration. Check the two warning logs.
- [ ] Get explicit operator approval to flash the test device.
- [ ] Upload the approved image. Keep the previous device configuration for rollback.
- [ ] Start the armed receiver on the isolated network with the command below.
- [ ] Examine the raw authenticated packets and the report for the two transports and all 10 reconnect trials.
- [ ] Test native voice, wake words, timers, and media playback while the probe runs.
- [ ] Select a transport only after the device data is sufficient.

The UDP receiver and WebSocket endpoint use port `8765`. The WebSocket path is `/q1`.
The armed receiver runs for 120 seconds by default.
It writes `q1-<run_id>.jsonl` adjacent to the external secrets file, with mode `0600`.
A new raw file is necessary. Keep raw data external to the repository.

The command below is a future step, not a result:

```sh
uv run python tools/probe_device.py --arm --events 1000 --reconnects 10 \
  --secrets "$DEVICE_SECRETS" --report docs/research/q1-device-probe.md
```

That command replaces this report. Keep a copy of the procedure before a device run.
Use `--bind` to select the isolated receiver interface and `--seconds` to change the bounded capture period.
Use `--sample`, not `--arm`, to read recorded JSONL data without network access.
Sample reports state that the device trial did not run.

## Sources

Access date: 2026-10-24 (UTC).

- Stock Voice PE package and board configuration: <https://github.com/esphome/home-assistant-voice-pe/blob/2644f4c794271d735d182ca7ebf899ed46164f4e/home-assistant-voice.yaml>
- ESP-IDF WebSocket transport, with client masking, upgrade checks, and explicit FIN opcode: <https://github.com/espressif/esp-idf/blob/v5.5.2/components/tcp_transport/transport_ws.c>
- ESP-IDF transport API: <https://github.com/espressif/esp-idf/blob/v5.5.2/components/tcp_transport/include/esp_transport_ws.h>
- ESPHome built-in component exclusions and configuration: <https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/esp32/__init__.py> (`DEFAULT_EXCLUDED_IDF_COMPONENTS:226-285`, explicit inclusion at lines 3148-3150).
- ESPHome loop task `priority` and core: <https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/esp32/core.cpp> (lines 24-28 and 41-45).
- ESPHome package merge: <https://github.com/esphome/esphome/blob/2026.10.0/esphome/config_helpers.py> (lines 77-98).
- ESP-IDF `5.5.6` Kconfig sources: <https://github.com/espressif/esp-idf/blob/v5.5.6/components/tcp_transport/Kconfig> and <https://github.com/espressif/esp-idf/blob/v5.5.6/components/lwip/Kconfig>.
- ESP-IDF key mapping: <https://github.com/espressif/esp-idf/blob/v5.5.6/components/freertos/sdkconfig.rename>.

The compile gate checks the installed ESP-IDF version. The API source above is not a toolchain pin.
