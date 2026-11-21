# Architecture

## Component boundary

ESPHome loads `components/assist_live/__init__.py` as an external component.
The schema has these necessary fields: `device`, `hmac_key`, `server`, `transport`, and `media_player_id`.
It accepts `port` (default `8765`), an identifier, optional `pre_roll` and `diagnostics` sections, and the standard component options.
ESP32 with the ESP-IDF framework is necessary.
`to_code(config)` makes `assist_live::AssistLiveComponent` and calls `register_component`.

The C++ class extends `Component`.
Its `setup()` makes a 16-event queue, starts a sender worker, and adds the media-player state callback.
The worker signs events with HMAC-SHA256 and sends them through the selected UDP or WebSocket transport.
Callbacks enqueue events without a wait. Resolution, signing, and network operations stay in the worker.
Its `dump_config()` prints the transport and counters, not the key.

See [device timing events](docs/protocol.md) for retry, shutdown, and signal limits.
See [microphone history](docs/pre-roll.md) for the optional virtual microphone, replay limits, and turn boundaries.
See [device diagnostics](docs/diagnostics.md) for optional completed-turn measurements and timing-sender counters.

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

`examples/wake-word.yaml` has two experimental substitutions, `assist_live_reply_window` and `assist_live_reply_restart`. Enable them independently.
Each defaults to `'false'` in the shared handler, base example, and pre-roll overlay.
Keep them off until device tests give satisfactory results.
Config-time includes do not load disabled packages.
With the two options off, tests remove the timing and arm slots, then compare the complete wake handler with pinned stock.

With `assist_live_reply_window: 'true'`, the overlay applies the stock Very sensitive cutoffs while the media player announces.
This includes voice-assistant replies and standalone announcements, not ordinary media playback.
Timer rings and device sounds are announcements and also open the window.
The cutoffs are 143 for Okay Nabu, 212 for Hey Jarvis, and 237 for Hey Mycroft.

The Stop word model, timer functions, and mute decisions stay unchanged.
With `assist_live_reply_restart: 'true'`, a named wake during a VA reply stops it and starts a new wake turn after VA goes to `IDLE`.
The handler identifies a VA reply with three conditions: VA runs, the stock phase is replying, and the media player announces.
Stop is not a named wake for this decision.

The stock `is_running` condition includes all non-`IDLE` states, also listening, thinking, and start/stop states.
These other states keep the stock stop-only decision. A standalone announcement also keeps its stop-only decision.

The sensitivity select keeps the current option, also after a change during the window.
Its first value callback adds one media-player state subscriber.
The subscriber does not replace the stock media or boot `actions`.
`ReplyWakeWindow` supplies one local cutoff table. A resolved-config test compares it with the pinned stock select.

The playback falling edge starts a 2000 ms tail, supplied by `ReplyWakeWindow::REPLY_TAIL_MS`.
The active tail script checks and applies cutoffs at `REPLY_CHECK_MS` intervals of 25 ms.
The deadline and scheduler use the same `millis_64()` clock.
A check before the deadline does not end the script. The next check closes the window.

A new listening turn does not move the deadline. VA can stay busy.
A new announcement replaces the previous tail.
The software bound is the last playback end plus 2000 ms and one check interval, with scheduler latency.
The script does not poll while no window is active. It does not wait 30 s for VA.

Selecting Very sensitive makes no cutoff change at the window edges.

Each applied cutoff change logs the model, integer value, and `reason` at INFO level.
The `reason` values are `reply window start`, `reply window end`, and `select changed`.
This policy increases sensitivity only in the reply window. Incorrect detections can stop replies.
Device tests must measure wake detection and the `false-accept rate`. Native tests do not prove acoustic performance.

In the current device checks, a wake word in the middle of a reply usually gives no detection.
The detector accepted 0 of 4 cases with 2 s or more of reply left.
This is a small test set, not a general acoustic guarantee.

## Reply wake restart

The wake timing event comes first, before stop, sound, or wait `actions`.
One pending request keeps its detection time and captures microphone history before it stops the reply.
The wait for VA and the media player to stop has a 500 ms limit.
ESPHome stops the media player, then changes `STREAMING_RESPONSE` to `RESPONSE_FINISHED` and `IDLE` in subsequent loop operations.
This is not a fixed-duration stop. If the wait expires, the script logs it, clears the pending history, and does not start.

At `IDLE`, the usual pre-start arm uses the saved detection time and audio.
The new turn gets the lookback before detection and the continuous bridge through stop and start.
The same 1000 ms total limit applies. The component counts each frame that it removes from the oldest end.
`pre_roll_ms` reports only history actually sent to VA.

With the wake sound on, the turn gets the same sound interval and no history, as in an `IDLE` wake turn.
The 1000 ms detection-to-start limit applies only to a turn with history.
With the wake sound on, a check after the chime that is late does not cancel the request.

After the chime, the script checks timer and announcement state again before it starts VA.
If one becomes active, it cancels the pending request and history without a start.

A second named wake during the wait does not queue one more turn.
Stop during the wait cancels the pending request and its history, then follows the stock stop branch.
If a timer rings during the wait, a wake word stops it as in the stock timer branch.
That wake word also cancels the pending request, because a stock wake word on a ringing timer starts no turn.

Mute, error, and disconnect also cancel the pending request.
An error from the stopped reply pipeline thus also cancels the request. A device test must show if HA sends such an error.
Each restart logs `detection_to_idle_ms` and `detection_to_start_ms`.
See [microphone history](docs/pre-roll.md#reply-stop-and-restart) for the buffer rules.

Design source: [assist-live `docs/design.md`, Satellite pre-roll, Wake word during a reply](https://github.com/legion-works/assist-live/blob/main/docs/design.md#satellite-pre-roll).

## Source-only boundary

Build files stay in ignored directories. The repository contains no firmware image.
The compile fixture is not a configuration for a device in use.
See [the verification record](docs/verification.md) for dependency limits and test results.
