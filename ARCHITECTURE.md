# Architecture

## Component boundary

ESPHome loads `components/assist_live/__init__.py` as an external component.
The schema has these necessary fields: `device`, `hmac_key`, `server`, `transport`, and `media_player_id`.
It accepts `port` (default `8765`), an identifier, and the standard component options.
ESP32 with the ESP-IDF framework is necessary.
`to_code(config)` makes `assist_live::AssistLiveComponent` and calls `register_component`.

The C++ class extends `Component`.
Its `setup()` makes a 16-event queue, starts a sender worker, and adds the media-player state callback.
The worker signs events with HMAC-SHA256 and sends them through the selected UDP or WebSocket transport.
Callbacks enqueue events without a wait. Resolution, signing, and network operations stay in the worker.
Its `dump_config()` prints the transport and counters, not the key.

See [device timing events](docs/protocol.md) for retry, shutdown, and signal limits.

## Stock package

The example and compile fixture import the official Voice PE package by commit.
They add Wi-Fi secrets, a device name, and the local component.
They pin the stock `voice_kit` source and sound URLs without changes to the stock functions.
The shared wake handler adds timing before the stock decisions and keeps their order.
The voice-assistant timing `actions` follow the stock `actions`.
The component reports media-player state changes as playback proxies, not measured sample boundaries.

The component reads the anonymous device identifier, HMAC key, and server address from ESPHome secrets.
The example and compile fixture select UDP. A second compile variant selects WebSocket.
No hardware trial result or transport selection is available.

## Reply wake window

`examples/wake-word.yaml` applies the stock Very sensitive cutoffs while the media player announces.
This includes voice-assistant replies and standalone announcements, not ordinary media playback.
The cutoffs are 143 for Okay Nabu, 212 for Hey Jarvis, and 237 for Hey Mycroft.
The Stop word model, timer functions, mute, and the stop-on-wake branch stay unchanged.
A wake during a reply stops that reply. It does not start a new command.

The sensitivity select keeps the current option, also after a change during the window.
Its first value callback adds one media-player state subscriber.
The subscriber does not replace the stock media or boot `actions`.
`ReplyWakeWindow` supplies one local cutoff table. A resolved-config test compares it with the pinned stock select.

After playback ends, one restartable script waits for VA `IDLE`, then waits 1000 ms before it uses the current option again.
The wait runs only in a reply window. VA `on_idle` fires only in continuous mode in the pinned ESPHome version.
A follow-up `on_listening` signal releases the previous reply without waiting for the new turn to end.
A new announcement cancels the previous tail.
If VA does not go to `IDLE` in 30 s after playback, the script logs the timeout and uses the selected cutoffs again.

This limit does not end the window during an announcement that continues to play.
Selecting Very sensitive makes no cutoff change at the window edges.

Each applied cutoff change logs the model, integer value, and `reason` at INFO level.
The `reason` values are `reply window start`, `reply window end`, and `select changed`.
This policy increases sensitivity only in the reply window. Incorrect detections can stop replies.
Device tests must measure wake detection and the `false-accept rate`. Native tests do not prove acoustic performance.

Design source: [assist-live `docs/design.md`, Satellite pre-roll, Wake word during a reply](https://github.com/legion-works/assist-live/blob/main/docs/design.md#satellite-pre-roll).

## Source-only boundary

Build files stay in ignored directories. The repository contains no firmware image.
The compile fixture is not a configuration for a device in use.
See [the verification record](docs/verification.md) for dependency limits and test results.
