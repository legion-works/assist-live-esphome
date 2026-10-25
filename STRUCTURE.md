# Repository structure

| Path | Purpose |
| --- | --- |
| `components/assist_live/` | Python schema, authenticated event codec, and bounded timing sender |
| `examples/voice-pe.yaml` | Local-source example that extends the stock Voice PE package |
| `tests/test_package.py` | Source-only boundary test |
| `tests/fixtures/voice-pe.yaml` | Compile-only configuration |
| `tests/fixtures/secrets.yaml` | Six fake values for the compile fixtures |
| `tests/fixtures/voice-pe-udp.yaml` | Explicit UDP compile variant |
| `tests/fixtures/voice-pe-websocket.yaml` | Explicit WebSocket compile variant |
| `tests/fixtures/device-vectors.json` | Byte-identical server authentication vectors |
| `tests/event_vectors.py` | System C++ compiler runner for codec and runtime harnesses |
| `tests/test_event_vectors.py` | Codec, runtime, compiler, and automation checks |
| `tests/native/event_vectors.cpp` | HMAC input, canonical-byte, and wire-output contract harness |
| `tests/native/event_runtime.cpp` | Queue, sequence, DNS, callback, and log simulation |
| `tests/native/include/` | Minimal SDK test doubles for the native runtime harness |
| `tests/probes/transport.yaml` | Device-trial configuration that extends stock Voice PE |
| `tests/probes/transport_probe.h` | Authenticated UDP and WebSocket probe worker |
| `tests/native/start_guard.cpp` | Native harness for the actual worker start function and its three mutations |
| `tests/test_probe_device.py` | Probe, external file copy, and measurement tests |
| `tools/probe_device.py` | External file copy and bounded receiver for device trials |
| `tools/check_release.py` | Source-only boundary and build-warning checks |
| `tests/fixtures/dependencies.lock` | ESP-IDF version for the CMake preflight |
| `tools/check_public_tree.py` | Public-data checks for source and Git history |
| `tests/test_public_tree.py` | Private-path, private-address, and optional denylist checks |
| `LICENSES/Apache-2.0.txt` | License for the public-data checker |
| `tests/test_release.py` | Image detection and warning-baseline tests |
| `docs/research/q1-device-probe.md` | Device probe procedure and sources |
| `docs/research/q1-device-trial.md` | Output from an armed run. No file before a trial |
| `docs/research/q1-device-trial.events.jsonl` | Decoded measurements with trial identifiers. No file before a trial |
| `tools/check_bootstrap.py` | Source, package, license, and privacy checks |
| `docs/verification.md` | Test commands, results, and source URLs |
| `docs/protocol.md` | Server-contract URL, credential rules, and firmware signal limits |
| `pyproject.toml` | Python requirements and development dependencies |
| `uv.lock` | Locked Python dependency versions |
| `LICENSE` | Full GPL version 3 text |
| `THIRD_PARTY_NOTICES.md` | External framework and package notices |

The root Markdown files give the project and contribution rules.

- `.gitignore` keeps build files and actual secrets out of Git.
- `tests/fixtures/.gitignore` keeps the fixture build output out of Git without a second secrets rule.
- `.editorconfig` sets the source text format.
