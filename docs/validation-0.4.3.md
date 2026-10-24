# Validation of the 0.4.3 source update

Status: passed with one optional integration skip. Date: October 24, 2026.

## Scope

- Resolve the repository root before reading memory records. This fixes macOS roots
  reached through `/var`, which resolves to `/private/var`.
- Add regression coverage for memory reads through a symlinked repository root.
- Run CI actions on Node 24 and pin Linux jobs to Ubuntu 24.04.
- No normalized contract, gate, guard, memory or workflow semantics change.
- Current release documentation and package metadata move to 0.4.3.

## Executed checks

Environment: Python 3.12.13, PyYAML 6.0.3, Briefcase 0.1.1 on Linux.

| Check | Result |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` | 202 tests passed, 1 skipped |
| `PYTHONPATH=src .venv/bin/python -m unittest tests.test_context tests.test_context_pivot tests.test_context_contracts tests.test_memory_migration` | 45 tests passed |
| `PYTHONPATH=src .venv/bin/python scripts/demo.py` | passed with expected failed and unknown outcomes |
| `PYTHONPATH=src .venv/bin/python scripts/demo_context.py` | passed with retained limitations |
| `PYTHONPATH=src .venv/bin/python scripts/validate.py` | `passed_with_optional_checks_unavailable`; installed wheel smoke passed |
| `npm test` | 2 launcher tests passed |
| `PYTHONPATH=src .venv/bin/python scripts/smoke_npm.py` | passed at 0.4.3 |
| `twine check` on the wheel and sdist | passed |
| `sha256sum -c dist/SHA256SUMS` | all four artifacts passed |

## Skips and limits

- `test_pinned_tools_support_archctl_and_roast_layouts` skipped because a reviewed
  v2 exporter and Briefcase binary were not configured. Pinned preparation remains
  unexecuted.
- The symlinked-root regression exercises the path normalization locally. The
  macOS failure itself is covered by the push CI matrix once it runs.
- Compatibility is verified only for Briefcase's Python import scope. Other
  languages, dynamic imports and runtime behavior remain unsupported.
- No registry publication or independent external acceptance is claimed.
