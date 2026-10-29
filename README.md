# assist-live-esphome

An experimental ESPHome component for assist-live. This project has no release.

The component sends authenticated device timing events through UDP or WebSocket.
It reports wake detection, a microphone-start proxy, and playback-state proxies.
See [device timing events](docs/protocol.md) for credentials, configuration, and signal limits.
The example extends the stock Home Assistant Voice Preview Edition (Voice PE) package.
The stock package keeps control of voice, wake words, timers, and the media player.

## Development check

Install `uv`, Task, `actionlint`, and Gitleaks.
Run the complete check from the repository root:

```sh
uv sync --locked
task check
```

The default work root is `${XDG_CACHE_HOME:-$HOME/.cache}/assist-live-esphome`.
Set `ESPHOME_WORK_DIR` to change it.
The Taskfile sets `ESPHOME_DATA_DIR` to `<work-root>/data` and `ESPHOME_BUILD_PATH` to `<work-root>/build`.
The check includes compilation and secret checks of the source output and the repository.

The lock file selects ESPHome `2026.10.0`.
The supported-version matrix contains only ESPHome `2026.10.0`.
This compile check is not a hardware compatibility claim.

The first compile downloads the build tools and external dependencies.
A device or a live server connection is not necessary for the compile.

The stock Voice PE package fetches its `voice_kit` source from its moving `dev` branch before the local pin.
Thus the build is not fully reproducible or offline.

WARNING: Do not flash the compile fixture. Its credentials are fake.
Do not connect to a device for this check.

## Example

Use [examples/voice-pe.yaml](examples/voice-pe.yaml) as a source template.
It uses the local `components/` directory because this project has no release.

Keep actual flash credentials in an external secrets directory.
Copy the example to that directory. Change its local component path to your source checkout.
Put the actual `secrets.yaml` adjacent to that copy, not in this repository.

Set `assist_live_device`, `assist_live_hmac_key`, and `assist_live_server` in the external secrets file.
The example uses them as the anonymous device identifier, 32-byte hexadecimal HMAC key, and server address.
It selects UDP timing events. No device trial or transport selection result is available.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Repository structure](STRUCTURE.md)
- [Development rules](CONTRIBUTING.md)
- [Verification record](docs/verification.md)
- [Vulnerability reports](SECURITY.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## License

The component source uses `GPL-3.0-or-later`.
The GNU General Public License version 3 or a subsequent version applies.
See [LICENSE](LICENSE) for the full version 3 text.
This repository supplies source only. It does not supply compiled firmware.
Before you supply compiled firmware, get a different license review.

A Legion Works project.
