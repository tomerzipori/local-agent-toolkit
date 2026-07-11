# Contributing

Thanks for considering a contribution. Local Agent Toolkit is intended to become a practical, community-built toolbox for delegating bounded coding work to local models.

Small fixes, documentation improvements, model compatibility notes, and focused new commands are all welcome.

## Good contribution areas

Useful contributions include:

- new bounded commands with clear input and output contracts;
- safer context collection and secret handling;
- model recommendation, memory estimation, and diagnostic improvements;
- improved prompt templates and verification guidance;
- Codex, Claude Code, or other coding-agent integrations;
- Linux, Bash, Fish, or Windows support;
- model compatibility notes and reproducible benchmarks;
- installer usability and failure-message improvements;
- tests, documentation, and examples.

For a larger behavioral change, opening an issue first is helpful so the scope and safety model can be discussed before implementation. Small, self-contained pull requests can be opened directly.

## Design principles

Contributions should preserve the core contract:

1. **Delegate bounded work.** A local worker should receive a narrow task and only the context it needs.
2. **Keep the parent agent responsible.** Local-model output is untrusted advice, not final authority.
3. **Prefer safe defaults.** Sensitive, ignored, untracked, external, binary, symlinked, and oversized files should not be included silently.
4. **Make side effects explicit.** Commands that execute code or write files must say so clearly.
5. **Separate evidence from claims.** The model must not claim to have run tests or commands unless their output is supplied.
6. **Keep recommendations explainable.** Model selection should expose assumptions, rejection reasons, and safety filters rather than hiding them behind an opaque score.
7. **Avoid unnecessary dependencies.** The CLI is currently implemented with the Python standard library only.
8. **Keep changes focused.** Avoid unrelated refactors or formatting churn in the same pull request.

## Development setup

Clone the repository and run the CLI directly from the working tree:

```bash
git clone https://github.com/tomerzipori/local-agent-toolkit.git
cd local-agent-toolkit
python3 bin/local-agent --help
```

The supported Python range is 3.10–3.13.

Ollama is required only for end-to-end model calls and recommendation checks against a live model inventory. Most unit tests do not require a running model server.

## Development checks

Run the full local gate before pushing:

```bash
bash scripts/check.sh
```

Run only the unit suite:

```bash
python3 -m unittest discover -s tests -v
```

The full gate requires Ruff and ShellCheck. It validates the skill, compiles Python sources including the recommendation benchmark helper, runs the unit suite, checks formatting and linting, and validates the installer with Bash syntax checks and ShellCheck.

## Adding or changing a command

A command change normally requires updates in several places:

- the prompt and command registration in `bin/local-agent`;
- argument parsing and context collection behavior;
- recommendation profile mapping when the command should be classified as fast, balanced, or strong;
- unit tests under `tests/`;
- the personal skill references under `skills/local-agent-toolkit/references/`;
- the README when the user-visible capability changes.

A good command should have:

- a narrow purpose;
- explicit context expectations;
- predictable local side effects;
- a structured response contract;
- an appropriate recommendation profile;
- tests for success, invalid input, context limits, and safety boundaries.

## Changing model recommendation behavior

Recommendation changes need extra care because they affect which model receives source context and whether the task is likely to fit available memory.

Please document and test:

- the command profile or ranking behavior being changed;
- context-capacity filters;
- memory-estimation assumptions;
- behavior for unknown metadata;
- deterministic tie-breaking;
- preferred and excluded model handling;
- diagnostics and reason codes;
- the guarantee that recommendation does not load, unload, benchmark, or run inference with a model.

Treat parameter count, quantization, artifact size, and estimated memory as imperfect signals. Preferences must never bypass context or memory safety filters.

## Pull requests

Please:

- keep the pull request narrowly scoped;
- explain the user problem and resulting behavior;
- include or update tests for behavior changes;
- update documentation when commands, flags, schemas, defaults, recommendation rules, or support boundaries change;
- mention any command execution, file-writing, privacy, memory, or compatibility implications;
- run `bash scripts/check.sh` and report the result;
- prefer squash merges.

A concise pull request is easier to review and safer to validate with both local and frontier models.

## Reporting model behavior

Model reports are useful when they include enough information to reproduce the result:

- exact Ollama model name and digest when available;
- quantization and parameter metadata when known;
- requested and supported context length;
- hardware, available memory, and operating system;
- command, recommendation output, and prompt used;
- whether the model was already running;
- whether the behavior was consistent across repeated runs;
- sanitized input and output when they can be shared safely.

For recommendation problems, include `local-agent recommend-model <command> --num-ctx <size> --json` and `local-agent models --verbose` output after removing anything sensitive.

Do not include proprietary source code, credentials, secrets, or other sensitive repository content in an issue or pull request.

## Questions and ideas

Use GitHub issues for feature ideas, unclear behavior, support requests, and proposed changes that need design discussion.
