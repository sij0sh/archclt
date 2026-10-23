# Validation of the 0.4.0 source update

Status: passed with one optional integration skip. Date: October 23, 2026.

## Scope

- One public contract version, v2.
- Advisory contracts moved from `contracts/context/v1` to `contracts/context/v2`.
- Ten legacy memory records migrated to `archctl.memory.v2`; the repository now has
  16 records, including the consolidation decision, family independence and migration reasoning.
- Legacy authoring v1 input and `archctl model migrate` removed from 0.4.0.
- Governed gate semantics and outcomes unchanged.
- External `pi-archctl` 0.3.0 accepts only v2 and requires archctl 0.3.0 or newer.

## Executed checks

| Check | Result |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` | 186 tests passed, 1 skipped (187 run) |
| `PYTHONPATH=src .venv/bin/python scripts/demo.py` | expected passed, failed, unknown and authority-changed outcomes |
| `PYTHONPATH=src .venv/bin/python scripts/demo_context.py` | cold start, stale reason, supersession and v2 execution passed |
| `PYTHONPATH=src .venv/bin/python scripts/validate.py` | `passed_with_optional_checks_unavailable`; schema conformance passed; installed wheel smoke passed |
| Installed wheel 0.4.0 | context, execution and memory outputs used the v2 contracts |
| `npm test` | 2 launcher tests passed |
| `npm pack --dry-run` | `@archclt/archctl@0.4.0`, 16 files, bundled wheel present |
| `pi-archctl` `npm test` | 40 tests passed |
| `pi-archctl` `npm run test:integration` | 13 tests passed |
| `pi-archctl` `npm run release:check` | passed; `pi-archctl@0.3.0`, 7 shipped files |
| Out-of-session adapter smoke | `archctl.status.v2`, `needs_attention`, gate `not_executed`, approval `not_assessed`, exit 2 |
| `archctl model validate` | passed at revision `7def7263de5a8258ef546830f227732a60fde0cdcad070fee7e3d03f60faab5b`, 9 components |
| `archctl status` | `needs_attention` only because `.archctl/evidence.json` is absent; model valid; gate `not_executed`; approval `not_assessed` |
| `archctl memory list` | 16 records, all `archctl.memory.v2` |
| `archctl verify run` | full regression passed with current scoped inputs; `archctl.execution.v2`; record `.archctl/executions/8aac09437e694b378d82afcb1acc56f1.json` |

The wheel recorded by `scripts/validate.py` was
`archclt-0.4.0-py3-none-any.whl`, 72,629 bytes, SHA-256
`e8d6c72ca6ef52da37411d450ce6d370b034f87bd22086ddf49e1275ff97b971`.

## Skips and limits

- `test_pinned_tools_support_archctl_and_roast_layouts` skipped because a reviewed
  v2 exporter and Briefcase binary were not configured. Native interoperability
  is not independently proven by this record.
- The release validation summary labels native interoperability as passed despite
  that optional skip; the skip is the authoritative check result here.
- The installed smoke used the bundled wheel, not a published registry artifact.
- No external inventory proves that every v1 consumer has migrated.
- `npm pack` requires an environment with setuptools; the local system `python3`
  lacked it, so the check used the project virtual environment on `PATH`.
- The memory migration was verified on repository records and a temporary legacy
  record. It does not prove that external memory collections are complete.
- A follow-up run with `ARCHCTL_RELEASE_EXPORTER=/home/joshsimon/.local/bin/archctl`
  (`archctl 0.4.0`) and
  `BRIEFCASE_BIN=/home/joshsimon/.local/opt/briefcase/adf8ff83d647825f3b3869b91b91ff1707b3fa1e/briefcase`
  (Briefcase 0.1.0) passed all 187 tests, executed pinned preparation and
  reported 6 prepared pins.
- The standalone Pi `arch_context` adapter still rejects the current CLI:
  `archctl status returned archctl.status.v2; expected archctl.status.v1`. Use
  the `archctl` CLI directly until that adapter is updated.
