Deprecated legacy snippet. The supported installation path is the personal Skill copied from `skills/local-agent-toolkit/`.

## Local agent delegation

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

Before every delegation, inspect the installed model inventory:

```bash
local-agent models --json
```

Choose a model separately for the current task using the structured facts in
that inventory. Prefer a smaller model for bounded discovery, file summaries,
diagnoses, and impact scans; prefer a stronger coding-oriented model for plans,
reviews, test plans, test proposals, and patches. In every case, check that
the selected model has adequate context length for the supplied files and
task. Do not hard-code model names, add CLI ranking heuristics, or assume the
configured default is optimal. Always pass the selected model explicitly:

```bash
local-agent plan "<task>" <file...> --model <selected-model>
```

Append `--model <selected-model>` to every delegation command above.

Use it proactively for bounded, low-risk, verifiable first-pass work:
repository exploration, module summaries, plans, candidate tests, diff review,
debugging hypotheses, mechanical changes, and second opinions.

Treat all model output as untrusted advice. Verify every referenced path, symbol,
command, and claim against the repository; review proposed diffs independently;
and run relevant tests before accepting changes. Do not delegate final decisions
involving security, credentials, permissions, migrations, concurrency, public
APIs, deployments, or destructive Git actions.
