# Optional device diagnostics

The project is experimental and has no release.
The default example has no diagnostic entities from `assist_live`.
`examples/voice-pe-pre-roll.yaml` and its compile fixture enable the optional measurements.
Home Assistant lists these entities in the device diagnostics.
Its recorder configuration controls history storage.

## Configuration

Each key is optional. Each configured key makes one entity.
Use the public ESPHome sensor options, such as `name`, for each numeric value.
The two Boolean values use public binary-sensor options.
All entities default to `entity_category: diagnostic`.

```yaml
assist_live:
  diagnostics:
    pre_roll_ms:
      name: "Pre-roll sent"
    replay_gate_delay_ms:
      name: "Replay gate delay"
    events_sent:
      name: "Timing events sent"
```

For history measurements, `pre_roll` is mandatory in the same component configuration.
See [microphone history](pre-roll.md) for that configuration.
Sender counters work without microphone history.
An empty or missing `diagnostics` mapping makes no entities.

With `transport: websocket`, the component accepts these two keys:

```yaml
assist_live:
  transport: websocket
  diagnostics:
    connected:
      name: "Timing transport connected"
    events_confirmed:
      name: "Timing events confirmed"
```

On UDP, each of these keys stops configuration with `requires websocket transport`.
UDP is connectionless. A complete UDP write does not prove that the server received the event.
There is no text sensor because the component measures no diagnostic text value.
No entity contains an identifier, key, address, transcript, or PCM content.

## Completed-turn measurements

The component makes one snapshot before it clears a finished logical turn.
Its main loop publishes this snapshot. The audio callback does not publish entities.
Numeric turn sensors use `state_class: measurement` and `accuracy_decimals: 0`.
Time sensors use `ms`.
Before the first finished turn, these entities have no value.

| Key | Meaning |
| --- | --- |
| `pre_roll_ms` | Historical audio actually handed to VA in the last turn. An unarmed turn gives 0. |
| `replay_gate_delay_ms` | Time from wake detection to the public STT-start replay gate. This is not microphone-start time. |
| `history_trimmed_ms` | Oldest history removed at the replay gate to keep the total history at or below its limit. |
| `overflows` | Queue overflow operations in the last turn, not a lifetime counter. |
| `dropped_ms` | Audio removed by queue overflow in the last turn. |
| `first_live_queue_ms` | Component queue time at the first live handoff. |
| `history_end_queue_ms` | Component queue time when the historical handoff ends. |
| `turn_end_queue_ms` | Component queue time immediately before logical turn cleanup. |
| `passthrough_reached` | Binary state: the turn used pass-through for live audio. |

An unreached gate or handoff point gives an unknown value, not a negative time.
Queue times refer only to the component queue, not the stock VA rings or network latency.
The frame-to-time conversion uses the component's 16 kHz measurements and integer milliseconds.
Mute does not remove the count of historical frames sent before mute.

Turn sensors default to `force_update: true` so equal results also supply history updates to Home Assistant.
Binary states show the last result, not a turn counter.
These are last-value entities, not a durable event queue.
If multiple turns finish before the main loop publishes, it keeps only the latest snapshot.
API batching can also merge state updates during congestion.

## Counters and transport state

Counters use `state_class: total_increasing` and no physical unit.
They start at 0 after boot.
The component samples them at most one time each second from its main loop.
It publishes only values that changed, plus the first value after boot.
It compares counter integers before the sensor float conversion.
The optional `connected` binary sensor uses the same interval and the `connectivity` device class.

If public `has_state() == false`, the next eligible sample publishes the entity again.
This does not remove the one-second rate limit.
An API reconnect does not clear entity state.
ESPHome sends the current state to each API client when it subscribes.
The component does not transmit unchanged values to all clients on reconnect.

| Key | Meaning |
| --- | --- |
| `events_sent` | Event writes with a result equal to the complete packet length from the UDP socket or WebSocket transport. Control frames do not count. |
| `events_confirmed` | WebSocket events followed by a received pong with the same payload as the confirmation ping. |
| `events_dropped` | The dropped-event counter, with queue, validation, transport, and confirmation failures. |
| `events_refused` | The WebSocket refusal counter for close codes `1008` and `1009`. It stays 0 on UDP. |
| `sender_initialization_failures` | The transport-initialization failure counter. |
| `expired_gates` | Finished turns with a replay gate above the 1000 ms limit. `pre_roll` is mandatory. |
| `connected` | Current WebSocket connection state. This is not proof that the server is healthy. |

A complete WebSocket write increments `events_sent` also if its subsequent confirmation is unsatisfactory.
An unmatched pong, timeout, or refused event does not increment `events_confirmed`.
A pong with the same payload is not proof of durable server storage.
The connection becomes known after the main-loop sample.
No new transport probe, retry, or network request supplies these diagnostics.

## Why states replace log capture

The previous per-turn log defect was a lifecycle mismatch, not a cause to increase log volume.
The pinned VA can finish a response without stopping its microphone sources.
An enabled stock source does not forward the next microphone start.
The component finishes logical turns independently of source start and stop.
See [logical turn boundaries](pre-roll.md#logical-turn-boundaries) for the repair and sources.

The API log path is also best-effort and does not retry a full write buffer.
Sensor state stays in the entity, and the public API state path can defer a send until the buffer has space.
After reconnect, Home Assistant can read the latest state without a previous log capture.
This does not supply all previous turns during a disconnected interval.
No logger setting or log volume changes are necessary.

## Sources and checks

Source access date: `2026-11-01` (UTC). Pinned ESPHome version: `2026.10.0`.

- [Sensor state storage](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/sensor/sensor.cpp#L116-L124).
- [Sensor API state path](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/api/api_connection.cpp#L694-L705).
- [Deferred state send](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/api/api_connection.cpp#L2449-L2499).
- [Public entity state check](https://github.com/esphome/esphome/blob/2026.10.0/esphome/core/entity_base.h#L146-L149).
- [API state subscription and initial replay](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/api/api_connection.h#L293-L299).
- [Initial state handlers](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/api/subscribe_state.h#L13-L15) send sensor and binary-sensor states to the subscribed client.
- [Best-effort log send](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/api/api_server.cpp#L765-L776).

Native tests check snapshots, main-loop publication, rate limits, and write/confirmation counts.
Resolved-config tests check optional entities, metadata, transport restrictions, and the unchanged default example.
Firmware compiles do not prove device behavior or Home Assistant recorder policy.
No device test is part of these checks.
