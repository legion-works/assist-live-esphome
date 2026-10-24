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

The configuration command gives five warnings from stock Voice PE `26.9.0`.
Its commit is `2644f4c794271d735d182ca7ebf899ed46164f4e`.
The earlier five-warning compile count came from an incremental build, not a clean build.
A clean build adds 19 compiler warning lines from eight third-party diagnostics.
No warning suppression applies.

Counts below refer to one clean compile and one subsequent incremental compile.
Compiler source paths are relative to the named component.

| Component and version | Source | Warning | Clean count | Incremental count |
| --- | --- | --- | --- | --- |
| Voice PE `26.9.0` | `esphome/components/voice_kit/__init__.py:142-145` | Missing `synchronous=` on `voice_kit.flash` | 1 | 1 |
| Voice PE `26.9.0` | `home-assistant-voice.yaml:293` | GPIO0 strapping pin | 1 | 1 |
| Voice PE `26.9.0` | `home-assistant-voice.yaml:523` | GPIO3 strapping pin | 1 | 1 |
| Voice PE `26.9.0` | `home-assistant-voice.yaml:595` | Deprecated `rgb_order` | 1 | 1 |
| Voice PE `26.9.0` | `home-assistant-voice.yaml:992` | GPIO45 strapping pin | 1 | 1 |
| `esphome/micro-opus` `0.4.1` | `silk/NLSF2A.c:54` | `cos_LSF_QA`, `-Wmaybe-uninitialized` | 2 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/mul.h:150` | `params`, `-Wshadow` | 3 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/mul.h:209` | `params`, `-Wshadow` | 3 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/mul.h:249` | `params`, `-Wshadow` | 3 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/sub.h:264` | `params`, `-Wshadow` | 2 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/sub.h:284` | `params`, `-Wshadow` | 2 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/sub.h:308` | `params`, `-Wshadow` | 2 | 0 |
| `espressif/esp-tflite-micro` `1.3.3~1` | `tensorflow/lite/kernels/internal/reference/sub.h:420` | `params`, `-Wshadow` | 2 | 0 |

The compiler version sources are in the clean build's `dependencies.lock`:

- `dependencies.esphome/micro-opus.version`, lines `93-102`: `0.4.1`.
- `dependencies.espressif/esp-tflite-micro.version`, lines `124-137`: `1.3.3~1`.

The managed-component manifests give those same versions:

- `managed_components/esphome__micro-opus/idf_component.yml:13`.
  Its `repository_info.commit_sha` at line `10` is `8354085908683c6130e32a832aeec8a7ca115c51`.
- `managed_components/espressif__esp-tflite-micro/idf_component.yml:19`.
  Its `repository_info.commit_sha` at line `16` is `78e5532e682d3863a3c2985c3a74eed0a9ebaa61`.

Complete configuration warning text:

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

The configuration and clean-compile logs contain 0 warnings from `components/assist_live/` or the local fixture.
The compiler baseline uses the component name, component-relative path, source line, warning flag, and complete message.
The same text from local component, fixture, or example lines stops the check.

A new third-party warning after an upstream change stops CI and must have a reviewed baseline update.
The stock package's moving `dev` fetch can cause such changes.

### Formatting and lint

Date: `2026-10-24`.

`task check` is the mandatory gate.
It uses the project Ruff configuration and locked development tools.
Its format and lint commands are:

```sh
uv run ruff format --check .
uv run ruff check .
```

Results:

```text
6 files already formatted
All checks passed!
```

The earlier bootstrap state used unpinned `uvx ruff` commands.
Those commands are not the current gate.

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

## Cross-repository checks

Date: `2026-10-24`.

Scope: the three bootstrap repositories, `assist-live`, `assist-live-server`, and `assist-live-esphome`.
Checks examined shared contracts, conventions, comments, documentation, and privacy across Git history.
The public record uses project state, and the firmware checker uses named stdout failures.

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

## Bootstrap validation results

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

## Continuous checks

Date: `2026-10-24`.

`task check` runs the locked tool install, format check, lint, type check, unit tests,
bootstrap checks, source-only checks, configuration validation, compile, and secret checks.
The lint rules are `E`, `F`, `W`, `I`, `B`, and `UP`. All rule sets apply.
The Python target is `3.12`, from the ESPHome metadata above.

The supported-version matrix contains only ESPHome `2026.10.0`.
A second version must compile correctly before it goes into the matrix.
No hardware compatibility claim follows from this compile check.

The first release-check test gave this failure:

```sh
cd "$WORKSPACE/assist-live-esphome"
uv run pytest tests/test_release.py -q
```

```text
E       ModuleNotFoundError: No module named 'tools'
1 failed in 0.04s
```

The pytest configuration adds the repository root to the import path.

