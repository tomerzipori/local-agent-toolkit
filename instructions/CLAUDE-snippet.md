## Local Qwen worker

A local Qwen coding worker is available through these shell commands:

- `qwen-find "<task>"`
- `qwen-files "<focus>" <file...>`
- `qwen-plan "<task>" <file...>`
- `qwen-review "<focus>" [file...]`
- `qwen-review-staged "<focus>"`
- `qwen-review-branch "<focus>" --base main`
- `qwen-test-plan "<task>" <file...>`
- `qwen-write-tests "<task>" <implementation-file> <test-file>`
- `qwen-fix-test "<task>" --command '<test command>' <file...>`
- `qwen-sql-review "<focus>" <file...>`
- `qwen-second-opinion "<claim or proposal>" [file...]`
- `qwen-patch "<task>" <file...>`

Use it proactively for bounded, low-risk, verifiable first-pass work:
repository exploration, module summaries, plans, candidate tests, diff review,
SQL review, debugging hypotheses, mechanical changes, and second opinions.

Delegation rules:

1. Give Qwen a narrow task and only the necessary context.
2. Treat all output as untrusted advice.
3. Verify every referenced path, symbol, and claim against the repository.
4. Review proposed diffs independently.
5. Run relevant tests and static checks before accepting changes.
6. Do not delegate final decisions involving security, credentials, permissions,
   migrations, concurrency, public APIs, deployments, or destructive Git actions.
7. Prefer the parent agent's own judgment when Qwen conflicts with repository evidence.
