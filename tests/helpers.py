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


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakePipe(io.StringIO):
    def isatty(self):
        return False


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


class RawResponseServer:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                return

        status = self.status
        payload = self.payload
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


@contextlib.contextmanager
def pytest_like_assert_raises():
    caught = SimpleNamespace(exception=None)
    try:
        yield caught
    except Exception as exc:  # noqa: BLE001 - test helper
        caught.exception = exc
    if caught.exception is None:
        raise AssertionError("expected an exception")


class LocalAgentTestCase(unittest.TestCase):
    def _validated_config(self):
        return local_agent.validate_config(local_agent.load_config())

    def _git(self, repo: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout

    def _commit(self, repo: Path, message: str = "initial") -> None:
        self._git(
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            message,
        )

    def _context_args(self, **overrides):
        defaults = {
            "mode": "files",
            "task": "",
            "files": [],
            "stdin": False,
            "allow_outside_repo": False,
            "include_untracked": False,
            "include_ignored": False,
            "allow_sensitive_files": False,
            "show_context_files": False,
            "allow_remote_host": False,
            "allow_insecure_remote_host": False,
            "max_file_bytes": local_agent.DEFAULT_MAX_FILE_BYTES,
            "max_context_files": local_agent.DEFAULT_MAX_CONTEXT_FILES,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @staticmethod
    def _error(function, *args):
        with pytest_like_assert_raises() as caught:
            function(*args)
        return str(caught.exception)


def unused_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