### GitHub Actions pins

Each pin came from `gh api repos/OWNER/REPO/git/ref/tags/TAG`.
Each tag below points directly to a commit, not an annotated tag.

| Action | Tag | Commit |
| --- | --- | --- |
| `actions/checkout` | `v4.3.1` | `34e114876b0b11c390a56381ad16ebd13914f8d5` |
| `actions/setup-python` | `v6.1.0` | `83679a892e2d95755f2dac6acb0bfd1e9ac5d548` |
| `astral-sh/setup-uv` | `v7.1.2` | `85856786d1ce8acfbcc2f13a5f3fbd6b938f9f41` |
| `go-task/setup-task` | `v1.0.0` | `0ab1b2a65bc55236a3bc64cde78f80e20e8885c2` |
| `actions/cache` | `v4.3.0` | `0057852bfaa89a56745cba8c7296529d2fc39830` |
| `googleapis/release-please-action` | `v4.3.0` | `c2a5a2bd6a758a0937f1ddb1e8950609867ed15c` |

The workflow downloads use SHA-256 checks from the GitHub release API asset metadata.
The commands were `gh api repos/gitleaks/gitleaks/releases/tags/v8.30.0`
and `gh api repos/rhysd/actionlint/releases/tags/v1.7.12`.

| Archive | SHA-256 |
| --- | --- |
| `gitleaks_8.30.0_linux_x64.tar.gz` | `79a3ab579b53f71efd634f3aaf7e04a0fa0cf206b7ed434638d1547a2470a66e` |
| `actionlint_1.7.12_linux_amd64.tar.gz` | `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8` |

### Build directories and secret checks

ESPHome `2026.10.0` reads `ESPHOME_BUILD_PATH` and `ESPHOME_DATA_DIR`.
The first sets the build parent directory. The second sets the data directory.
Sources:

- `esphome/core/config.py:500-503` in ESPHome `2026.10.0`.
- `esphome/core/__init__.py:829-833` in ESPHome `2026.10.0`.
- <https://github.com/esphome/esphome/blob/2026.10.0/esphome/core/config.py>
- <https://github.com/esphome/esphome/blob/2026.10.0/esphome/core/__init__.py>

The upstream tag points to `704551a6c93c29a311802f7ee97d67a9e9bce718`.
The Taskfile uses a stable external cache directory, not the repository.
`ESPHOME_WORK_DIR` can change its root.
The default is `${XDG_CACHE_HOME:-$HOME/.cache}/assist-live-esphome`.

CI uses the runner temporary directory.
The cache key includes the ESPHome version, the lock file, and the fixture files.
It includes PlatformIO downloads, the ESP-IDF tools cache, and ESPHome data.
The compile check keeps network access to GitHub and `raw.githubusercontent.com`.

`gitleaks dir .` examines Git-ignored directories.
The initial check found 54 results in downloaded upstream source in the previous build tree.
Those results came from libsodium, noise-c, and WebSocket example private keys.
It found no fake fixture value in the C++ source output.
The previous build tree stays in an external directory.

After each correct compile, Gitleaks checks the `src` output directory explicitly.
It then checks the complete repository directory.
No rule ignores a directory or a full file.
Default Gitleaks rules stay enabled.
The custom fixture rule ignores only four specified fake values, each at the fixture path.
A different Wi-Fi password at that path stops the check, also with low entropy.

### Warning checks and source archives

The log checker compares structured warnings with the configuration and compiler entries above.
It removes ANSI codes and timestamps before it compares messages.
The FAQ continuation URL is not a different warning.
A URL with `-warning-` does not stop the gate.
A new `WARNING` message or compiler diagnostic stops the gate.
The log must also contain the configuration or compile success line.

The source-only gate checks `git ls-files -co --exclude-standard` and supplied release archives.
It refuses compiled suffixes, ELF headers, ESP image headers, and compiled files in archives.
The source-archive workflow makes a source archive in the runner temporary directory.
It checks that archive and uploads nothing.

Release workflows run only through manual dispatch.
Their first step stops unless `ASSIST_LIVE_RELEASES_APPROVED` is `true`.
The operator sets this repository `variable` only after explicit publication approval.
Only the release `job` has write access.
The project has no release. No workflow ran on GitHub during these local checks.

`ci-complete` has a dependency on all other `jobs` and runs with `always()`.
Its tests parse the workflow and run its actual gate command.
Failure, cancellation, or a skipped `job` stops the necessary check.

Mutation results in an isolated source copy:

```text
PASS mutation renamed ESP image: exit=1
PASS mutation fixture password: exit=1; leaks=1
PASS mutation new compile warning: exit=1
PASS mutation changed baseline message: exit=1
PASS workflow source archive: checked without publication
```

