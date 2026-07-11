from __future__ import annotations

import contextlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("local_agent", str(ROOT / "bin/local-agent"))
SPEC = importlib.util.spec_from_loader("local_agent", LOADER)
assert SPEC and SPEC.loader
local_agent = importlib.util.module_from_spec(SPEC)
sys.modules["local_agent"] = local_agent
SPEC.loader.exec_module(local_agent)


@contextlib.contextmanager
def temporary_home():
    with tempfile.TemporaryDirectory() as home:
        with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
            yield Path(home)


@contextlib.contextmanager
def temporary_cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class OllamaServer:
    def __init__(self, response: dict[str, object], status: int = 200):
        self.response = response
        self.status = status
        self.requests: list[dict[str, object]] = []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self._reply()

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                owner.requests.append(json.loads(self.rfile.read(length)))
                self._reply()

            def _reply(self):
                payload = json.dumps(owner.response).encode()
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                return

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def host(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class LocalAgentTests(unittest.TestCase):
    def test_parser_covers_every_mode_and_version(self):
        for mode in local_agent.COMMANDS:
            args = local_agent.build_parser().parse_args([mode, "task"])
            self.assertEqual(args.mode, mode)
            prompt, truncated = local_agent.build_prompt(mode, "task", "context", 1000)
            self.assertIn("context", prompt)
            self.assertFalse(truncated)
        self.assertIn("Review the supplied", local_agent.build_prompt("review-staged", "task", "", 1000)[0])
        self.assertIn("Review the supplied", local_agent.build_prompt("review-branch", "task", "", 1000)[0])
        self.assertEqual(local_agent.build_parser().parse_args(["models"]).mode, "models")
        self.assertEqual(local_agent.build_parser().parse_args(["configure"]).mode, "configure")

    def test_diagnose_and_impact_have_distinct_prompts_and_help(self):
        parser = local_agent.build_parser()
        self.assertEqual(parser.parse_args(["diagnose", "failure", "error.log", "--stdin"]).mode, "diagnose")
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
            local_agent.save_config({"model": "saved", "host": "http://saved", "num_ctx": 10, "max_chars": 20})
            args = SimpleNamespace(model=None, host=None, num_ctx=None, max_chars=None)
            with mock.patch.dict(os.environ, {
                "LOCAL_AGENT_MODEL": "environment",
                "LOCAL_AGENT_HOST": "http://environment",
                "LOCAL_AGENT_NUM_CTX": "30",
                "LOCAL_AGENT_MAX_CHARS": "40",
            }, clear=False):
                settings = local_agent.resolve_settings(args)
                self.assertEqual(settings.model, "environment")
                self.assertEqual(settings.host, "http://environment")
                self.assertEqual(settings.num_ctx, 30)
                self.assertEqual(settings.max_chars, 40)
            args = SimpleNamespace(model="cli", host="http://cli", num_ctx=50, max_chars=60)
            settings = local_agent.resolve_settings(args)
            self.assertEqual(settings, local_agent.Settings("cli", "http://cli", 50, 60))

    def test_missing_and_malformed_configuration_are_actionable(self):
        with temporary_home() as home:
            self.assertIn("No model is configured", self._error(local_agent.resolve_settings, SimpleNamespace(model=None, host=None, num_ctx=None, max_chars=None)))
            path = home / ".config/local-agent/config.json"
            path.parent.mkdir(parents=True)
            path.write_text("not json")
            message = self._error(local_agent.load_config)
            self.assertIn("malformed", message)

    def test_model_discovery_and_generate_payload(self):
        with OllamaServer({"models": [{"name": "model:latest"}]}) as server:
            self.assertEqual(local_agent.discover_models(server.host), ["model:latest"])
            # The same response is sufficient to verify request shape; a generate response is installed below.
            with mock.patch.object(local_agent, "request_json", side_effect=[
                {"models": [{"name": "model:latest"}]}, {"response": " answer "}
            ]) as request:
                result = local_agent.call_ollama("prompt", local_agent.Settings("model:latest", server.host, 123, 456))
            self.assertEqual(result, "answer")
            payload = request.call_args_list[1].args[2]
            self.assertEqual(payload["model"], "model:latest")
            self.assertEqual(payload["options"]["num_ctx"], 123)
            self.assertFalse(payload["stream"])

    def test_enriched_model_inventory_uses_tags_and_show_and_fills_optional_metadata(self):
        with mock.patch.object(local_agent, "request_json", side_effect=[
            {
                "models": [
                    {"name": "coder:latest", "size": 123, "details": {"family": "tags-family"}},
                    {"name": "small:latest"},
                ]
            },
            {
                "details": {
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "7B",
                    "quantization_level": "Q4_K_M",
                },
                "capabilities": ["completion"],
                "model_info": {"llama.context_length": 8192},
            },
            {"details": {}, "model_info": {}},
        ]) as request:
            inventory = local_agent.model_inventory("http://host")

        self.assertEqual(inventory, [
            {
                "name": "coder:latest",
                "size_bytes": 123,
                "family": "llama",
                "families": ["llama"],
                "parameter_size": "7B",
                "quantization": "Q4_K_M",
                "capabilities": ["completion"],
                "context_length": 8192,
            },
            {
                "name": "small:latest",
                "size_bytes": None,
                "family": None,
                "families": [],
                "parameter_size": None,
                "quantization": None,
                "capabilities": [],
                "context_length": None,
            },
        ])
        self.assertEqual(request.call_args_list[1].args[1:], ("/api/show", {"model": "coder:latest"}))
        self.assertEqual(request.call_args_list[2].args[1:], ("/api/show", {"model": "small:latest"}))

    def test_model_inventory_propagates_show_api_failures(self):
        with mock.patch.object(local_agent, "request_json", side_effect=[
            {"models": [{"name": "model:latest"}]},
            RuntimeError("Ollama returned HTTP 404 at http://host/api/show: missing"),
        ]):
            message = self._error(local_agent.model_inventory, "http://host")
        self.assertIn("HTTP 404", message)

    def test_models_json_reports_default_and_plain_output_is_unchanged(self):
        with temporary_home():
            local_agent.save_config({"model": "coder:latest"})
            with mock.patch.object(local_agent, "request_json", side_effect=[
                {"models": [{"name": "coder:latest", "size": 10}]},
                {"details": {}, "capabilities": [], "model_info": {}},
            ]), contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = local_agent.main(["models", "--json", "--host", "http://host"])
            self.assertEqual(status, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["host"], "http://host")
            self.assertEqual(payload["default_model"], "coder:latest")
            self.assertEqual(payload["models"][0]["name"], "coder:latest")

            with mock.patch.object(local_agent, "request_json", return_value={"models": [{"name": "coder:latest"}]}), contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = local_agent.main(["models", "--host", "http://host"])
            self.assertEqual(status, 0)
            self.assertEqual(stdout.getvalue(), "coder:latest\n")

    def test_empty_models_missing_ollama_and_api_error(self):
        with OllamaServer({"models": []}) as server:
            message = self._error(local_agent.discover_models, server.host)
            self.assertIn("No Ollama models are installed", message)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            unused_port = sock.getsockname()[1]
        message = self._error(local_agent.discover_models, f"http://127.0.0.1:{unused_port}")
        self.assertIn("Could not reach Ollama", message)
        with OllamaServer({"error": "bad request"}, status=500) as server:
            message = self._error(local_agent.discover_models, server.host)
            self.assertIn("HTTP 500", message)

    def test_stale_model_is_rejected(self):
        with mock.patch.object(local_agent, "discover_models", return_value=["new"]):
            message = self._error(local_agent.call_ollama, "prompt", local_agent.Settings("old", "host", 1, 1))
        self.assertIn("is not installed", message)

    def test_every_delegation_mode_accepts_explicit_model_precedence(self):
        with temporary_home():
            local_agent.save_config({"model": "saved"})
            with mock.patch.dict(os.environ, {"LOCAL_AGENT_MODEL": "environment"}, clear=False):
                for mode in local_agent.COMMANDS:
                    args = local_agent.build_parser().parse_args([mode, "task", "--model", "cli"])
                    self.assertEqual(local_agent.resolve_settings(args).model, "cli", mode)

    def test_select_model_accepts_number(self):
        with mock.patch("builtins.input", side_effect=["2"]):
            self.assertEqual(local_agent.select_model(["one", "two"]), "two")

    def test_binary_skipping_boundary_protection_and_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            outside = Path(directory) / "outside.txt"
            repo.mkdir()
            (repo / "source.py").write_text("print('ok')")
            (repo / "binary.dat").write_bytes(b"header\0binary")
            outside.write_text("private")
            subprocess.run(["git", "init", "--initial-branch=main"], cwd=repo, check=True, stdout=subprocess.PIPE)
            args = SimpleNamespace(mode="files", task="", files=[str(repo / "source.py"), str(repo / "binary.dat"), str(outside)], stdin=False, allow_outside_repo=False)
            with mock.patch.object(local_agent, "run_git", side_effect=lambda command: str(repo) + "\n" if command[:2] == ["rev-parse", "--show-toplevel"] else ""):
                message = self._error(local_agent.collect_context, args)
            self.assertIn("outside the current repository", message)
            args.allow_outside_repo = True
            with mock.patch.object(local_agent, "run_git", side_effect=lambda command: str(repo) + "\n" if command[:2] == ["rev-parse", "--show-toplevel"] else ""):
                context, _ = local_agent.collect_context(args)
            self.assertIn("print('ok')", context)
            self.assertIn("SKIPPED BINARY", context)
            self.assertIn("private", context)
            truncated, was_truncated = local_agent.truncate_context("x" * 100, 40)
            self.assertTrue(was_truncated)
            self.assertIn("TRUNCATED TO 40", truncated)

    def test_diagnose_reads_stdin_and_files_without_subprocesses(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.py"
            source.write_text("raise RuntimeError('broken')")
            args = SimpleNamespace(
                mode="diagnose",
                task="Explain the failure",
                files=[str(source)],
                stdin=True,
                allow_outside_repo=False,
            )
            with temporary_cwd(Path(directory)), mock.patch("sys.stdin", io.StringIO("CI: RuntimeError")), mock.patch.object(
                local_agent.subprocess, "run", side_effect=AssertionError("diagnose ran a subprocess")
            ):
                context, status = local_agent.collect_context(args)
            self.assertIsNone(status)
            self.assertIn("CI: RuntimeError", context)
            self.assertIn("raise RuntimeError('broken')", context)

    def test_impact_collects_repository_search_and_both_diffs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            tracked = repo / "retry.py"
            tracked.write_text("def retry_request():\n    return 'initial'\n")
            subprocess.run(["git", "init", "--initial-branch=main"], cwd=repo, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "add", "retry.py"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "initial"],
                cwd=repo,
                check=True,
                stdout=subprocess.PIPE,
            )
            args = SimpleNamespace(
                mode="impact",
                task="Assess retry_request behavior",
                files=[],
                stdin=False,
                allow_outside_repo=False,
            )
            with temporary_cwd(repo):
                clean_context, status = local_agent.collect_context(args)
            self.assertIsNone(status)
            self.assertNotIn("===== STAGED DIFF =====", clean_context)
            self.assertNotIn("===== UNSTAGED DIFF =====", clean_context)
            tracked.write_text("def retry_request():\n    return 'staged change'\n")
            subprocess.run(["git", "add", "retry.py"], cwd=repo, check=True)
            tracked.write_text("def retry_request():\n    return 'unstaged change'\n")
            with temporary_cwd(repo):
                context, status = local_agent.collect_context(args)
            self.assertIsNone(status)
            self.assertIn("===== REPOSITORY FILE LIST =====", context)
            self.assertIn("retry.py", context)
            self.assertIn("===== REPOSITORY SEARCH =====", context)
            self.assertIn("retry_request", context)
            self.assertIn("===== STAGED DIFF =====", context)
            self.assertIn("staged change", context)
            self.assertIn("===== UNSTAGED DIFF =====", context)
            self.assertIn("unstaged change", context)

    def test_impact_requires_a_git_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                mode="impact",
                task="Assess impact",
                files=[],
                stdin=False,
                allow_outside_repo=False,
            )
            with temporary_cwd(Path(directory)):
                message = self._error(local_agent.collect_context, args)
            self.assertIn("inside a Git repository", message)

    def test_default_branch_prefers_remote_default_then_local_fallback(self):
        with mock.patch.object(local_agent, "run_git", side_effect=["origin/develop\n"]):
            self.assertEqual(local_agent.default_base(), "origin/develop")
        with mock.patch.object(local_agent, "run_git", side_effect=[RuntimeError("none"), "sha\n"]):
            self.assertEqual(local_agent.default_base(), "main")
        with mock.patch.object(local_agent, "run_git", side_effect=[RuntimeError("none"), RuntimeError("none"), "sha\n"]):
            self.assertEqual(local_agent.default_base(), "master")

    def test_fix_test_executes_command_and_propagates_status(self):
        args = ["fix-test", "diagnose", "--command", "printf test-output; exit 3", "--model", "model"]
        captured = []
        with mock.patch.object(local_agent, "call_ollama", side_effect=lambda prompt, _settings: captured.append(prompt) or "advice"), mock.patch.dict(os.environ, {}, clear=False):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = local_agent.main(args)
        self.assertEqual(status, 3)
        self.assertIn("advice", stdout.getvalue())
        self.assertIn("test-output", captured[0])
        self.assertIn("EXIT CODE: 3", captured[0])
        self.assertIn("Executing local shell command", stderr.getvalue())

    def test_installer_is_repeatable_and_uninstall_is_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home}
            install = ROOT / "install.sh"
            first = subprocess.run(["bash", str(install)], env=env, text=True, capture_output=True, check=True)
            second = subprocess.run(["bash", str(install)], env=env, text=True, capture_output=True, check=True)
            target = Path(home) / ".local/bin/local-agent"
            self.assertTrue(target.is_file())
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            zshrc = (Path(home) / ".zshrc").read_text()
            self.assertEqual(zshrc.count('export PATH="$HOME/.local/bin:$PATH"'), 1)
            self.assertFalse((Path(home) / ".codex/AGENTS.md").exists())
            self.assertFalse((Path(home) / ".claude/CLAUDE.md").exists())
            subprocess.run(["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True)
            subprocess.run(["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True)
            self.assertFalse(target.exists())

    def test_installer_instruction_modes_repeat_and_uninstall(self):
        install = ROOT / "install.sh"
        for mode in ("codex", "claude", "both", "none"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as home:
                home_path = Path(home)
                env = {**os.environ, "HOME": home}
                (home_path / ".codex").mkdir()
                (home_path / ".claude").mkdir()
                (home_path / ".codex/AGENTS.md").write_text("Keep this Codex instruction.\n")
                (home_path / ".claude/CLAUDE.md").write_text("Keep this Claude instruction.\n")
                config = home_path / ".config/local-agent/config.json"
                config.parent.mkdir(parents=True)
                config.write_text('{"model": "saved"}\n')

                subprocess.run(["bash", str(install), "--instructions", mode], env=env, check=True, capture_output=True)
                subprocess.run(["bash", str(install), "--instructions", mode], env=env, check=True, capture_output=True)

                codex = (home_path / ".codex/AGENTS.md").read_text()
                claude = (home_path / ".claude/CLAUDE.md").read_text()
                self.assertEqual(codex.count("<!-- BEGIN LOCAL-AGENT TOOLKIT -->"), int(mode in {"codex", "both"}))
                self.assertEqual(claude.count("<!-- BEGIN LOCAL-AGENT TOOLKIT -->"), int(mode in {"claude", "both"}))
                self.assertIn("Keep this Codex instruction.", codex)
                self.assertIn("Keep this Claude instruction.", claude)

                subprocess.run(["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True)
                subprocess.run(["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True)
                self.assertFalse((home_path / ".local/bin/local-agent").exists())
                self.assertNotIn("<!-- BEGIN LOCAL-AGENT TOOLKIT -->", (home_path / ".codex/AGENTS.md").read_text())
                self.assertNotIn("<!-- BEGIN LOCAL-AGENT TOOLKIT -->", (home_path / ".claude/CLAUDE.md").read_text())
                self.assertEqual(config.read_text(), '{"model": "saved"}\n')

    @staticmethod
    def _error(function, *args):
        with pytest_like_assert_raises() as caught:
            function(*args)
        return str(caught.exception)


@contextlib.contextmanager
def pytest_like_assert_raises():
    caught = SimpleNamespace(exception=None)
    try:
        yield caught
    except Exception as exc:  # noqa: BLE001 - test helper
        caught.exception = exc
    if caught.exception is None:
        raise AssertionError("expected an exception")


if __name__ == "__main__":
    unittest.main()
