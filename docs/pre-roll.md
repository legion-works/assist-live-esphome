# Optional microphone history

The project is experimental and has no release.
The default example has no microphone history.
Keep this option off until a device test gives satisfactory results.

## Configuration

`examples/voice-pe-pre-roll.yaml` adds `examples/pre-roll.yaml` to the default example.
`tests/probes/pre-roll.yaml` supplies the same option for a device test with external secrets.
It does not change the transport probe protocol.
Keep the include paths and the local component path correct in an external copy.
Do not flash the compile fixture or use its fake credentials on a device.

```yaml
assist_live:
  pre_roll:
    id: pre_roll_mic
    microphone: i2s_mics
    length_ms: 250
    wake_sound: wake_sound
```

`microphone` identifies the physical source: 16 kHz, 32-bit stereo PCM.
`wake_sound` identifies the stock wake-sound switch. This ID is mandatory.
`length_ms` must be an integer from 1 through 1000.
Its provisional default is 250 ms, a small initial interval for device calibration, not a measured wake-word interval.
The default configuration has no `pre_roll` section.

The component sets only the `voice_assistant.microphone` ID values during `FINAL_VALIDATE_SCHEMA`.
The stock two-source configuration is mandatory: physical `channels` 0 and 1, 16-bit output, and `gain_factor` 1.
The source count, source IDs, `channels`, and `gain_factor` must stay unchanged.
A change stops configuration with a named error.
`micro_wake_word`, its stop model, and other microphone users stay on the physical microphone.

The stock anonymous mute `actions` continue to select the physical microphone.
The virtual microphone is a public C++ `microphone::Microphone` subclass.
Its ID is not a candidate for automatic microphone selection.
Only the component connects VA to that ID.

The public ESPHome 2026.10.0 `FINAL_VALIDATE_SCHEMA` context supplies the configuration.
The examined core validators do not change microphone IDs.
After an ESPHome upgrade, the resolved-config and generated-code checks must give satisfactory results before use.

## Turn selection

The overlay keeps the stock mute, timer, stop, announcement, and wake-sound decisions.
It adds one arm call in the usual wake-to-start branch.
The `then:` mapping replaces the stock list.
A resolved-config test removes that one call and compares the complete handler with the default handler.

A button, follow-up, or announcement does not arm history.
An arm expires after one second.
At microphone start, the wake-sound switch must be off, or the turn gets no history.

Mute clears the PCM queue and the arm. The component keeps no new history while mute is active.
Unmute cannot use previous history.
Stop, error, disconnect, and shutdown clear the queue.

## Audio order and limits

Wake detection holds the start index of the recent stereo history.
New frames append after that index, through VA microphone start and the HA handshake.
The two signals use one frame index and one queue.
History ends at the VA microphone-start index. Live audio starts at the next index.
No sample is missing or duplicated at that boundary when the queue does not overflow.

The configured interval is before detection.
The detection-to-start bridge also counts as history.
Total history has a 1000 ms maximum, with that bridge.
If necessary, microphone start removes the oldest frames and counts `trimmed_ms`.
The newest history stays continuous with live audio.

Public wake detection supplies no acoustic word-end timestamp.
Device calibration must select an interval that starts near the acoustic wake-word end.
An interval that is too long can send the wake-word tail to STT.
History stays in RAM. It does not go to flash or an `idle` network stream.

## Pacing and overflow

The public `on_listening` signal enables replay after HA starts STT.
Replay sends a maximum of 16 ms of stereo frames for each operation, at a maximum rate of 2x.
The public API connection must report write readiness.
The component also limits the estimated increase in backlog to 256 ms:

```text
frames handed to VA <= 16 * (elapsed_ms_since_VA_microphone_start + 256)
```

The formula uses only 1x VA drain, the rate necessary for live audio.
The stock rings each hold 512 ms. The estimated increase in backlog is 256 ms or less.
With history above 256 ms, this limit can keep some live audio in the component queue until turn end.
When the queue becomes empty, live callbacks go directly to VA, as in the stock path.

The queue holds the configured interval plus 1000 ms.
A long stall drops the oldest full 16 ms units and increments the overflow and dropped-frame counters.
Dropped history does not contribute to `pre_roll_ms`.
A satisfactory device test must have 0 queue overflows and 0 dropped frames.

No public API reports accurate VA ring occupancy or gives a record of each audio-consumption operation.
The estimate is not proof that a stock ring cannot overflow during a network stall.
A future upstream public space or consumption callback can remove that uncertainty.
The component does not access `protected` VA members.

## Events, logs, and RAM

`mic_open.data.pre_roll_ms` is an integer in the HMAC-signed event data.
It gives the length of historical audio actually handed to VA, from 0 through 1000 ms.
A turn without history gives 0. The proxy timestamp continues to identify `voice_assistant.on_start`.
For a history turn, the component sends the event after history replay ends, or when the turn stops.
Thus, dropped history does not count in the event value.

Debug logs give device monotonic times for wake detection and VA microphone start.
Each stopped turn logs `history_samples`, `live_samples`, `overflow_count`, `dropped_ms`, and `trimmed_ms`.
The sample counts refer to frames for each signal, not the sum of the two signals.
Logs contain no PCM content.

The log gives queue time intervals at three points:

- First live handoff.
- History end.
- Turn end.

The first two values are `-1` before these points.
If `passthrough_reached` is 1, live callbacks went directly to VA.
Measure these intervals in the device test, especially with history above 256 ms.

At 16 kHz, 32-bit stereo, one second of history costs 128000 PCM bytes.
The one-second queue margin makes the maximum queue allocation 256000 bytes.
The 250 ms setting uses 160000 PCM bytes.
The ESPHome `RAMAllocator` prefers PSRAM and falls back to internal RAM.
There is also a 2048-byte output-vector reserve, a 2048-byte loop stack buffer, and small state objects.
The component does not replace or borrow the stock VA or wake-word buffers.

## Device test

The native tests use numbered synthetic stereo frames, not recorded voice.
A device test must measure command coverage, time intervals, memory, and native-function behavior.
Use approved synthetic or licensed audio for continuous wake-and-command trials.
Measure acoustic wake end independently of the detection log.
Check the two HA signal selections and the history-to-live boundary.

Test wake sound on and off, mute, button starts, follow-ups, announcements, timer stop, and the stop word.
Test slow API connections, stalled connections, and connections after a stall.
Reject a usual run with dropped frames, queue overflow, missing command onset, or a changed stock function.
The native and compile gates do not include a device test.

## Sources

Source access date: 2026-10-29 (UTC).

- [Stock wake handler](https://github.com/esphome/home-assistant-voice-pe/blob/2644f4c794271d735d182ca7ebf899ed46164f4e/home-assistant-voice.yaml#L1739-L1780): the usual branch starts VA after the mute, timer, stop, and announcement decisions.
- [VA microphone enable](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L315-L356): the loop starts microphone sources after the start request changes state at lines 683 to 695.
- [Public STT signal](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L794-L796): STT start calls `on_listening`.
- [Configuration validation](https://github.com/esphome/esphome/blob/2026.10.0/esphome/config.py#L1239-L1244): the public context holds the validated result object.
- [Code generation](https://github.com/esphome/esphome/blob/2026.10.0/esphome/__main__.py#L797-L808): `to_code` receives sections from `CORE.config`, which line 2749 sets to the validated configuration.
