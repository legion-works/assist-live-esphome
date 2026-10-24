# Third-party notices

## ESPHome

ESPHome is the external build framework. This repository does not copy its source.
Its Python code and other non-runtime parts use the MIT license.
Its C++ runtime uses the GNU General Public License version 3.

Source: <https://github.com/esphome/esphome/tree/2026.10.0>

License: <https://github.com/esphome/esphome/blob/2026.10.0/LICENSE>

## Home Assistant Voice PE package

The example and fixture use the official package URL. This repository does not copy the package or its assets.
The upstream license uses MIT for non-runtime files and GPL version 3 for runtime files.
The package downloads stock sounds, wake-word models, and voice-kit firmware during a build.
No such asset is part of this source repository.
Before you supply firmware, review all downloaded assets and their source and license obligations.

Source: <https://github.com/esphome/home-assistant-voice-pe/tree/2644f4c794271d735d182ca7ebf899ed46164f4e>

License: <https://github.com/esphome/home-assistant-voice-pe/blob/2644f4c794271d735d182ca7ebf899ed46164f4e/LICENSE>

## Development dependencies

`pytest` uses the MIT license. It is a test tool, not firmware code.
`uv.lock` records the external Python dependency versions.
This repository does not vendor those packages.
