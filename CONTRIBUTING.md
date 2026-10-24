# Contributing

This project is experimental and has no release.
Discuss changes to the component boundary before implementation.
Keep each change small for review.

## Development

Install `uv`, Task, `actionlint`, and Gitleaks.
Use the checked-in lock file. Run the complete check from the repository root:

```sh
uv sync --locked
task check
```

The mandatory `task check` command includes all format, lint, type, unit, license, source-only, configuration, compile, and secret checks.
The default work root is `${XDG_CACHE_HOME:-$HOME/.cache}/assist-live-esphome`.
Set `ESPHOME_WORK_DIR` to change it.
The Taskfile sets `ESPHOME_DATA_DIR` to `<work-root>/data` and `ESPHOME_BUILD_PATH` to `<work-root>/build`.

Run the documentation checker on each Markdown file that you change.
Do not add build output or actual credentials to Git.
Do not flash the compile fixture or connect to a device for these checks.
Keep actual flash credentials in an external secrets directory.

## Source and licenses

Keep the stock voice, wake-word, timer, and media functions.
Use `GPL-3.0-or-later` for component source.
Record new external dependencies and their licenses in `THIRD_PARTY_NOTICES.md`.
Use synthetic test audio or audio with a permitted open license and the necessary consent.
Write documentation and comments in ASD-STE100 Simplified Technical English.

Get explicit operator approval before publication or cloud tests.
