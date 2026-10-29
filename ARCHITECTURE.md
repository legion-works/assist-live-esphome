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
They append wake and voice-assistant timing `actions` without removing the stock `actions`.
The component reports media-player state changes as playback proxies, not measured sample boundaries.

The component reads the anonymous device identifier, HMAC key, and server address from ESPHome secrets.
The example and compile fixture select UDP. A second compile variant selects WebSocket.
No hardware trial result or transport selection is available.

## Source-only boundary

Build files stay in ignored directories. The repository contains no firmware image.
The compile fixture is not a configuration for a device in use.
See [the verification record](docs/verification.md) for dependency limits and test results.
