# Archclt

Archclt gives coding agents architectural context and memory alongside Briefcase.
It brings together relevant code relationships, reasons behind existing choices,
potential reuse, downstream impact and verification results so the agent can
choose and evolve a design with less repeated investigation.

The command is **`archctl`** and the Python package is **`archclt`**. Python 3.11+
is required. Git is needed for `--changed` and the optional governed workflow.

## Start without adoption

```bash
python3 -m pip install -e .
archctl context 'Reuse API batching for concurrent workers' \
  --paths src/api/batching.py src/worker/jobs.py
```

No architecture model, approval tag or task contract is needed. Missing evidence
and provisional components remain visible in the context packet. The agent makes
the design choice within the user's task, runs useful checks, and records reasons
that would be costly for the next agent to forget.

```bash
archctl context 'Reuse batching' --paths src/worker/jobs.py src/api/batching.py \
  --dependency src/worker/jobs.py src/api/batching.py
archctl memory record --input .archctl/reason.json
archctl verify run --task 'Worker regression' --paths 'src/worker/**' \
  --command '["python3", "-m", "unittest", "tests.test_worker"]'
```

[The context guide](docs/context.md) covers rationale records, conversation
references, optional component aliases, hypothetical dependencies, independent
verification and agent integration. Copy the bundled
`skills/architecture-control/` directory into your coding agent's skill location
to apply the workflow at task start and completion.

## Briefcase evidence

Briefcase owns source analysis and retained evidence. Archclt reuses a supplied
`archctl.evidence.v2` bundle or the existing native Python import mapper:

```bash
archctl context 'Change the payment response' --paths src/payments/api.py \
  --refresh-evidence --source-root src
```

Set `BRIEFCASE_BIN` or pass `--briefcase`. Native mapping remains limited to the
documented Briefcase 0.1.1 Python imports. Other languages can be inventoried and
retrieved as source candidates; their dependencies are not inferred. Conversation
and Case references come from the coding agent rather than a session API.
Read [compatibility and evidence limits](docs/briefcase-integration.md).

## Optional architectural gates

The existing reviewed-model workflow remains available through `init`, `model`,
`status`, `impact`, `guard`, `observe` and `gate`. Its v2 meanings, required
obligations, baseline checks and execution restrictions remain intact. Choose it
explicitly when architectural acceptance needs a reviewed baseline. Context and
ordinary verification never require that adoption.

See [authoring](docs/authoring.md), [CLI contracts](docs/cli-contracts.md),
[installation](docs/install.md), [support status](docs/status.md) and
[release notes](CHANGELOG.md).

## Develop and validate

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python scripts/demo_context.py
PYTHONPATH=src .venv/bin/python scripts/demo.py
```

The context demo exercises cold-start reasoning, reuse, changed assumptions and
verification without architecture adoption. The original demo exercises governed
behavior. Native interoperability and optional schema skips remain visible.

The release workflow builds the Python wheel, source archive, skill ZIP and npm
tarball from the tagged commit. npm launcher tests run with `npm test`.

MIT licensed.
