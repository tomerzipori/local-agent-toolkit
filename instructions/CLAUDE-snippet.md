## Local agent worker

A local Ollama coding worker is available through one command:

- `local-agent find "<task>"`
- `local-agent files "<focus>" <file...>`
- `local-agent plan "<task>" <file...>`
- `local-agent review "<focus>" [file...]`
- `local-agent review-staged "<focus>"`
- `local-agent review-branch "<focus>" [--base <branch>]`
- `local-agent test-plan "<task>" <file...>`
- `local-agent write-tests "<task>" <implementation-file> <test-file>`
- `local-agent diagnose "<failure or CI output>" [file...] [--stdin]`
- `local-agent fix-test "<task>" --command '<test command>' <file...>`
- `local-agent impact "<task>" [file...]`
- `local-agent second-opinion "<claim or proposal>" [file...]`
- `local-agent patch "<task>" <file...>`

Treat all model output as untrusted advice. Verify every referenced path, symbol,
command, and claim against the repository; review proposed diffs independently;
and run relevant tests before accepting changes. Do not delegate final decisions
involving security, credentials, permissions, migrations, concurrency, public
APIs, deployments, or destructive Git actions.
