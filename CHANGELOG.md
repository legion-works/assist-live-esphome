# Changelog

## Unreleased

- Add the source-only `assist_live` component. It sends authenticated timing events to the server with UDP or a WebSocket.
- Add an example and compile fixture that extend the stock Voice PE package.
- Add the source-only boundary test and bootstrap checker.
- Add optional microphone history for wake-word turns with the wake sound off. The lookback defaults to 200 ms.
- Clear microphone history at each voice-turn boundary, also when the stock microphone sources stay enabled.
- Keep live audio and reply restart available without history if the history allocation or PCM format check is unsatisfactory. Mute continues to send 0 samples.
- Add optional Home Assistant diagnostic entities for completed turns and the timing sender. Publish counters only when their values change.
- Add optional replay pacing from public voice-assistant buffer space. An ESPHome version or component override that supplies the interface is necessary.
- Record wake detection before the wake sound. Include the length of history sent in the authenticated microphone timing event.
- Add reply-window and reply-restart options. Each is off by default. The window uses Very sensitive cutoffs through playback and for 2000 ms after playback ends.
- With reply restart on, a named wake during a voice-assistant reply stops playback and starts a new wake turn after the stop. The wait has a 500 ms limit.
- Keep available microphone history through reply stop and restart. Stop, mute, error, disconnect, and a wake that stops a ringing timer cancel a pending restart.

This project is experimental and has no release.
