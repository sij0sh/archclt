# Installation

## Source update 0.3.0

Install the Python project from this source with `python3 -m pip install -e .`,
or build a wheel with `python3 -m pip wheel --no-deps --no-build-isolation .`.
Copy `skills/architecture-control/` to your coding agent's skill directory.
Start with `archctl context '<task>' --paths ...`; adoption is optional.

The release workflow publishes the 0.3.0 wheel, source archive, skill ZIP and
npm tarball when `v0.3.0` is tagged. Registry publication follows that release and
is controlled by `PUBLISH_REGISTRIES`. Context and ordinary verification may use
a project environment; external reviewed evaluators are required only by the
governed gate.

Use the CLI `archctl`, distributed as npm `@archclt/archctl` or Python `archclt`.
Python 3.11+ and Git are required. npm also requires Node.js 20+.

## npm

```bash
npm install -g https://github.com/sij0sh/archclt/releases/download/v0.3.0/archclt-archctl-0.3.0.tgz
archctl setup
export ARCHCTL_BIN="$(archctl --runtime-path)"
archctl install-skill "$HOME/.agents/skills"
```

First setup installs the bundled, checksum-checked wheel and PyYAML 6.0.3 into
`~/.local/share/archclt/<version>/<wheel-hash>/`. Subsequent commands reuse that
runtime. Setup writes progress to stderr so JSON command output stays parseable.
Set `ARCHCLT_PYTHON` to an absolute Python interpreter or `ARCHCLT_HOME` to a
user-owned directory outside source checkouts. The launcher preserves the
application's working directory, PATH, streams and command exit status.

The same launcher supports `npx --package @archclt/archctl@0.3.0 archctl` and
project development dependencies; its evaluator still lives outside the project.
Registry commands become available after the first release is published.

## Python or release wheel

```bash
pipx install https://github.com/sij0sh/archclt/releases/download/v0.3.0/archclt-0.3.0-py3-none-any.whl
```

For the first release or an offline install, download `archclt-0.3.0-py3-none-any.whl`
and `SHA256SUMS` from the corresponding GitHub release. Verify the hash, then:

```bash
python3 -m venv "$HOME/.local/opt/archclt/0.3.0"
"$HOME/.local/opt/archclt/0.3.0/bin/python" -m pip install \
  /path/to/archclt-0.3.0-py3-none-any.whl
export ARCHCTL_BIN="$HOME/.local/opt/archclt/0.3.0/bin/archctl"
```

For offline installation, provision a compatible PyYAML 6.x wheel and use
`--no-index` with explicit wheel paths. Keep the evaluator outside the application
and outside source checkouts. Application tests use their own environment.

## Agent skill

npm includes `skills/architecture-control/`. `archctl install-skill` copies it
without overwriting an existing skill. The GitHub release also includes a
versioned skill ZIP. Extract the complete directory into the agent's skills
location; `SKILL.md` and `references/` are self-contained. The Python wheel
contains the CLI; obtain the skill separately from the same release.

## Evidence producer

Install the reviewed Briefcase release identified in
[the compatibility guide](briefcase-integration.md), outside source checkouts.
Set `BRIEFCASE_BIN` to its absolute executable path. Flags override the variable.
A normalized `archctl.evidence.v2` bundle from a trusted producer is also supported.

Native export assesses Python imports only. Preparation requires explicit source
roots and fresh output directories. It runs verification in the full application,
not its evidence projection. Keep missing and partial coverage visible.

## Upgrade and adoption

Install the new version alongside the reviewed one. Verify model validation,
evidence export and a representative application gate before changing the project
pin. Review one-way model migration and select the new baseline deliberately.
See [authoring](authoring.md) for optional adoption or [context](context.md) for ordinary tasks.
