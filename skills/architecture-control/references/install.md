# Install and select tools

For ordinary context-first work, use the project's selected Python environment
or an installed `archclt` distribution, and copy this skill directory to the
agent's skill location. No external approved evaluator or baseline is required.
`archctl context` works without Briefcase, retaining dependency gaps; refresh
only with a compatible installed Briefcase executable. The reviewed installation
procedures below apply to optional governed v2 acceptance.

Install the versioned `@archclt/archctl` npm package or `archclt` Python package
outside the application. With npm, run `archctl setup`, then set `ARCHCTL_BIN`
to the absolute path printed by `archctl --runtime-path`. With pipx, select the
absolute installed entrypoint. Python 3.11+ and Git are required.

Provision the compatible Briefcase executable for native Python import evidence;
set `BRIEFCASE_BIN` to its absolute path outside source checkouts. A separately
trusted producer can instead supply normalized `archctl.evidence.v2`.
Record release versions and artifact hashes. The release source is
https://github.com/sij0sh/archclt; installation and compatibility instructions
are in that release's `docs/install.md` and `docs/briefcase-integration.md`.

Verification executes in the application's environment. Use reviewed argument
vectors that select its runner, such as `[.venv/bin/python, -m, pytest]`.
The evaluator uses its own isolated interpreter and preserves the caller's PATH.

Install this complete skill directory in the agent's skills directory. Its
references need no source checkout. After installing tools, continue with
[adoption](adoption.md). Keep reviewed historical installs when upgrading.