### Clean-build warnings

The baseline comes from a clean build in a new external build root.
Before compilation, `test ! -e "$ESPHOME_WORK_DIR"` gave exit code `0`.
`CCACHE_DISABLE=1` disabled the compiler cache.
The toolchain downloads stayed in their initial cache.
The compile gave 19 third-party compiler warning lines, plus five configuration warnings:

- `silk/NLSF2A.c:54` gives two `-Wmaybe-uninitialized` warnings about `cos_LSF_QA`.
- `reference/mul.h:150,209,249` gives nine `-Wshadow` warnings about `params`.
- `reference/sub.h:264,284,308,420` gives eight `-Wshadow` warnings about `params`.

The build root comes from the external `ESPHOME_WORK_DIR` value.
The check command copied the clean-build log to `clean-compile.log` before a second `task compile` command.
The second compile used the same build root.
The check command copied that log to `incremental-compile.log`.

Commands:

```sh
cd "$WORKSPACE/assist-live-esphome"
export CCACHE_DISABLE=1
uv run pytest tests/test_release.py -q && task check && uv run python tools/check_release.py --source-only && gitleaks dir . --redact --exit-code 1
uv run python tools/check_release.py --compile-log "$ESPHOME_WORK_DIR/clean-compile.log"
uv run python tools/check_release.py --compile-log "$ESPHOME_WORK_DIR/incremental-compile.log"
```

Results:

```text
PASS fresh build root absent; compiler cache disabled
34 passed in 0.17s
6 files already formatted
All checks passed!
Success: no issues found in 6 source files
45 passed in 0.82s
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS source-only release
PASS clean-compile.log: config_warnings=5 compiler_warnings=19 new_warnings=0
PASS incremental-compile.log: config_warnings=5 compiler_warnings=0 new_warnings=0
```

The complete chain gave exit code `0`.
The warning check accepted the clean-build log and the incremental-build log.
Gitleaks examined the `src` output and the repository directory, with no findings.
The unchanged-text local-source tests and the changed-message mutation checks stop the gate as intended.

### Release version source

Date: `2026-10-24`.

The release configuration uses the Python strategy and the root `pyproject.toml`.
Its `[project].version` and `.release-please-manifest.json` each contain `0.0.0`.
No `version.txt` file is necessary.
The project is experimental and has no release.

The pinned release action's `package-lock.json` selects release-please `17.1.2`.
Source key: `packages["node_modules/release-please"].version`.
That version's tag points to `5d62849f23940e3dc1dd08beb2732792c2f6ea0e`.
The Python strategy reads `pyproject.toml` and selects its `[project]` table.
Its updater changes the `version` value in that table, not a new version file.

Sources:

- `src/strategies/python.ts:84-97` in release-please `17.1.2`.
- `src/updaters/python/pyproject-toml.ts:51-72` in release-please `17.1.2`.
- <https://github.com/googleapis/release-please/blob/5d62849f23940e3dc1dd08beb2732792c2f6ea0e/src/strategies/python.ts>
- <https://github.com/googleapis/release-please/blob/5d62849f23940e3dc1dd08beb2732792c2f6ea0e/src/updaters/python/pyproject-toml.ts>

The configuration test checks that the strategy's version source is a file and agrees with the release manifest.
With the simple strategy, its first run stopped because `version.txt` was missing:

```text
assert version_file.is_file()
E       AssertionError: assert False
1 failed in 0.02s
```

The development group uses `pytest==9.1.1`, the version from the bootstrap lock file.
No test or dependency requirement made the lower `8.4.2` version necessary.
The lock file and complete test suite use that version.

Verification results:

```text
pytest 9.1.1
46 passed in 0.46s
```

The subsequent complete gate uses a warm incremental firmware compile.
The earlier clean-build and incremental-build baseline logs stay unchanged.

## Archive probe on Python 3.12

Date: 2026-10-24 (UTC).

The first hosted CI run used Python 3.12. One unit test gave a failure:

```text
FAILED tests/test_release.py::test_source_passes_and_failures_are_collected
'component.cpp: unreadable archive (ReadError)'
```

On Python 3.12, `zipfile.is_zipfile` does not put the stream back at offset 0.
`tarfile.is_tarfile` then read from the end of the stream.
It identified a source file as a tar archive.
On Python 3.14, `zipfile.is_zipfile` puts the stream back at offset 0, so the local test run did not show the problem.
The release checker gives each archive probe its own stream at this time.

```sh
uv run --locked --python 3.12 pytest tests/ -q
uv run --locked pytest tests/ -q
```

```text
before the change, Python 3.12: 1 failed, 33 passed (tests/test_release.py)
after the change, Python 3.12: 46 passed
after the change, Python 3.14: 46 passed
```
