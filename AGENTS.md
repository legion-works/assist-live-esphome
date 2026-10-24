# Repository rules

- Keep this repository source-only with the `GPL-3.0-or-later` license.
- Keep the SPDX identifier on each component source file.
- Extend the stock Voice PE package without changes to voice, wake words, timers, or media functions.
- Keep personal data, actual credentials, recordings, and compiled firmware out of the repository.
- Keep actual flash credentials in an external secrets directory.
- Use only fake compile values in `tests/fixtures/secrets.yaml`.
- Do not connect to a device or flash the compile fixture.
- Write documentation and comments in ASD-STE100 Simplified Technical English.
- Follow `CONTRIBUTING.md` for development checks.
- Get explicit operator approval before publication or cloud tests.
