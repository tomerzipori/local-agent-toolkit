# Commands

Use the shared form:

```bash
local-agent <command> "<task>" <explicit-files> --model <selected-model>
```

`--show-context-files` inspects the intended context and exits without contacting Ollama.

| Command | Purpose | Required context | Local side effects | Expected response | Example |
| --- | --- | --- | --- | --- | --- |
| `find` | Bounded repository discovery. It inspects repository inventory and search results. | A narrow question. Files are optional. | Reads repository metadata and search results only. | Likely files, symbols, or flows to inspect next. | `local-agent find "Where is retry backoff implemented?" --model <selected-model>` |
| `files` | Explicit-file summaries only. | A focus prompt plus explicit files. | Reads only the supplied files. | A bounded summary grounded in the given files. | `local-agent files "Explain responsibilities and risks" src/client.py src/retry.py --model <selected-model>` |
| `plan` | Implementation plan only; no implementation authority. | A bounded task plus explicit files. | Reads supplied files only. | An ordered plan and likely checks. | `local-agent plan "Add validation for empty package names" src/config.py tests/test_config.py --model <selected-model>` |
| `review` | Focused review of current changes. It gathers staged and unstaged Git diffs. | A review focus. Files are optional. | Runs read-only Git diff commands. | Findings, risks, and likely missing tests. | `local-agent review "Look for correctness regressions" --model <selected-model>` |
| `review-staged` | Review the staged diff only. | A review focus. | Runs read-only Git diff commands against the staged diff. | Findings on the staged change set. | `local-agent review-staged "Pre-commit correctness review" --model <selected-model>` |
| `review-branch` | Review the branch diff versus a base branch. | A review focus. Optional `--base`. | Runs read-only Git diff commands for the branch comparison. | Findings on the branch diff. | `local-agent review-branch "Review before opening a PR" --base origin/main --model <selected-model>` |
| `test-plan` | Focused test ideas for explicit code or change context. | A bounded test objective plus explicit files. | Reads supplied files only. | Targeted test cases and gaps. | `local-agent test-plan "Tests for deterministic package sampling" src/sampling.py tests/test_sampling.py --model <selected-model>` |
| `write-tests` | Proposed test diff only. The parent agent must review and run it. | A test task, implementation file, and test file. | Reads supplied files only. | A candidate test patch or precise test edits. | `local-agent write-tests "Add regression tests for duplicate IDs" src/sampling.py tests/test_sampling.py --model <selected-model>` |
| `diagnose` | Diagnose supplied failure output. It does not execute commands. | Failure text plus optional files or `--stdin`. | No command execution. | Root-cause hypotheses and next checks. | `local-agent diagnose "Explain this CI failure" --stdin tests/test_sampling.py --model <selected-model>` |
| `fix-test` | Requires `--command`; it explicitly executes that command before delegation. | A bounded task, reviewed local command, and explicit files. | Executes the supplied local shell command first. | Diagnosis plus a minimal fix proposal tied to the observed command output. | `local-agent fix-test "Diagnose and propose a minimal fix" --command 'pytest tests/test_sampling.py -x' src/sampling.py --model <selected-model>` |
| `impact` | Bounded blast-radius analysis. | A scoped change description plus optional explicit files. | Reads repository inventory, targeted search results, and diffs. | Files, paths, or tests likely affected by the change. | `local-agent impact "Assess the blast radius of changing retry behavior" src/retry.py tests/test_retry.py --model <selected-model>` |
| `second-opinion` | Attempt to falsify a supplied proposal. | A specific claim or proposal plus optional files or `--stdin`. | Reads only the supplied context. | Risks, counterexamples, or missing assumptions. | `git diff | local-agent second-opinion --stdin "Challenge the design choices in this diff" --model <selected-model>` |
| `patch` | Minimal unified diff proposal only. | A bounded task plus explicit files. | Reads supplied files only. | A small candidate patch to review independently. | `local-agent patch "Add validation for empty insight names" src/config.py tests/test_config.py --model <selected-model>` |
