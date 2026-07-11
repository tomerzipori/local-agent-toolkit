from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path
from unittest import mock

from tests.helpers import LocalAgentTestCase, local_agent, temporary_home


class ExecutionTests(LocalAgentTestCase):
    def test_fix_test_executes_command_and_propagates_status(self):
        args = [
            "fix-test",
            "diagnose",
            "--command",
            "printf test-output; exit 3",
            "--model",
            "model",
        ]
        captured = []
        with (
            mock.patch.object(
                local_agent,
                "call_ollama",
                side_effect=lambda prompt, _settings, **_kwargs: (
                    captured.append(prompt) or "advice"
                ),
            ),
            mock.patch.dict("os.environ", {}, clear=False),
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = local_agent.main(args)
        self.assertEqual(status, 3)
        self.assertIn("advice", stdout.getvalue())
        self.assertIn("test-output", captured[0])
        self.assertIn("EXIT CODE: 3", captured[0])
        self.assertIn("Executing local shell command", stderr.getvalue())

    def test_ctrl_c_returns_130(self):
        with (
            temporary_home(),
            mock.patch.object(
                local_agent,
                "resolve_settings",
                return_value=local_agent.Settings("model", "http://127.0.0.1:11434", 1, 10),
            ),
            mock.patch.object(local_agent, "collect_context", side_effect=KeyboardInterrupt),
        ):
            status = local_agent.main(["files", "Explain", "--model", "model"])
        self.assertEqual(status, 130)

    def test_broken_pipe_exits_cleanly(self):
        def flaky_print(*args, **kwargs):
            if kwargs.get("file") is not None:
                return None
            if args == ("answer",):
                raise BrokenPipeError
            return None

        with (
            temporary_home(),
            mock.patch.object(
                local_agent,
                "resolve_settings",
                return_value=local_agent.Settings("model", "http://127.0.0.1:11434", 1, 10),
            ),
            mock.patch.object(
                local_agent,
                "collect_context",
                return_value=type(
                    "Collection",
                    (),
                    {"text": "x", "included": [], "skipped": [], "command_status": None},
                )(),
            ),
            mock.patch.object(local_agent, "call_ollama", return_value="answer"),
            mock.patch("builtins.print", side_effect=flaky_print),
        ):
            status = local_agent.main(["files", "Explain", "--model", "model"])
        self.assertEqual(status, 0)

    def test_output_save_parent_directory_missing(self):
        with tempfile.TemporaryDirectory() as directory, temporary_home():
            target = Path(directory) / "nested" / "output.txt"
            with (
                mock.patch.object(
                    local_agent,
                    "resolve_settings",
                    return_value=local_agent.Settings("model", "http://127.0.0.1:11434", 1, 10),
                ),
                mock.patch.object(
                    local_agent,
                    "collect_context",
                    return_value=type(
                        "Collection",
                        (),
                        {"text": "x", "included": [], "skipped": [], "command_status": None},
                    )(),
                ),
                mock.patch.object(local_agent, "call_ollama", return_value="answer"),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                status = local_agent.main(
                    ["files", "Explain", "--model", "model", "--save", str(target)]
                )
            self.assertEqual(status, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "answer\n")
