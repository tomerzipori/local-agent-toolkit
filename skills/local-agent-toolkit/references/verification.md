# Verification

The parent agent must:

- Confirm every referenced path and symbol.
- Validate every suggested command before running it.
- Inspect proposed unified diffs independently.
- Reject unrelated changes.
- Run relevant formatting, linting, and tests.
- Treat execution claims as untrusted without included output.
- Escalate uncertainty instead of accepting speculation.

Checklist:

```text
[ ] Files and symbols verified
[ ] Command safety and scope verified
[ ] Diff reviewed
[ ] Unrelated changes rejected
[ ] Relevant checks run
[ ] Remaining uncertainty surfaced
```
