# Verification record

## Dependency sources

Record date: `2026-10-24`.

The ESPHome `2026.10.0` PyPI metadata gives `info.requires_python` as `<3.15,>=3.12.0`.
`pyproject.toml` uses that range and pins `esphome==2026.10.0` in the development group.

`pytest` is the other development dependency. `uv.lock` records locked versions.

Source: <https://pypi.org/pypi/esphome/2026.10.0/json>

The official Voice PE repository uses the `dev` branch and supplies `home-assistant-voice.yaml`.
Tag `26.9.0` resolves to commit `2644f4c794271d735d182ca7ebf899ed46164f4e`.
That package declares `min_version: 2026.6.0`, below the pinned compiler version.
The compile gate must give a satisfactory result before this record can show a correct build.
This is not a general compatibility guarantee.

Source: <https://github.com/esphome/home-assistant-voice-pe/blob/2644f4c794271d735d182ca7ebf899ed46164f4e/home-assistant-voice.yaml>

The package URL uses a full commit and `refresh: never`.
The local configuration adds a last `voice_kit` source at that same commit.
ESPHome installs external component sources in order. The last source supplies the component code.
The stock package fetches its internal `dev` source before that last pin.

The sound substitutions use the same commit, not the upstream `dev` URLs.
Stock wake-word release URLs and compiler-supplied models stay unchanged.
Those upstream downloads limit a fully offline or bit-for-bit build.

The user example uses local source at `../components`, not an unpublished GitHub component.
The compile fixture uses `../../components`.
The token and server secrets flow only into substitutions with no consumer, not component code.
No live connection or device is necessary for compilation.

Network access to `github.com` and `raw.githubusercontent.com` is necessary for compilation.
CI variants with new template keys must update the exact-set checker and the YAML in the same change.

## Source-only boundary

Date: `2026-10-24`.

Command:

```sh
cd "$WORKSPACE/assist-live-esphome"
uv run --no-project --with pytest pytest tests/test_package.py -q
```

Result before project metadata or component source:

```text
E       AssertionError: assert False
tests/test_package.py:4: AssertionError
1 failed in 0.01s
```

The missing file was `components/assist_live/assist_live.h`.

## Public-tree checks

Date for each command in this section: `2026-10-24`.

The ancestor check before `git init -b main` gave `PASS no Git ancestor`.
The repository is its own Git root. Each subsequent Git command used this root check:

```sh
cd "$WORKSPACE/assist-live-esphome"
test "$(git rev-parse --show-toplevel)" = "$(pwd -P)" && echo "PASS own Git root"
```

Result:

```text
PASS own Git root
```

The complete bootstrap command was:

```sh
cd "$WORKSPACE/assist-live-esphome"
export UV_LINK_MODE=copy
uv sync --locked && uv run pytest tests/test_package.py -q && uv run esphome config tests/fixtures/voice-pe.yaml && uv run esphome compile tests/fixtures/voice-pe.yaml && uv run python tools/check_bootstrap.py
```

The command gave exit code `0`. The result lines were:

```text
Resolved 108 packages in 1ms
Checked 88 packages in 0.84ms
1 passed in 0.01s
INFO Configuration is valid!
INFO Successfully compiled program.
PASS firmware bootstrap
```

The shell printed `SUCCESS firmware compile gate` after all checks completed.
That line is a shell result marker, not ESPHome output.
`UV_LINK_MODE=copy` selects copy mode for the cache and environment on different filesystems.
The first sync used automatic hardlink fallback and gave a warning. The locked sync above did not give that warning.

### Fixture ignore file

ESPHome `2026.10.0` writes a default `.gitignore` adjacent to the configuration if that file is missing.
Source: `esphome/writer.py:747-750`, function `write_gitignore` in the installed package.
Its default `/secrets.yaml` rule hides the fake fixture secrets despite the root negation.
The first bootstrap checker stopped with:

```text
FAIL firmware bootstrap: fake secrets are not ignored
```

The repository supplies `tests/fixtures/.gitignore` with only `/.esphome/` to prevent that default file.
The second complete compile kept the supplied file unchanged.

Commands before and after the second compile:

```sh
cp tests/fixtures/.gitignore "$VERIFY_TMP/fixture.gitignore.before"
uv run esphome compile tests/fixtures/voice-pe.yaml
cmp tests/fixtures/.gitignore "$VERIFY_TMP/fixture.gitignore.before"
git check-ignore -v tests/fixtures/secrets.yaml tests/fixtures/.esphome/build
```

`VERIFY_TMP` is an external temporary directory. Results:

```text
PASS fixture ignore file unchanged
.gitignore:12:!tests/fixtures/secrets.yaml tests/fixtures/secrets.yaml
tests/fixtures/.gitignore:1:/.esphome/ tests/fixtures/.esphome/build
```

