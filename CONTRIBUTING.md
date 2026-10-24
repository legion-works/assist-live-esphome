# Contributing

This project is experimental and has no release.
Discuss changes to the component boundary before implementation.
Keep each change small for review.

## Development

Use `uv` and the checked-in lock file. Run these commands from the repository root:

```sh
uv sync --locked
uv run pytest tests/test_package.py -q
uv run esphome config tests/fixtures/voice-pe.yaml
uv run esphome compile tests/fixtures/voice-pe.yaml
uv run python tools/check_bootstrap.py
uvx ruff format --check .
uvx ruff check .
```

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
