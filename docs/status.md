# Support status

The first public release is 0.2.0. Its command is `archctl`; packages are
`archclt` (Python) and `@archclt/archctl` (npm). Exchange contracts are v2.

Supported: Python 3.11+, Git, Linux and macOS, static Python import mapping,
local gates, explicit required/advisory obligations, task contracts and reviewed
command execution. Windows packaging is experimental pending platform validation.

Briefcase is an external native evidence producer. A passing package test does
not establish native interoperability; release validation reports skips explicitly.
Runtime coverage, dynamic imports and non-Python mapping remain unsupported.
Hosted approval, graph UI, tracing collection and new policy kinds are deferred.

Generated tests, evaluations and gate runs are kept in ignored local directories
or release/CI artifacts. Historical dogfood campaigns are retained privately;
the public repository starts from a clean source snapshot.