The negation line means the fake secrets file is not ignored.
Git ignores the build directory. No build output is in the publication file list.
Source files are part of the Git history. Build output is not part of that history.

### Upstream warning baseline

The config command gives five warnings. The compile command gives the same five warnings.
All five come from the stock package at `2644f4c794271d735d182ca7ebf899ed46164f4e`.
These warnings come from stock behavior. No warning suppression applies.

| Warning | Stock source at the pinned commit |
| --- | --- |
| Missing `synchronous=` on `voice_kit.flash` | `esphome/components/voice_kit/__init__.py:142-145` |
| GPIO0 strapping pin | `home-assistant-voice.yaml:293` |
| GPIO3 strapping pin | `home-assistant-voice.yaml:523` |
| Deprecated `rgb_order` | `home-assistant-voice.yaml:595` |
| GPIO45 strapping pin | `home-assistant-voice.yaml:992` |

Complete warning text for each command:

```text
WARNING register_action('voice_kit.flash', ...) is missing the synchronous= parameter. Defaulting to synchronous=False (safe but prevents StringRef optimization). Check the C++ class: use synchronous=False if play_next_() is deferred to a callback, timer, or loop(); use synchronous=True if play_next_() always runs before the initial play/play_complex call returns
WARNING GPIO0 is a strapping pin and should only be used for I/O with care.
Attaching external pullup/down resistors to strapping pins can cause unexpected failures.
See https://esphome.io/guides/faq/#why-am-i-getting-a-warning-about-strapping-pins
WARNING GPIO3 is a strapping pin and should only be used for I/O with care.
Attaching external pullup/down resistors to strapping pins can cause unexpected failures.
See https://esphome.io/guides/faq/#why-am-i-getting-a-warning-about-strapping-pins
WARNING [esp32_rmt_led_strip] 'rgb_order' is deprecated, use 'channel_colors: GRB'. Will be removed in 2027.3.0
WARNING GPIO45 is a strapping pin and should only be used for I/O with care.
Attaching external pullup/down resistors to strapping pins can cause unexpected failures.
See https://esphome.io/guides/faq/#why-am-i-getting-a-warning-about-strapping-pins
```

The complete config and compile log contains 0 warning lines with `assist_live` or `fixtures/voice-pe.yaml`.
Source checks find each warning in the stock files in the table.
The component and the local fixture introduce 0 warnings.

CI compares warnings with this baseline and stops on each new warning.

### Formatting and lint

Commands:

```sh
uvx ruff format --check .
uvx ruff check .
```

Results:

```text
13 files already formatted
All checks passed!
```

### Documentation and privacy

Run the ASD-STE100 checker on each root Markdown file and on this record.
Use the private denylist to examine the files from `git ls-files -co --exclude-standard` output.
Do not print the private terms. Also check for local home paths and private IPv4 addresses.
The bootstrap checker accepts an optional external `--denylist` file for the same check.
No private term is part of this repository.

The documentation checker gave these results:

| File | Findings | Exit code |
| --- | --- | --- |
| `README.md` | 0 | 0 |
| `ARCHITECTURE.md` | 0 | 0 |
| `STRUCTURE.md` | 0 | 0 |
| `CHANGELOG.md` | 0 | 0 |
| `AGENTS.md` | 0 | 0 |
| `CODE_OF_CONDUCT.md` | 0 | 0 |
| `CONTRIBUTING.md` | 0 | 0 |
| `SECURITY.md` | 0 | 0 |
| `THIRD_PARTY_NOTICES.md` | 0 | 0 |
| `docs/verification.md` | 0 | 0 |

The publication privacy check examined 24 files:

```text
denylist_matches: 0
local_home_paths: 0
private_ipv4: 0
PASS publication privacy scan
```

The bootstrap check with the external private denylist gave `PASS firmware bootstrap`.

### Code analysis

A static analysis snapshot includes `$WORKSPACE/assist-live-esphome`.

The Python analyzer gave 0 errors and 0 warnings.
The generic YAML analyzer reported four `Unresolved tag: !secret` errors in the example.
The C++ analyzer could not find a compile database or a different workspace marker.
These are tool limits, not ESPHome configuration or compile failures.
The actual ESPHome config and compile commands are the validation checks for these files.

## Template validation

Date: `2026-10-24`.

The README states the moving `dev` dependency and the offline and reproducibility limits.
The checker reads template YAML without access to external secrets or ESPHome global configuration.
It checks the fake secrets file first. YAML read and parser errors give a named failure without a traceback.

The example and fixture use the same package and component constants.
Only their device names, local component paths, and comments are different.
The checker examines all raw GitHub URLs and `ref` values in the two templates for the pinned commit.
The checker accepts only the current set of top-level template keys.

### Mutation checks

The mutation runner copied only the publication files into different temporary Git repositories.
It did not change or delete the working fixture secrets.
Command in each temporary copy:

```sh
uv run python tools/check_bootstrap.py
```

Initial regression results:

