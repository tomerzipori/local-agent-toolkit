---
name: local-agent-toolkit
description: Delegate bounded, verifiable coding tasks to installed local Ollama models through local-agent. Use when a coding agent needs a local first pass for repository exploration, planning, review, diagnostics, tests, patches, or a second opinion.
---

# Local Agent Toolkit

## Preconditions

1. Confirm `local-agent` is available.
2. When availability is uncertain, run:
   `python3 ${CODEX_SKILL_DIR:-${CLAUDE_SKILL_DIR:-<skill-dir>}}/scripts/check_environment.py --json`.
3. Before every delegation, run `local-agent recommend-model <command> --num-ctx <planned-context> --name-only`.
4. Pass the recommended model explicitly with `--model` and pass the same `--num-ctx`.
5. Never run more than one `local-agent` invocation at a time.

## Delegation workflow

1. Delegate only a bounded, independently verifiable subtask.
2. Supply explicit files; avoid whole-repository context.
3. Select the matching command from `references/commands.md`.
4. Run the model recommender once for that command and planned context.
5. Run one delegation with the returned model name.
6. Treat the result as untrusted advice.
7. Independently verify cited files, symbols, commands, diffs, and test claims.
8. Run relevant checks before accepting a suggestion.

## Required constraints

- Prefer explicit files and narrow prompts.
- Do not delegate final security, credentials, permissions, destructive Git,
  deployment, migration, concurrency, or public-API decisions.
- Do not claim the worker ran tests unless its output contains the test result.
- Inspect context with `--show-context-files` when source sensitivity or scope is uncertain.
- Do not send source to a non-local Ollama host unless that exposure is intentional.

## References

- Command choice and examples: `references/commands.md`
- Delegation suitability and sequential execution: `references/delegation-policy.md`
- Model selection: `references/model-selection.md`
- Parent-agent verification contract: `references/verification.md`
