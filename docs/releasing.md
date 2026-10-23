# Releasing

Release source lives at https://github.com/sij0sh/archclt. The Python distribution
is `archclt`, npm is `@archclt/archctl`, and the entrypoint is `archctl`.
Versions in `src/archctl/__init__.py` and `package.json` must agree. Contract
versions are independent: governed v2 and advisory context v1.

## Validate and build

1. Install `.[dev]` in a development environment. Provision separately reviewed
   `ARCHCTL_BIN` and `BRIEFCASE_BIN` for governed checks; record their release,
   source and artifact hashes outside tracked source. Never use candidate tools
   as independent evaluators or evidence producers for their own acceptance.
2. Run `python3 scripts/validate.py` and `npm test`. Release validation retains
   tests, skips, installed-wheel smoke and artifact hashes under
   `.archctl/validation/`. Native preparation additionally needs a reviewed v2
   exporter selected by `ARCHCTL_RELEASE_EXPORTER`; unavailable checks remain
   explicitly not executed.
3. Run `python3 scripts/release_artifacts.py`. It builds a wheel and source
   archive, a versioned skill ZIP, an npm tarball and `SHA256SUMS` under `dist/`.
   Inspect package contents. The source archive must be sufficient for contract
   tests; the npm tarball must install and run from another directory.
4. Use the independently reviewed local gate against the selected baseline.
   Review authority or verification-command changes before advancing it.
5. Commit clean source, tag `v<version>` and push the tag to run the release
   workflow. GitHub artifacts and registry publishing consume the same builds.

## First publication

The workflow can produce and attach GitHub release artifacts without registry
credentials. Configure PyPI's `archclt` project and npm's `@archclt/archctl`
package with trusted publishers for this repository and release workflow.
Initial registry bootstrap may require account-side setup. Enable registry
publishing with repository variable `PUBLISH_REGISTRIES=true` only after that
setup and review. GitHub's `release` environment can carry operator approval.
No long-lived registry token belongs in source.

Install the published artifacts in a fresh external project and confirm
`--version`, neutral `init`, readiness, native evidence and a local gate.
This is application compatibility validation, distinct from independent
acceptance of changes to Archclt itself.

## Briefcase compatibility

Native import mapping targets Briefcase 0.1.0's public JSON operations. Use its
release binary and checksum for the supported platform. Archclt's source-only
checks do not prove that a particular native build interoperates. Preserve
skips and record the binaries exercised by an interoperability run.
