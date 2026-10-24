# assist-live-esphome

An experimental ESPHome component for assist-live. This project has no release.

The component is a placeholder. It adds no network connection, timing events, or voice hooks.
It only calls `register_component` and prints a configuration message.
The example extends the stock Home Assistant Voice Preview Edition (Voice PE) package.
The stock package keeps control of voice, wake words, timers, and the media player.

## Development check

Install `uv`. Then run these commands from the repository root:

```sh
uv sync --locked
uv run pytest tests/test_package.py -q
uv run esphome config tests/fixtures/voice-pe.yaml
uv run esphome compile tests/fixtures/voice-pe.yaml
uv run python tools/check_bootstrap.py
```

The lock file selects ESPHome `2026.10.0`.

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
The `assist_live_device_token` and `assist_live_server` substitutions have no runtime consumer at this step.

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