```text
PASS control: exit=0; PASS firmware bootstrap
RED missing-secrets: exit=1; AttributeError: 'NoneType' object has no attribute 'parent'
RED example-dev-sound: exit=0; PASS firmware bootstrap
RED example-voice-assistant: exit=0; PASS firmware bootstrap
```

The first mutation removes the fake secrets file in its copy.
The second changes one example sound URL to the `dev` branch.
The third adds `voice_assistant: {}` to the example.
Command in each temporary copy:

```sh
uv run python tools/check_bootstrap.py
```

Current regression results:

```text
PASS control: exit=0; PASS firmware bootstrap
PASS missing-secrets: exit=1; FAIL firmware bootstrap: unreadable YAML: tests/fixtures/secrets.yaml
PASS example-dev-sound: exit=1; FAIL firmware bootstrap: examples/voice-pe.yaml: pinned raw GitHub URL
PASS example-voice-assistant: exit=1; FAIL firmware bootstrap: examples/voice-pe.yaml: must not redefine stock voice, wake words, timers, or media player
```

Each negative check gives exit code `1` and a named failure without a traceback.
The control copy gives exit code `0`.

### Compile validation

The complete bootstrap command in this record ran again with a one-hour timeout.
It gave exit code `0`:

```text
PASS own Git root
1 passed in 0.00s
INFO Configuration is valid!
INFO Successfully compiled program.
PASS firmware bootstrap
PASS config: stock_warnings=5; new_warnings=0; own_source_warnings=0
PASS compile: stock_warnings=5; new_warnings=0; own_source_warnings=0
PASS full literal gate chain; exit 0
```

The complete warning lines are the same as the upstream baseline in this record.
The static analysis snapshot gave generic YAML and clangd limits, with no Python diagnostics.
The source-only publication boundary and the four fake secrets stay unchanged.

The Ruff format and lint checks gave `13 files already formatted` and `All checks passed!`.
The 10 repository Markdown files each have 0 STE findings.
The initial publication privacy check gave:

```text
{'files': 24, 'denylist_matches': 0, 'local_home_paths': 0, 'private_ipv4': 0}
PASS publication privacy scan
PASS own Git root; fake secrets visible; build ignored; index empty; no remotes
```

## Review of all three repositories

Date: `2026-10-24`.

Scope: the three bootstrap repositories, `assist-live`, `assist-live-server`, and `assist-live-esphome`.
The review checked cross-repository contracts, convention drift, comment and prose hygiene, and privacy across Git history.
The result was `REVISE`.

The public record uses topic headings and project state without internal provenance.
The firmware checker sends named failure lines to stdout, as the other repositories do.
The package test resolves its source root from `__file__` and uses that root for the Git command.
The record keeps the upstream warning table and source citations.
CI compares warnings with the baseline and stops on each new warning.

## Package test invocation

Date: `2026-10-24`.

The test uses `Path(__file__).resolve().parents[1]` for its source root.
Its file assertions and `git ls-files` command use that root, not the working directory.
The Git subprocess receives `cwd=ROOT`.

Command:

```sh
cd "$WORKSPACE/assist-live-esphome/tests"
uv run pytest test_package.py -q
```

The relative-path regression gave these initial results:

```text
E       AssertionError: assert False
test_package.py:4: AssertionError
1 failed in 0.01s
```

The root-relative test gives:

```text
1 passed in 0.01s
```

## Checker output

Date: `2026-10-24`.

The checker prints `FAIL firmware bootstrap: <message>` on stdout and gives a non-zero exit code.
Success also uses stdout. A missing fake-secret file in a temporary copy checks the failure stream.
The temporary copy uses the same public command:

```sh
uv run python tools/check_bootstrap.py
```

Result:

```text
PASS failure stream: exit=1; stdout='FAIL firmware bootstrap: unreadable YAML: tests/fixtures/secrets.yaml\n'; stderr=''
```

## Current validation results

Date: `2026-10-24`.

The complete bootstrap command in this record gave exit code `0` with a one-hour timeout:

```text
PASS own Git root
1 passed in 0.04s
INFO Configuration is valid!
INFO Successfully compiled program.
PASS firmware bootstrap
PASS config: stock_warnings=5; new_warnings=0; own_source_warnings=0
PASS compile: stock_warnings=5; new_warnings=0; own_source_warnings=0
PASS full literal gate chain; exit 0
```

The public-tree checker examines the working tree and its Git history.
`PRIVATE_DENYLIST` is an external private input file. Its contents are not part of this repository.

Command:

```sh
cd "$WORKSPACE/assist-live-esphome"
uv run --project "$WORKSPACE/assist-live" python "$WORKSPACE/assist-live/tools/check_public_tree.py" --history --root . --private-denylist "$PRIVATE_DENYLIST"
```

Results:

```text
PASS own Git root
PASS history secrets commits=1
PASS public data matches=0
```
