# Archclt

Archclt helps coding agents change a Python project while preserving reviewed
architecture. It connects a scoped change contract to component boundaries,
ADRs, source evidence and real verification commands, then reports `passed`,
`failed`, `unknown` or `error` with retained evidence.

The command is **`archctl`**. The npm package is **`@archclt/archctl`** and the
Python package is **`archclt`**. Python 3.11+ and Git are required; the npm
launcher also needs Node.js 20+. Linux and macOS are the initial supported
platforms; Windows packaging remains experimental.

## Install

```bash
npm install -g https://github.com/sij0sh/archclt/releases/download/v0.2.0/archclt-archctl-0.2.0.tgz
archctl setup
export ARCHCTL_BIN="$(archctl --runtime-path)"
archctl install-skill "$HOME/.agents/skills"
```

The npm package bundles the exact Python wheel. Setup creates an isolated
runtime outside your project and installs its pinned PyYAML dependency; it
requires network access on first setup. `ARCHCLT_PYTHON` selects Python and
`ARCHCLT_HOME` selects an external runtime directory. There is no install hook.

The registry name is `@archclt/archctl`; after its first registry publication,
`npm install -g @archclt/archctl@0.2.0` selects the same release.

For a direct Python installation:

```bash
pipx install https://github.com/sij0sh/archclt/releases/download/v0.2.0/archclt-0.2.0-py3-none-any.whl
archctl --version
```

Use the versioned GitHub release artifacts before the first registry publication.
See [installation](docs/install.md) for wheel installation and the skill bundle.

Native source evidence requires a compatible, separately installed
[Briefcase](https://github.com/sij0sh/briefcase-release) executable. Set `BRIEFCASE_BIN`
to its absolute path. You can also supply a trusted normalized evidence bundle.
Read the [compatibility and evidence limits](docs/briefcase-integration.md).

## Adopt a Python project

From its Git root, run `archctl init`. This creates an empty, unreviewed
`architecture/model.yaml`. Use the bundled `architecture-control` skill to
inspect the source and propose real components, ADRs, constraints and commands.
Review that intent, commit it and choose the baseline:

```bash
git tag archctl-baseline <reviewed-full-commit-sha>
archctl briefcase export-evidence --source-root src
archctl gate --baseline-ref "$(git rev-parse archctl-baseline)" --scope all --run
```

For a change, record `.archctl/change.yaml` with component/file scope and
acceptance criteria mapped to reviewed verification IDs, then run:

```bash
archctl gate --baseline-ref "$(git rev-parse archctl-baseline)" \
  --change .archctl/change.yaml --source-root src --run
```

Read the newly printed run directory's `gate-summary.md` and JSON. A pass
covers required obligations within reported scope and coverage. Missing or
stale evidence, unexecuted required checks and unresolved scope remain unknown.
A gate never approves architecture authority or advances a baseline itself.

## Contracts and limits

One v2 contract family defines authoring, evidence, impact, verification and
reports. Strict enforcement is the default; advisory policy obligations remain
explicit and visible. [Migration](docs/authoring.md#obligation-strength) converts
legacy intent without overwriting it.

Native mapping assesses Python imports. Dynamic imports, other languages and
runtime structure remain explicit gaps. Reviewed commands execute application
code with your privileges. Run the evaluator outside the candidate repository;
Archclt is a review workflow, not a security sandbox or merge controller.

## Develop

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python scripts/demo.py
.venv/bin/python scripts/validate.py
```

Storefront is a development fixture. Generated validation results stay local or
become CI artifacts. See [contributing](CONTRIBUTING.md),
[architecture](ARCHITECTURE.md), [authoring](docs/authoring.md),
[CLI contracts](docs/cli-contracts.md), [support status](docs/status.md) and
[release notes](CHANGELOG.md).

MIT licensed.
