# Validation of the 0.3.0 source update

Run date: October 23, 2026. Environment: Python 3.12.13 on Linux with `jsonschema` installed and Briefcase 0.1.0 on `PATH`.

## Results

| Check | Result |
|---|---|
| Full regression suite | 173 tests: 172 passed, 1 skipped, 0 failures, 0 errors |
| Native Briefcase integration | Passed against Briefcase 0.1.0 |
| Prepared-evidence interoperability | 1 check skipped: pinned reviewed exporter unavailable |
| JSON Schema conformance | Passed with `jsonschema` installed |
| Published advisory-schema regeneration | Passed; committed schemas match the generator |
| Original governed demo | Passed all four expected valid/stale/violation/changed-authority scenarios |
| Context demo | Passed cold-start retrieval, stale reasoning, historical replacement, concurrent pure batching and baseline-free verification |
| Bundled agent skill validation | Passed front matter and metadata checks |
| Python wheel build and isolated installed smoke | Passed; imports resolved to the installed wheel |
| Installed context and independent verification | Assembled useful partial context; command passed with current recorded inputs |
| Installed v2 compatibility | Status, impact, Guard, workflows, composite gate and selective advisory behavior passed |
| Python source distribution | Built and exercised by the distribution regression |
| npm launcher tests | Passed 2 tests with 0.3.0 metadata |
| Packed npm artifact | Installed in an external project; version, external runtime, neutral status, exit status and skill installation passed |
| Release artifacts | Wheel, source archive, npm tarball, skill ZIP and SHA256SUMS built; `twine check` passed |

The normal source test command is:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The tests include new greenfield, reuse-retrieval, standalone ADR, cold-start memory,
conflict, supersession, freshness, rename alias, proposed cycle, same-component
import, independent execution, harness import and input-integrity scenarios.

The distribution regression copies npm and hosted-CI assets when present, while
still building a real wheel and source distribution and running contracts from
the extracted source. npm launcher unit tests run separately; the hosted release
workflow was not executed locally.

Native interoperability and schema conformance were exercised in this environment.
They remain environment-dependent and must report explicit skips when the matching
binary or optional validator is absent. Fixture-level tests and schema regeneration
do not substitute for those checks. The update makes no empirical claim about
measured reductions in agent-induced technical debt; that requires controlled
multi-task agent evaluation.
