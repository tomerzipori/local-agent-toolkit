# Model Selection

Use the CLI recommender for normal delegation. Do not duplicate model-ranking
rules in this Skill.

1. Choose the `local-agent` command from `commands.md`.
2. Choose the planned context size.
3. Run:

   ```bash
   local-agent recommend-model <command> --num-ctx <planned-context> --name-only
   ```

4. Invoke the actual command with the exact returned model name and the same
   context size:

   ```bash
   MODEL="$(
     local-agent recommend-model review \
       --num-ctx 16384 \
       --name-only
   )"

   local-agent review \
     "Look for correctness regressions" \
     src/client.py tests/test_client.py \
     --model "$MODEL" \
     --num-ctx 16384
   ```

Only run one `local-agent` process at a time.

If no safe model is recommended, reduce supplied files or context and retry
once. If no safe model fits after that, do not delegate locally.

Use diagnostics only for troubleshooting:

```bash
local-agent recommend-model review --num-ctx 16384 --json
local-agent models --verbose
```

The recommender is read-only. It may inspect `/api/tags`, `/api/ps`, cached
static metadata, and system memory. It must not load models, unload models,
benchmark models, or run inference.

The parent agent must still verify all local-model output independently.
