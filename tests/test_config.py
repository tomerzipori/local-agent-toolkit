from __future__ import annotations

import contextlib
import io
import json
import stat
import sys
from unittest import mock

from tests.helpers import FakePipe, FakeTTY, LocalAgentTestCase, local_agent, temporary_home


class ConfigTests(LocalAgentTestCase):
    def test_parser_covers_every_mode_and_version(self):
        for mode in local_agent.COMMANDS:
            args = local_agent.build_parser().parse_args([mode, "task"])
            self.assertEqual(args.mode, mode)
            prompt, truncated = local_agent.build_prompt(mode, "task", "context", 1000)
            self.assertIn("context", prompt)
            self.assertFalse(truncated)
        review_staged, _ = local_agent.build_prompt("review-staged", "task", "", 1000)
        review_branch, _ = local_agent.build_prompt("review-branch", "task", "", 1000)
        self.assertIn("Review the supplied", review_staged)
        self.assertIn("Review the supplied", review_branch)
        self.assertEqual(local_agent.build_parser().parse_args(["models"]).mode, "models")
        self.assertEqual(local_agent.build_parser().parse_args(["configure"]).mode, "configure")

    def test_diagnose_and_impact_have_distinct_prompts_and_help(self):
        parser = local_agent.build_parser()
        self.assertEqual(
            parser.parse_args(["diagnose", "failure", "error.log", "--stdin"]).mode, "diagnose"
        )
        self.assertEqual(parser.parse_args(["impact", "change retry behavior"]).mode, "impact")
        diagnose_prompt, _ = local_agent.build_prompt("diagnose", "failure", "output", 1000)
        impact_prompt, _ = local_agent.build_prompt("impact", "change", "diff", 1000)
        self.assertIn("Evidence versus hypotheses", diagnose_prompt)
        self.assertIn("Suggested verification", diagnose_prompt)
        self.assertIn("Affected files and symbols", impact_prompt)
        self.assertIn("Compatibility risks", impact_prompt)
        help_output = parser.format_help()
        self.assertIn("diagnose", help_output)
        self.assertIn("impact", help_output)

    def test_configuration_precedence_cli_then_environment_then_saved(self):
        with temporary_home():
            local_agent.save_config(
                {"model": "saved", "host": "http://saved", "num_ctx": 10, "max_chars": 20}
            )
            args = type(
                "Args", (), {"model": None, "host": None, "num_ctx": None, "max_chars": None}
            )()
            with mock.patch.dict(
                "os.environ",
                {
                    "LOCAL_AGENT_MODEL": "environment",
                    "LOCAL_AGENT_HOST": "http://environment",
                    "LOCAL_AGENT_NUM_CTX": "30",
                    "LOCAL_AGENT_MAX_CHARS": "40",
                },
                clear=False,
            ):
                settings = local_agent.resolve_settings(args, self._validated_config())
                self.assertEqual(settings.model, "environment")
                self.assertEqual(settings.host, "http://environment")
                self.assertEqual(settings.num_ctx, 30)
                self.assertEqual(settings.max_chars, 40)
            args = type(
                "Args", (), {"model": "cli", "host": "http://cli", "num_ctx": 50, "max_chars": 60}
            )()
            settings = local_agent.resolve_settings(args, self._validated_config())
            self.assertEqual(settings, local_agent.Settings("cli", "http://cli", 50, 60))

    def test_missing_and_malformed_configuration_are_actionable(self):
        with temporary_home() as home:
            args = type(
                "Args", (), {"model": None, "host": None, "num_ctx": None, "max_chars": None}
            )()
            message = self._error(local_agent.resolve_settings, args, {})
            self.assertIn("No model is configured", message)
            path = home / ".config/local-agent/config.json"
            path.parent.mkdir(parents=True)
            path.write_text("not json", encoding="utf-8")
            message = self._error(local_agent.load_config)
            self.assertIn("malformed", message)

    def test_every_delegation_mode_accepts_explicit_model_precedence(self):
        with temporary_home():
            local_agent.save_config({"model": "saved"})
            with mock.patch.dict("os.environ", {"LOCAL_AGENT_MODEL": "environment"}, clear=False):
                for mode in local_agent.COMMANDS:
                    args = local_agent.build_parser().parse_args([mode, "task", "--model", "cli"])
                    self.assertEqual(
                        local_agent.resolve_settings(args, self._validated_config()).model, "cli"
                    )

    def test_configure_model_flag_is_noninteractive(self):
        with temporary_home():
            local_agent.save_config(
                {
                    "model": "saved:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 4096,
                    "max_chars": 9000,
                }
            )
            with (
                mock.patch.object(
                    local_agent,
                    "discover_models",
                    return_value=["saved:latest", "qwen-coder:latest"],
                ),
                mock.patch(
                    "builtins.input", side_effect=AssertionError("configure prompted unexpectedly")
                ),
            ):
                status = local_agent.main(["configure", "--model", "qwen-coder:latest"])
            self.assertEqual(status, 0)
            self.assertEqual(
                local_agent.load_config(),
                {
                    "schema_version": 1,
                    "model": "qwen-coder:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 4096,
                    "max_chars": 9000,
                },
            )

    def test_configure_saves_host_num_ctx_and_max_chars(self):
        with temporary_home():
            with mock.patch.object(
                local_agent, "discover_models", return_value=["qwen-coder:latest"]
            ):
                status = local_agent.main(
                    [
                        "configure",
                        "--host",
                        "http://127.0.0.1:11434",
                        "--model",
                        "qwen-coder:latest",
                        "--num-ctx",
                        "32768",
                        "--max-chars",
                        "120000",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(
                local_agent.load_config(),
                {
                    "schema_version": 1,
                    "model": "qwen-coder:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 32768,
                    "max_chars": 120000,
                },
            )

    def test_configure_preserves_unspecified_values(self):
        with temporary_home():
            local_agent.save_config(
                {
                    "model": "saved:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 8192,
                    "max_chars": 110000,
                    "extra_field": "preserve-me",
                }
            )
            with mock.patch.object(
                local_agent, "discover_models", return_value=["saved:latest", "qwen-coder:latest"]
            ):
                status = local_agent.main(["configure", "--model", "qwen-coder:latest"])
            self.assertEqual(status, 0)
            self.assertEqual(
                local_agent.load_config(),
                {
                    "schema_version": 1,
                    "model": "qwen-coder:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 8192,
                    "max_chars": 110000,
                    "extra_field": "preserve-me",
                },
            )

    def test_configure_interactive_preserves_non_model_settings(self):
        with temporary_home():
            local_agent.save_config(
                {
                    "model": "saved:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 2048,
                    "max_chars": 7000,
                }
            )
            stdin = FakeTTY()
            stdout = FakeTTY()
            with (
                mock.patch.object(
                    local_agent,
                    "discover_models",
                    return_value=["saved:latest", "qwen-coder:latest"],
                ),
                mock.patch.object(local_agent, "select_model", return_value="qwen-coder:latest"),
                mock.patch.object(sys, "stdin", stdin),
                mock.patch.object(sys, "stdout", stdout),
            ):
                status = local_agent.main(["configure"])
            self.assertEqual(status, 0)
            self.assertEqual(
                local_agent.load_config(),
                {
                    "schema_version": 1,
                    "model": "qwen-coder:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 2048,
                    "max_chars": 7000,
                },
            )

    def test_configure_rejects_missing_model_at_effective_host(self):
        with temporary_home(), contextlib.redirect_stderr(io.StringIO()) as stderr:
            local_agent.save_config(
                {
                    "model": "saved:latest",
                    "host": "http://127.0.0.1:11434",
                    "num_ctx": 4096,
                    "max_chars": 9000,
                }
            )
            with mock.patch.object(
                local_agent, "discover_models", return_value=["different:latest"]
            ):
                status = local_agent.main(
                    ["configure", "--host", "http://127.0.0.1:11434", "--model", "missing:latest"]
                )
            self.assertEqual(status, 1)
            self.assertIn("is not installed", stderr.getvalue())
            self.assertEqual(local_agent.load_config()["model"], "saved:latest")

    def test_configure_noninteractive_without_flags_fails(self):
        stdin = FakePipe()
        stdout = FakePipe()
        with (
            temporary_home(),
            mock.patch.object(sys, "stdin", stdin),
            mock.patch.object(sys, "stdout", stdout),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = local_agent.main(["configure"])
        self.assertEqual(status, 2)
        self.assertIn(
            "configure requires explicit options in a noninteractive environment", stderr.getvalue()
        )

    def test_legacy_config_is_migrated(self):
        with temporary_home() as home:
            path = home / ".config/local-agent/config.json"
            path.parent.mkdir(parents=True)
            payload = {
                "model": "saved:latest",
                "host": "http://127.0.0.1:11434",
                "num_ctx": 4096,
                "max_chars": 9000,
            }
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with mock.patch.object(
                local_agent, "discover_models", return_value=["saved:latest", "qwen-coder:latest"]
            ):
                status = local_agent.main(["configure", "--model", "qwen-coder:latest"])
            self.assertEqual(status, 0)
            self.assertEqual(local_agent.load_config()["schema_version"], 1)

    def test_future_config_schema_is_rejected(self):
        with temporary_home() as home, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = home / ".config/local-agent/config.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"schema_version": 99, "model": "saved:latest"}\n', encoding="utf-8")
            status = local_agent.main(["configure", "--show"])
        self.assertEqual(status, 1)
        self.assertIn("supports up to 1", stderr.getvalue())

    def test_config_save_is_atomic(self):
        with temporary_home():
            local_agent.save_config({"model": "saved:latest"})
            path = local_agent.config_path()
            with self.assertRaises(OSError):
                with mock.patch.object(local_agent.os, "replace", side_effect=OSError("boom")):
                    local_agent.save_config({"model": "next:latest"})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"schema_version": 1, "model": "saved:latest"},
            )
            leftovers = [
                item.name
                for item in path.parent.iterdir()
                if item.name.startswith(f".{path.name}.")
            ]
            self.assertEqual(leftovers, [])

    def test_config_permissions_are_0600(self):
        with temporary_home():
            local_agent.save_config({"model": "saved:latest"})
            mode = stat.S_IMODE(local_agent.config_path().stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_configure_show_reports_setting_sources(self):
        with (
            temporary_home(),
            mock.patch.dict(
                "os.environ", {"LOCAL_AGENT_HOST": "http://env-host:11434"}, clear=False
            ),
        ):
            local_agent.save_config({"model": "saved:latest", "num_ctx": 2048})
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = local_agent.main(["configure", "--show", "--model", "cli:latest"])
            self.assertEqual(status, 0)
            rendered = stdout.getvalue()
            self.assertIn("model: cli:latest [cli]", rendered)
            self.assertIn("host: http://env-host:11434 [environment]", rendered)
            self.assertIn("num_ctx: 2048 [saved config]", rendered)
            self.assertIn("max_chars: 120000 [default]", rendered)

    def test_select_model_accepts_number(self):
        with mock.patch("builtins.input", side_effect=["2"]):
            self.assertEqual(local_agent.select_model(["one", "two"]), "two")
