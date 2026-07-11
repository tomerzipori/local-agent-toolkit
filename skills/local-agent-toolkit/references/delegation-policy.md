# Delegation Policy

Appropriate delegation targets:

- Finding files, symbols, and likely implementation flows.
- Summarizing a small explicit file set.
- First-pass plans, test ideas, focused diff review, and supplied-error diagnosis.
- Design challenge and minimal patch drafts.

Do not delegate:

- Open-ended repository work.
- Final decisions about security, credentials, permissions, destructive Git, deployments, migrations, concurrency, or public APIs.
- Work requiring undocumented broad product context.

Decision gate:

```text
Is the task bounded?
Can the relevant context be supplied explicitly?
Can the output be independently verified?
Does delegation save meaningful parent-agent effort?

If any critical answer is no, do not delegate.
```

Run one `local-agent` invocation at a time. Do not parallelize workers.
