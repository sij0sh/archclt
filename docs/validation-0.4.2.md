# Validation of the 0.4.2 source update

Status: passed with one optional integration skip. Date: October 24, 2026.

## Scope

- Declares Briefcase 0.1.1 Python import support; the support profile moves from
  `briefcase-0.1.0-python-imports` to `briefcase-0.1.1-python-imports`.
- No normalized contract, gate, guard, memory or workflow semantics change.
- Current release documentation and package metadata move to 0.4.2.

## Executed checks

Environment: Python 3.12.13, PyYAML 6.0.3, Briefcase 0.1.1 on Linux.

| Check | Result |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` | 201 tests passed, 1 skipped |
| `PYTHONPATH=src .venv/bin/python -m unittest tests.test_briefcase_native` | 11 tests passed against the real Briefcase 0.1.1 binary |
| `PYTHONPATH=src .venv/bin/python scripts/demo.py` | passed with expected failed and unknown outcomes |
| `PYTHONPATH=src .venv/bin/python scripts/demo_context.py` | passed with retained limitations |
| `PYTHONPATH=src .venv/bin/python scripts/validate.py` | `passed_with_optional_checks_unavailable`; installed wheel smoke passed |
| `npm test` | 2 launcher tests passed |
| `PYTHONPATH=src .venv/bin/python scripts/smoke_npm.py` | passed at 0.4.2 |
| `twine check` on the wheel and sdist | passed |
| `sha256sum -c dist/SHA256SUMS` | all four artifacts passed |

## Skips and limits

- `test_pinned_tools_support_archctl_and_roast_layouts` skipped because a reviewed
  v2 exporter and Briefcase binary were not configured. The native tests did run
  against the installed Briefcase 0.1.1 binary, but pinned preparation remains
  unexecuted.
- Briefcase v0.1.1 has a source tag and no published GitHub release assets. The
  interoperability run used the locally built binary from that tag. Reviewed
  release archives and checksums remain a prerequisite for the governed install
  path.
- Compatibility is verified only for Briefcase's Python import scope. Other
  languages, dynamic imports and runtime behavior remain unsupported.
- No registry publication or independent external acceptance is claimed.
