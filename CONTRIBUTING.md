# Contributing

Create a development environment with `python3 -m venv .venv` and install
`.[dev]`. Use the commands in [AGENTS.md](AGENTS.md) to validate changes.
The editable installation is for development; application gates use a reviewed
external evaluator.

Read [ARCHITECTURE.md](ARCHITECTURE.md) and governing ADRs before changing module
boundaries. Core remains independent, Atlas does not import Guard, and Guard and
Observatory share the process adapter. Intended and observed types stay separate.

For adopted development, use the bundled architecture-control skill. Record scope
and acceptance criteria in `.archctl/change.yaml`; gate against the independently
reviewed `archctl-baseline` commit. Authority and command changes require operator
review. A gate pass is bounded by scope and coverage and does not approve itself.

Storefront lives under `tests/fixtures/`. `scripts/demo.py` runs the reviewed
integration regression; it is development tooling. Its exporter is fixture-only.
Keep positive, negative and false-pass regressions when modifying contracts.

`scripts/generate_schemas.py` maintains the single `contracts/v2/` family.
`scripts/validate.py` runs tests, builds distributions and exercises the installed
wheel. Outputs go under ignored `.archctl/validation/`; skips stay visible.
Native interoperability uses separately reviewed `ARCHCTL_BIN` and `BRIEFCASE_BIN`.

For releases, follow [docs/releasing.md](docs/releasing.md). Test the wheel,
extracted source distribution and npm tarball. Publish artifacts from a clean
source tag and attach checksums and the versioned skill bundle. Source archives
exclude local evidence, validation runs, environments and caches.
