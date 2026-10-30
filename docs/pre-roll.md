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
It puts the timing `action` first, before the wake sound and its 300 ms interval.
It adds an arm call immediately before `voice_assistant.start`, after that interval.
One call immediately after that start connects the arm to the wake request.
The `then:` mapping replaces the stock list.

A resolved-config test removes only these two calls and the first timing `action`.
It then compares the complete handlers.

A button, follow-up, or announcement does not arm history.
The wake-sound switch must be off to make an arm.
At the replay gate, the wake-sound switch must be off, or the turn gets no history.

The post-start call checks public VA `is_running()` after the synchronous wake request.
The pre-start call accepts an arm only while VA is in `IDLE`.
Thus, a wake handler after a sound interval cannot arm an active button request.
An arm without that paired call cannot give history to a button start.
If VA does not start, the component clears the arm and its PCM.

The replay gate is `on_listening`, the public STT-start signal after the HA handshake.
The component holds all frames from the arm until this gate, also with microphone sources that stay enabled.
The two VA rings have empty buffers before this signal.
The component sends no historical frame to VA before this gate.

The detection-to-gate interval has a 1000 ms limit.
At 1001 ms or more, the component clears PCM and gives the turn no history.
It discards new PCM until the gate or turn end.
The log field `arm_to_start_ms` gives detection-to-gate time, not detection-to-microphone-start time.
`arm_expired` identifies an interval above the limit.

Mute clears the PCM queue and the arm. The component keeps no new history while mute is active.
Unmute cannot use previous history.
Stop, error, disconnect, and shutdown clear the queue.

## Logical turn boundaries

The pinned VA can finish a response without stopping its microphone sources.
An enabled stock source does not call the virtual microphone start again.
Thus, microphone start and stop alone cannot identify all turns.
Logical turn state does not change the count of enabled sources.
It does not change stock source state or start/stop pairing.

`on_stt_end` finishes the logical turn and logs one summary.
`on_end`, the public `IDLE` state, and an actual microphone stop are idempotent fallbacks.
Finish clears replay, the arm, PCM, queue measurements, and pass-through state for that turn.
The completed `pre_roll_ms` value stays available until the next logical turn.
An unarmed `on_start` sets this value to 0 before the timing event.

Between turns, the component keeps only bounded rolling history and forwards current frames directly to enabled sources.
It does not keep queued live audio through a response or `IDLE` interval.
A new wake can arm while a previous stock `on_end` list waits in an error phase.
That previous list cannot finish a newer active turn or change its timing event.
The added `actions` follow the unchanged stock `actions`.

## Audio order and limits

Wake detection holds the start index of the recent stereo history.
New frames append after that index, through VA microphone start and the HA handshake.
The two signals use one frame index and one queue.
History ends at the replay-gate index. Live audio starts at the next index.
No sample is missing or duplicated at that boundary when the queue does not overflow.

The configured interval is before detection.
The detection-to-gate bridge also counts as history.
Total history has a 1000 ms maximum, with that bridge.
If necessary, the replay gate removes the oldest frames and counts `trimmed_ms`.
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

Debug logs give device monotonic times for wake detection and the replay gate.
Each finished turn logs `history_samples`, `live_samples`, `overflow_count`, `dropped_ms`, and `trimmed_ms`.
The sample counts refer to frames for each signal, not the sum of the two signals.
Logs contain no PCM content.

ESPHome discards API log messages when the write buffer is full.
ESPHome does not retry these messages.
Missing logs alone are not proof that a turn had no history.

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

Setup also makes a 2048-byte `silence_` buffer.
Muted callbacks use it in units of at most 256 stereo frames.
The adapter makes no new heap allocation in a muted callback.
The component does not replace or borrow the stock VA or wake-word buffers.

## Device test

The native tests use numbered synthetic stereo frames, not recorded voice.
A device test must measure command coverage, time intervals, memory, and native-function behavior.
Use approved synthetic or licensed audio for continuous wake-and-command trials.
Measure acoustic wake end independently of the detection log.
Check the two HA signal selections and the history-to-live boundary.

Test wake sound on and off, mute, button starts, follow-ups, announcements, timer stop, and the stop word.
Test slow API connections, stalled connections, and connections after a stall.
Test button starts during wake processing and cancellation before microphone start.
Examine `arm_to_start_ms` and `arm_expired`, with wake sound on and off.
Reject a usual run with dropped frames, queue overflow, missing command onset, or a changed stock function.
The native and compile gates do not include a device test.

## Sources

Source access date: 2026-10-30 (UTC).

- [Stock wake handler](https://github.com/esphome/home-assistant-voice-pe/blob/2644f4c794271d735d182ca7ebf899ed46164f4e/home-assistant-voice.yaml#L1739-L1780): the usual branch starts VA after the mute, timer, stop, and announcement decisions.
- [VA microphone enable](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L315-L356): the loop starts microphone sources after the start request changes state at lines 683 to 695.
- [Public STT signal](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L794-L796): STT start calls `on_listening`.
- [Configuration validation](https://github.com/esphome/esphome/blob/2026.10.0/esphome/config.py#L1239-L1244): the public context holds the validated result object.
- [Code generation](https://github.com/esphome/esphome/blob/2026.10.0/esphome/__main__.py#L797-L808): `to_code` receives sections from `CORE.config`, which line 2749 sets to the validated configuration.
- [Public start request](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L683-L695): `request_start` supplies no start-origin token.
- [Public active state](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.h#L182): `is_running` includes microphone-start and microphone-stop states.
- [Default loop interval](https://github.com/esphome/esphome/blob/2026.10.0/esphome/core/application.h#L526): the nominal interval is 16 ms.
- [Stock source pairing](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/microphone/microphone_source.cpp#L13-L25): an enabled source does not forward the next start.
- [Ring allocation and clearing](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L122-L175): VA makes the two rings before the start request to HA.
- [Audio callbacks](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L37-L52): each source writes only to its live ring.
- [Response end](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L498-L525): response end can go directly to `IDLE`.
- [Run-end selection](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/voice_assistant/voice_assistant.cpp#L914-L925): run end does not stop sources from a response state.
- [API log writes](https://github.com/esphome/esphome/blob/2026.10.0/esphome/components/api/api_connection.cpp#L2411-L2423): a full write buffer can discard a log message.
