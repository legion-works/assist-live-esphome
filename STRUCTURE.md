# Repository structure

| Path | Purpose |
| --- | --- |
| `components/assist_live/` | Python schema and C++ placeholder component |
| `examples/voice-pe.yaml` | Local-source example that extends the stock Voice PE package |
| `tests/test_package.py` | Source-only boundary test |
| `tests/fixtures/voice-pe.yaml` | Compile-only configuration |
| `tests/fixtures/secrets.yaml` | Four fake values for the compile fixture |
| `tools/check_bootstrap.py` | Source, package, license, and privacy checks |
| `docs/verification.md` | Test commands, results, and source URLs |
| `pyproject.toml` | Python requirements and development dependencies |
| `uv.lock` | Locked Python dependency versions |
| `LICENSE` | Full GPL version 3 text |
| `THIRD_PARTY_NOTICES.md` | External framework and package notices |

The root Markdown files give the project and contribution rules.

- `.gitignore` keeps build files and actual secrets out of Git.
- `tests/fixtures/.gitignore` keeps the fixture build output out of Git without a second secrets rule.
- `.editorconfig` sets the source text format.
