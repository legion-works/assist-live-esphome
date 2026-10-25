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

## Device loop startup

Date: 2026-10-24 (UTC).

The resolved startup tests first gave two failures:

```sh
uv run pytest tests/test_probe_device.py -k resolved -q
```

```text
FAILED tests/test_probe_device.py::test_resolved_probe_keeps_stock_boot_and_starts_from_loop
FAILED tests/test_probe_device.py::test_resolved_config_has_only_probe_additions_and_external_credentials
2 failed, 29 deselected in 21.24s
```

The package merge put the probe start after the stock `delay: 1s` and `delay: 10min`.
It also changed the stock startup `priority` from `375` to `-100`.
The probe starts one time from `esphome.on_loop` at this time.
It does not declare `esphome.on_boot`.
The resolved startup `priority` and all stock startup steps agree with the fixture.

The worker uses FreeRTOS `priority` 0 on core 0.
ESPHome's loop uses `priority` 1 on core 1 in the dual-core Voice PE build.
Source: ESPHome `2026.10.0`, `esphome/components/esp32/core.cpp:24-28,41-45`.
A device test must measure the actual effect on native audio.

The tests list all differences between the two resolved configurations.
Only probe fields, external credentials, device names, build paths, and the missing placeholder component can have different values.
The [device probe record](research/q1-device-probe.md#resolved-configuration-contract) lists each permitted field.

A mutation put the start back in `on_boot` with `priority: 375`, the stock value.
The tests found that mutation:

```text
FAILED tests/test_probe_device.py::test_probe_extends_stock_without_native_overrides
FAILED tests/test_probe_device.py::test_resolved_probe_keeps_stock_boot_and_starts_from_loop
FAILED tests/test_probe_device.py::test_resolved_config_has_only_probe_additions_and_external_credentials
3 failed, 28 deselected in 18.34s
```

The source then changed back to the isolated loop start.
The unmodified probe test run gave:

```sh
uv run pytest tests/test_probe_device.py -q
```

```text
31 passed in 16.15s
```

The resolved tests invoke the locked ESPHome Python package.
They use external data and build roots and can fetch the pinned public package sources.
No different external tool or CI install step is necessary.
Device trial: not run (no test device at this time).

The loop-start firmware used a new external build root and the same fake compile-only secrets:

```sh
uv run python tools/probe_device.py stage --config tests/probes/transport.yaml \
  --secrets "$DEVICE_SECRETS" --output "$RUNROOT/q1-config"
ESPHOME_DATA_DIR="$RUNROOT/data" ESPHOME_BUILD_PATH="$RUNROOT/build" \
  uv run esphome config "$RUNROOT/q1-config/transport.yaml" >"$RUNROOT/config.log" 2>&1
ESPHOME_DATA_DIR="$RUNROOT/data" ESPHOME_BUILD_PATH="$RUNROOT/build" \
  ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT=2 \
  uv run esphome compile "$RUNROOT/q1-config/transport.yaml" >"$RUNROOT/compile.log" 2>&1
uv run python tools/check_release.py --config-log "$RUNROOT/config.log" \
  --compile-log "$RUNROOT/compile.log"
ESPHOME_WORK_DIR="$STOCK_WORK_ROOT" UV_LINK_MODE=copy task check
UV_PROJECT_ENVIRONMENT="$FLOOR_ENV" UV_LINK_MODE=copy \
  uv run --locked --python 3.12 pytest tests/ -q
```

```text
PASS probe staged; no upload or device connection
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS config warnings: new_warnings=0
INF no leaks found
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
77 passed in 19.14s
PASS firmware bootstrap
PASS source-only release
77 passed in 17.91s
```

Firmware revision: `sha256-c483c3d7bd2cb1e0fd2e40ce4f79b20cb7ca8791ade325ad9d200184a2087463`.
The source output has `StartupTrigger(375.0f)` and a different `LoopTrigger` for the probe start.
The SDK configuration output has two FreeRTOS cores.
No upload, flash, or device connection occurred.

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

## Device transport probe

Date: 2026-10-24 (UTC).

Device trial: not run (no test device at this time).
The probe extends the stock Voice PE package without native audio or voice replacements.
The [device probe record](research/q1-device-probe.md) gives its event format, authentication, and subsequent device steps.

The first standalone test run stopped because the result reader was not available:

```sh
uv run pytest tests/test_probe_device.py -q
```

```text
E       ModuleNotFoundError: No module named 'tools.probe_device'
1 failed in 0.01s
```

After implementation, the same command gave:

```text
29 passed in 0.05s
```

The tests check external file copies, necessary secrets, fixture refusal, packet authentication, replay refusal, changed boots, and recorded sample reports.
They also check the armed command arguments without network access and the masked WebSocket frame reader.
Host-generated sample data is not a device result.

The probe used external scratch paths and obviously fake credentials for compilation only:

```sh
uv run python tools/probe_device.py stage --config tests/probes/transport.yaml \
  --secrets "$DEVICE_SECRETS" --output "$RUNROOT/q1-config"
ESPHOME_DATA_DIR="$RUNROOT/data" ESPHOME_BUILD_PATH="$RUNROOT/build" \
  uv run esphome config "$RUNROOT/q1-config/transport.yaml" >"$RUNROOT/config.log" 2>&1
ESPHOME_DATA_DIR="$RUNROOT/data" ESPHOME_BUILD_PATH="$RUNROOT/build" \
  ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT=2 \
  uv run esphome compile "$RUNROOT/q1-config/transport.yaml" >"$RUNROOT/compile-final.log" 2>&1
uv run python tools/check_release.py --config-log "$RUNROOT/config.log" \
  --compile-log "$RUNROOT/compile-final.log"
gitleaks dir "$RUNROOT/build/assist-live-probe/src" \
  --config .gitleaks.toml --redact --exit-code 1
```

```text
PASS probe staged; no upload or device connection
INFO Configuration is valid!
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS config warnings: new_warnings=0
INF no leaks found
```

ESPHome `2026.10.0` used ESP-IDF `5.5.6`.
The compiled image and source output stayed in the external build root.
No upload, flash, or device connection occurred.
The compile fixture's secret file did not change.

The first compile identified a missing explicit `tcp_transport` dependency.
The next compile identified an ambiguous `socket` name after ESPHome's namespace imports.
The probe explicitly includes the built-in transport and uses `::socket`.
The two changes do not change the stock package.

The two explicit SDK keys are correct in ESP-IDF `5.5.6`:

```text
CONFIG_WS_TRANSPORT=y
CONFIG_LWIP_MAX_SOCKETS=15
```

The SDK configuration output contains these values.
The [device probe record](research/q1-device-probe.md#build-configuration) gives the Kconfig sources and the socket settings.
A device test must measure heap use and native function behavior.

A clean stock-fixture compile and the first clean probe configuration gave the same CMake notices at `build.cmake:631` and `project.cmake:765`.
The two logs also mapped the same legacy stack-memory key.
The probe does not set that legacy key.
The incremental probe compile gave exit code 0, with no CMake notices or compiler warnings.
The warning checker does not check CMake notices.

Repository and floor-Python gates:

```sh
ESPHOME_WORK_DIR="$RUNROOT/stock" UV_LINK_MODE=copy task check
UV_PROJECT_ENVIRONMENT="$RUNROOT/venv312" UV_LINK_MODE=copy \
  uv run --locked --python 3.12 pytest tests/ -q
```

```text
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
75 passed in 0.53s
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INF no leaks found
75 passed in 0.38s
```

The tests add no external command dependency.
CI installs the pinned tools that the repository gate uses.

The ASD-STE100 checker examined this record and `docs/research/q1-device-probe.md`, with 0 findings for each file.
The privacy self-scan examined all publishable files, with 0 private-data findings.
The public-data checker used this command:

```sh
uv run --project "$WORKSPACE/assist-live" python \
  "$WORKSPACE/assist-live/tools/check_public_tree.py" --root . \
  --private-denylist "$PRIVATE_DENYLIST"
```

```text
PASS own Git root
PASS public data matches=0
```

## Trial identity and server boot windows

Date: 2026-10-24 (UTC).

The device probe record gives different rules for trial identity and production server boot windows.
One trial uses one boot of one firmware revision. The trial reader rejects a change during that trial.
The production server accepts a new boot identifier as a new sequence and a new clock window.
Source: `docs/design.md` in the `legion-works/assist-live` repository.
Its device event section states: "A new boot ID starts a new sequence and clock window."
The server-side transport probe must test post-restart events.

The record and code comments also include the `ready` handshake exemption.
The handshake does not consume the first measurement's `(boot_id, seq 0)` pair or set the trial identity.
Python parsing ignores comments. The Python syntax tree agrees with `HEAD`.
Runtime behavior did not change.

```sh
ESPHOME_WORK_DIR="$STOCK_WORK_ROOT" UV_LINK_MODE=copy task check
UV_PROJECT_ENVIRONMENT="$FLOOR_ENV" UV_LINK_MODE=copy \
  uv run --locked --python 3.12 pytest tests/ -q
```

```text
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
77 passed in 12.07s
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INF no leaks found
77 passed in 12.46s
```

The ASD-STE100 checker gave 0 findings for each of the two changed Markdown files.
The public-data checker gave `PASS public data matches=0`.
The privacy self-scan gave 0 denylist, local-path, and private-address findings.
`git diff --check` gave exit code 0.

Device trial: not run (no test device at this time).

## Pre-flash source checks

Date: 2026-10-25 (UTC).

The probe starts only after task creation gives `pdPASS`.
An unsuccessful task creation logs an error. The loop tries a maximum of three times.
The device identifier comes from the ESPHome node name and stays in the decoded events and trial report.

An armed run must have an explicit `--bind` address.
It refuses `docs/research/q1-device-probe.md` as a trial output path.
The procedure uses `docs/research/q1-device-trial.md` for the trial result.

The source-only check refuses `.hex` images and checks ESP image headers and factory partition offsets.
An isolated `0xE9` byte at offset 4096 does not identify an image.
The warning check compares component versions with the build's `dependencies.lock`.
It compares CMake warnings with the ESP-IDF `5.5.6` baseline and checks the `idf` entry in the build's `dependencies.lock`.
Only the two documented upstream CMake notices are in that baseline.

Initial regression command:

```sh
uv run --locked pytest tests/test_release.py tests/test_probe_device.py tests/test_ci.py \
  -q --tb=short -k 'not resolved'
```

```text
32 failed, 63 passed, 2 deselected in 2.16s
FAILED tests/test_release.py::test_new_cmake_warning_is_refused
```

The new CMake warning tests gave `assert False` because the checker ignored those warnings.
The native ESPHome framework-layout tests also stopped before the path check accepted that layout.
The configuration keeps the same warning baseline for native ESPHome and PlatformIO framework paths.

Static and floor-version commands:

```sh
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
UV_PROJECT_ENVIRONMENT="$FLOOR_ENV" UV_LINK_MODE=copy \
  uv run --locked --python 3.12 pytest tests/ -q
actionlint
```

```text
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
106 passed in 13.55s
```

`actionlint` gave exit code 0.
18 changes to the new guards each made the selected tests stop with a failure.
A native C++ harness checked the start guard with one unsuccessful task creation followed by success.
It also checked task-creation failures again and again, and the three-try limit.
Changes to the start guard, retry limit, and error log each stopped a runtime assertion.

All Taskfile `uv run` commands use `--locked`.
The complete gate includes Python 3.12 tests in the ignored `.venv-floor` directory.
The CI compile task copies and compiles the probe with obviously fake credentials in runner temporary storage.
The Gitleaks check and warning check apply to the source output of each configuration.
The root secret gate also checks Git history. CI checks out the complete history.

Device trial: not run (no test device at this time).
No flash, upload, or device connection occurred.

The complete firmware gate used this command:

```sh
ESPHOME_WORK_DIR="$BUILD_ROOT" UV_LINK_MODE=copy task check
```

Result: exit code 0. The default Python and the local Python 3.12 suites each ran 112 tests.
The stock fixture and the probe each compiled and gave 0 new warnings.

```text
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
112 passed in 15.03s
112 passed in 11.15s
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS probe staged; no upload or device connection
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INF no leaks found
INF 6 commits scanned.
INF no leaks found
```

The different Python 3.12 command above gave `112 passed in 14.74s`.
The actual compiled app and factory image bytes also stopped the source-only content check with a `.txt` name.
The checks used synthetic data and compile-only credentials. No device supplied data.

## Trial identifier privacy and native startup tests

Date: 2026-10-25 (UTC).

The stock package adds a hardware-address suffix to the runtime node name.
The reader replaces the full device identifier with a per-trial HMAC-SHA256 identifier before it stores each measurement.
This also removes the configured name from the public output.
Only external scratch storage keeps the random 32-byte salt, in a private file with mode `0600`.
The same trial keeps the same identifier. A different trial uses a new salt.

The trial report and its `.events.jsonl` file contain decoded data with trial identifiers.
Only the external packet log can contain the raw identifier and signed packets.
The salt and packet log must not be in a repository.
No trial result file is available before a receiver run.

The initial regression command selected privacy, native startup, and CI history tests:

```sh
uv run --locked pytest tests/test_probe_device.py tests/test_ci.py -q --tb=short \
  -k 'mac_suffix or trial_token or trial_salt or native_start_guard or missing_native_compiler or history_scans'
```

```text
FAILED tests/test_probe_device.py::test_mac_suffix_is_private_in_report_and_evidence
AssertionError: FAIL native start guard: missing harness source
7 failed, 2 passed, 55 deselected in 0.19s
```

The native harness source is `tests/native/start_guard.cpp`.
The test compiles the actual start function from `tests/probes/transport_probe.h` with the system C++ compiler.
It runs the control and three changed functions that set the guard before success, remove the retry limit, or remove the error log.
An unavailable compiler stops the test with a named failure. The test does not skip that condition.
The CI Ubuntu runner supplies the system C++ compiler.

The CI contract test checks `fetch-depth: 0` before each Git-history secret check.
The check includes Taskfile dependencies.
The `feature.yml` template uses the firmware-specific request about credentials, device names, addresses, and recordings.
All operator commands in the device probe procedure use `uv run --locked`.

The unit and static checks used these commands:

```sh
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest tests/ -q
```

```text
All checks passed!
Success: no issues found in 8 source files
121 passed in 15.48s
```

Eight negative tests changed the identifier, salt, checkout, and start-guard rules.
Each change made the selected test stop with a failure.
The three C++ changes compiled before their runtime assertions stopped.
Device trial: not run (no test device at this time).
No flash, upload, or device connection occurred.

The complete gate and Python 3.12 check used these commands:

```sh
ESPHOME_WORK_DIR="$BUILD_ROOT" UV_LINK_MODE=copy task check
UV_PROJECT_ENVIRONMENT="$FLOOR_ENV" UV_LINK_MODE=copy \
  uv run --locked --python 3.12 pytest tests/ -q
actionlint
```

The complete gate gave exit code 0:

```text
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
121 passed in 14.80s
121 passed in 13.48s
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS probe staged; no upload or device connection
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INF no leaks found
INF 6 commits scanned.
INF no leaks found
```

The different Python 3.12 command gave `121 passed in 15.03s`.
`actionlint` gave exit code 0.

## CMake toolchain parity

Date: 2026-10-25 (UTC).

The local firmware build used the ESPHome-managed CMake `3.30.2`.
Its compile log runs `<IDF_TOOLS_PATH>/tools/cmake/3.30.2/bin/cmake`.
Its `CMakeCache.txt` records that command and version `3.30.2`.
The local system command reports `cmake version 4.4.4`, but that is not the firmware build's executable.

The hosted compiler used an Ubuntu runner image. Its software list contains CMake `4.4.4`.
The hosted log contains four third-party deprecation warnings, from the ESP-NN and TFLite Micro `cmake_minimum_required` calls.
The hosted step printed only the last compile-log lines. It did not record the resolved CMake executable path or version command.
The historical executable path is not available from that log.

By default, ESPHome `2026.10.0` does not install optional CMake when `PATH` has a CMake executable.
The `ESPHOME_IDF_DEFAULT_TOOLS_FORCE` setting changes that selection.
ESP-IDF `5.5.6` marks CMake as `on_request` and recommends version `3.30.2`.
Its tool resolver prefers an installed managed version. Without that version, an optional tool can use the system `PATH`.
The build can use a different CMake version on each system.

Task and CI use the managed CMake installation.
The pre-compile check uses the same ESPHome framework environment as the firmware build.
It checks the ESP-IDF recommendation and the actual executable version against `3.30.2`.
It prints the executable path and version and gives a named failure on mismatch.
The compile-log check also checks the command and version from the actual build cache.

The third-party deprecations are not in the warning baseline.
The pinned build must give 0 new warnings.

Initial regression command:

```sh
uv run --locked pytest tests/test_release.py tests/test_ci.py -q --tb=short \
  -k 'ci_deprecation_fragment or cmake_cache_drift or cmake_preflight or resolver_checks_manifest or cmake_is_forced'
```

```text
FAILED tests/test_release.py::test_ci_deprecation_fragment_reports_cmake_drift
8 failed, 69 deselected in 0.27s
```

The test used all four hosted deprecation lines and a build cache for CMake `4.4.4`.
It stopped because the checker did not identify the toolchain mismatch.
The release and CI suites then gave `77 passed in 0.56s`.

Pre-compile check:

```sh
ESPHOME_IDF_DEFAULT_TOOLS_FORCE='required;cmake' \
  uv run --locked python tools/check_release.py --toolchain
```

```text
Skipping cmake@3.30.2 (already installed)
INFO CMake toolchain: path=<IDF_TOOLS_PATH>/tools/cmake/3.30.2/bin/cmake version=3.30.2
PASS CMake toolchain: version=3.30.2
```

Sources, accessed 2026-10-25 (UTC):

- ESP-IDF tool list: <https://github.com/espressif/esp-idf/blob/v5.5.6/tools/tools.json>, `cmake` entry.
- ESP-IDF tool resolution: <https://github.com/espressif/esp-idf/blob/v5.5.6/tools/idf_tools.py#L2312-L2342>.
- ESPHome installation selection: <https://github.com/esphome/esphome/blob/2026.10.0/esphome/espidf/framework.py#L1284-L1296>.
- ESPHome tool-path resolution: <https://github.com/esphome/esphome/blob/2026.10.0/esphome/espidf/get_idf_tool_paths.py#L31-L45>.
- ESPHome build executable selection: <https://github.com/esphome/esphome/blob/2026.10.0/esphome/espidf/toolchain.py#L200-L209>.
- Hosted image software list: <https://github.com/actions/runner-images/blob/ubuntu26/20261012.163/images/ubuntu/Ubuntu2604-Readme.md>, CMake `4.4.4`.

No device, flash, or upload operation occurred.

The two managed components each use `cmake_minimum_required(VERSION 3.5)`.
A minimal project with that same call reproduces the hosted deprecation with system CMake `4.4.4`.
The same project gives no deprecation with the managed CMake `3.30.2`.
Each configuration command gives exit code 0.

The complete gate used a new external build root:

```sh
ESPHOME_WORK_DIR="$BUILD_ROOT" UV_LINK_MODE=copy task check
UV_PROJECT_ENVIRONMENT="$FLOOR_ENV" UV_LINK_MODE=copy \
  uv run --locked --python 3.12 pytest tests/ -q
actionlint
```

The complete gate gave exit code 0:

```text
8 files already formatted
All checks passed!
Success: no issues found in 8 source files
129 passed in 13.56s
129 passed in 13.05s
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
INFO CMake toolchain: path=<IDF_TOOLS_PATH>/tools/cmake/3.30.2/bin/cmake version=3.30.2
PASS CMake toolchain: version=3.30.2
INFO Successfully compiled program.
INFO CMake build: path=<IDF_TOOLS_PATH>/tools/cmake/3.30.2/bin/cmake version=3.30.2
PASS compile warnings: new_warnings=0
PASS probe staged; no upload or device connection
INFO Successfully compiled program.
INFO CMake build: path=<IDF_TOOLS_PATH>/tools/cmake/3.30.2/bin/cmake version=3.30.2
PASS compile warnings: new_warnings=0
INF no leaks found
INF 7 commits scanned.
INF no leaks found
```

The different Python 3.12 command gave `129 passed in 15.84s`.
`actionlint` gave exit code 0.
Six changes to the installation policy, manifest check, version checks, and check order each made a selected test stop with a failure.
The stock fixture and probe each compiled from a new build tree with CMake `3.30.2` and 0 new warnings.
No hosted run of this change occurred at this time.

## Authenticated firmware timing

Date: `2026-10-25` (UTC).

The server protocol is the authority for encoding. See [Device timing events](protocol.md) for configuration and signal limits.
The firmware fixture is a byte-identical copy of the server vectors.

The initial vector test gave this result:

```text
ModuleNotFoundError: No module named 'tests.event_vectors'
1 failed in 0.01s
```

Commands:

```sh
uv run --locked pytest tests/ -q
ESPHOME_WORK_DIR="$CHECK_TMP" task check
UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT="$CHECK_TMP/venv312" uv run --locked --python 3.12 pytest tests/ -q
```

The complete gate gave exit code 0 with these result lines:

```text
11 files already formatted
All checks passed!
Success: no issues found in 11 source files
141 passed in 62.94s (0:01:02)
141 passed in 65.67s (0:01:05)
PASS
PASS
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
PASS config warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS probe staged; no upload or device connection
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INF no leaks found
INF 7 commits scanned.
INF no leaks found
```

The two production compiles select UDP and WebSocket explicitly.
The different Python 3.12 command gave `141 passed in 60.86s (0:01:00)`.
`actionlint` gave exit code 0. The warning rules for pinned upstream components did not change.

Vector-copy commands:

```sh
cmp "$SERVER_SOURCE/protocol/device-vectors.json" tests/fixtures/device-vectors.json
sha256sum "$SERVER_SOURCE/protocol/device-vectors.json" tests/fixtures/device-vectors.json
uv run --locked python -m tests.event_vectors
```

`cmp` gave exit code 0. The two SHA-256 values were:

```text
b74cf28042f22e9bd85520a864f335e0f61fddbd99559ce458f78cd5b540bc89
```

The native command gave two `PASS` lines.
It compiles the actual codec and component code with the system C++ compiler.
A missing compiler gives a named failure, not a skip.
The vector harness checks all bytes at the HMAC input and the tag at the output.
The pinned ESP-IDF mbedTLS function supplies HMAC-SHA256 in firmware.
The native test does not test the ESP-IDF hash function on a device.

Native simulations check boot changes, increasing sequences, overflow drops, worker failure, DNS caching, retry, and transport output.
The timestamp lambda reads two different device times at two calls.
The configuration checks keep all stock components and all stock callback steps unchanged.
Only the listed telemetry steps append to the stock wake and command callbacks.
The media-player callback adds to the stock callback list.

### Credential output

The component uses a `_DeviceKey` value with a masked `repr`, `str`, and type-specific YAML representation.
Only code generation reads its private bytes.
Usual and `--show-secrets` configuration tests for the two transports find no complete fake HMAC key in stdout or stderr.
Other value types keep their previous YAML output.

Native log capture for the two variants gave `secret_matches=0` for the fake key canary and its hexadecimal text.
A negative compile test shows that the C++ key buffer has `protected` access.
It has no getter, entity, or diagnostic field.
Fixture credentials are public fake values. The checks used no actual device credential.

The firmware must contain the key. A search of `main.cpp` is not a check for safe key storage.
Keep all build output private and do not publish firmware images.
The stock ESPHome password display can keep bytes between terminal control codes after package loading.
This upstream limit does not change the component's HMAC-key rule. See the source URLs in `docs/protocol.md`.

### Behavioral mutations

Each mutation compiled and then caused a test failure:

1. Remove `stage` from the signed bytes: canonical-byte assertion failure.
2. Use little-endian integers: canonical-byte assertion failure.
3. Restart the sequence without a new boot identifier: increasing-sequence assertion failure.
4. Use host time as device time: monotonic-time assertion failure.
5. Wait on a full send queue: zero-wait assertion failure.
6. Print the key: secret-canary output assertion failure.
7. Mark a media-player proxy as measured: playback-quality assertion failure.

All seven mutations compiled before the behavioral test.

Device trial not run: no test device at this time.
The `mic_open` source is the public `voice_assistant.on_start` proxy, not a first-packet measurement.
The device trial must measure its interval to the actual command-audio stream start.
Transport selection, sample-callback validation, and native-function latency measurements stay open.

### Public source checks

Command:

```sh
uv run --project "$WORKSPACE/assist-live" python "$WORKSPACE/assist-live/tools/check_public_tree.py" --root . --private-denylist "$PRIVATE_DENYLIST" --history
```

Result:

```text
PASS own Git root
PASS history secrets commits=7
PASS public data matches=0
```

A source check also gave `denylist_matches=0`, `home_path_matches=0`, and `private_ipv4_matches=0` across 69 public files.

## Firmware data and build controls

Date: `2026-10-25` (UTC).

The key-output check uses each window of six or more key bytes.
It checks raw ASCII, lowercase hexadecimal text, and decimal text with and without separators.
The same check runs on captured runtime logs and configuration output.
Decimal log fields, decimal CSV output, and an eight-byte hexadecimal prefix each cause a test failure.

A native test uses two `std::thread` objects to start and end 100 turns.
It checks one `mic_open` event for each turn and no drop.
The command state uses `std::atomic<bool>` with `exchange`.
The production templates do not contain the probe-token substitution.

The worker parses JSON with ArduinoJson `7.4.3` and compares canonical bytes before signing.
Tests refuse malformed JSON, duplicate keys, incorrect key order, whitespace, invalid UTF-8, and values above the documented limits.
The native tests download the same pinned header and check its SHA-256.
See [runtime limits](protocol.md#automation-and-runtime-limits) for the numeric and nesting restrictions.

UDP socket initialization and WebSocket transport initialization can retry after five seconds.
Tests check the retry interval, failure counter, and warning output.
The CMake preflight reads the IDF version from the fixture dependency lock.
The actual build lock must use the same IDF version.
The local and CI preflights select only `esp32s3`.

Commands:

```sh
ESPHOME_WORK_DIR="$CHECK_TMP" PRIVATE_DENYLIST="$PRIVATE_DENYLIST" task check
UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT="$CHECK_TMP/venv312" uv run --locked --python 3.12 pytest tests/ -q
uv run --locked pytest tests/test_event_vectors.py -q
actionlint
```

The complete gate gave exit code 0:

```text
13 files already formatted
All checks passed!
Success: no issues found in 13 source files
171 passed in 62.72s (0:01:02)
171 passed in 65.71s (0:01:05)
PASS
PASS
PASS firmware bootstrap
PASS source-only release
PASS config warnings: new_warnings=0
PASS config warnings: new_warnings=0
PASS CMake toolchain: version=3.30.2
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS CMake toolchain: version=3.30.2
PASS probe staged; no upload or device connection
INFO Successfully compiled program.
PASS compile warnings: new_warnings=0
PASS own Git root
PASS history secrets commits=10
PASS public data matches=0
```

The two production builds and the unchanged probe each recorded managed CMake `3.30.2` in the actual build cache.
Source and history secret checks gave `no leaks found`.
The different Python 3.12 command gave `171 passed in 66.89s (0:01:06)`.
The event suite gave `16 passed in 52.46s`. `actionlint` gave exit code 0.
The vector `cmp` gave exit code 0. The two SHA-256 values stayed `b74cf28042f22e9bd85520a864f335e0f61fddbd99559ce458f78cd5b540bc89`.

The 16 native and output mutations, 13 Python and pipeline mutations, and seven initial numbered mutations each caused a test failure.
Native behavioral mutations compiled before the assertion failure.
No compiler failure counts as a behavioral result.

The public-data check is mandatory in `task check` and CI.
With no external denylist, its output includes `NOT CHECKED private denylist` and `PASS public data matches=0`.
Private-path and private-address checks run in that mode.
The external denylist run gave `PASS public data matches=0`.

Device trial not run: no test device at this time.
