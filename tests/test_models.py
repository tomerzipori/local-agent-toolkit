from __future__ import annotations

import contextlib
import io
import json
from unittest import mock

from tests.helpers import (
    LocalAgentTestCase,
    OllamaServer,
    RawResponseServer,
    local_agent,
    temporary_home,
    unused_local_port,
)


class ModelTests(LocalAgentTestCase):
    def _memory(self, total=32 * local_agent.GIB, available=24 * local_agent.GIB):
        reserve = max(
            local_agent.MIN_SYSTEM_RESERVE_BYTES, int(total * local_agent.SYSTEM_RESERVE_RATIO)
        )
        return local_agent.SystemMemory(
            platform="darwin",
            architecture="arm64",
            memory_model="unified",
            total_bytes=total,
            available_bytes=available,
            protected_reserve_bytes=reserve,
            model_budget_bytes=min(available, total - reserve),
            confidence="high",
            warnings=(),
        )

    def test_model_discovery_and_generate_payload(self):
        with OllamaServer({"models": [{"name": "model:latest"}]}) as server:
            self.assertEqual(local_agent.discover_models(server.host), ["model:latest"])
            side_effect = [{"models": [{"name": "model:latest"}]}, {"response": " answer "}]
            with mock.patch.object(local_agent, "request_json", side_effect=side_effect) as request:
                result = local_agent.call_ollama(
                    "prompt", local_agent.Settings("model:latest", server.host, 123, 456)
                )
            self.assertEqual(result, "answer")
            payload = request.call_args_list[1].args[2]
            self.assertEqual(payload["model"], "model:latest")
            self.assertEqual(payload["options"]["num_ctx"], 123)
            self.assertFalse(payload["stream"])

    def test_enriched_model_inventory_uses_tags_and_show_and_fills_optional_metadata(self):
        with temporary_home():
            with mock.patch.object(
                local_agent,
                "request_json",
                side_effect=[
                    {
                        "models": [
                            {
                                "name": "coder:latest",
                                "size": 123,
                                "details": {"family": "tags-family"},
                            },
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
                        "model_info": {
                            "llama.context_length": 8192,
                            "llama.block_count": 32,
                            "llama.embedding_length": 4096,
                            "llama.attention.head_count": 32,
                            "llama.attention.head_count_kv": 8,
                        },
                    },
                    {"details": {}, "model_info": {}},
                ],
            ) as request:
                inventory = local_agent.model_inventory("http://host")

        self.assertEqual(inventory[0]["name"], "coder:latest")
        self.assertEqual(inventory[0]["size_bytes"], 123)
        self.assertEqual(inventory[0]["family"], "llama")
        self.assertEqual(inventory[0]["families"], ["llama"])
        self.assertEqual(inventory[0]["parameter_size"], "7B")
        self.assertEqual(inventory[0]["parameter_count"], 7_000_000_000)
        self.assertEqual(inventory[0]["quantization"], "Q4_K_M")
        self.assertEqual(inventory[0]["quantization_rank"], 5)
        self.assertEqual(inventory[0]["capabilities"], ["completion"])
        self.assertEqual(inventory[0]["context_length"], 8192)
        self.assertEqual(inventory[0]["coding_signal"], "strong")
        self.assertEqual(inventory[0]["kv_bytes_per_token_f16"], 131072)
        self.assertEqual(inventory[1]["name"], "small:latest")
        self.assertEqual(
            request.call_args_list[1].args[1:], ("/api/show", {"model": "coder:latest"})
        )
        self.assertEqual(
            request.call_args_list[2].args[1:], ("/api/show", {"model": "small:latest"})
        )

    def test_model_inventory_propagates_show_api_failures(self):
        with temporary_home():
            with mock.patch.object(
                local_agent,
                "request_json",
                side_effect=[
                    {"models": [{"name": "model:latest"}]},
                    RuntimeError("Ollama returned HTTP 404"),
                ],
            ):
                message = self._error(local_agent.model_inventory, "http://host")
        self.assertIn("HTTP 404", message)

    def test_models_json_reports_default_and_plain_output_is_unchanged(self):
        with temporary_home():
            local_agent.save_config({"model": "coder:latest"})
            side_effect = [
                {"models": [{"name": "coder:latest", "size": 10}]},
                {"details": {}, "capabilities": [], "model_info": {}},
                {"models": []},
            ]
            with (
                mock.patch.object(local_agent, "request_json", side_effect=side_effect),
                mock.patch.object(
                    local_agent, "inspect_system_memory", return_value=self._memory()
                ),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                status = local_agent.main(["models", "--json", "--host", "http://host"])
            self.assertEqual(status, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["host"], "http://host")
            self.assertEqual(payload["default_model"], "coder:latest")
            self.assertEqual(payload["models"][0]["name"], "coder:latest")
            self.assertEqual(payload["models"][0]["memory"]["status"], "safe")

            with (
                mock.patch.object(
                    local_agent, "request_json", return_value={"models": [{"name": "coder:latest"}]}
                ),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                status = local_agent.main(["models", "--host", "http://host"])
            self.assertEqual(status, 0)
            self.assertEqual(stdout.getvalue(), "coder:latest\n")

    def test_empty_models_missing_ollama_and_api_error(self):
        with OllamaServer({"models": []}) as server:
            message = self._error(local_agent.discover_models, server.host)
            self.assertIn("No Ollama models are installed", message)
        message = self._error(
            local_agent.discover_models, f"http://127.0.0.1:{unused_local_port()}"
        )
        self.assertIn("Could not reach Ollama", message)
        with OllamaServer({"error": "bad request"}, status=500) as server:
            message = self._error(local_agent.discover_models, server.host)
            self.assertIn("HTTP 500", message)

    def test_stale_model_is_rejected(self):
        with mock.patch.object(local_agent, "discover_models", return_value=["new"]):
            message = self._error(
                local_agent.call_ollama, "prompt", local_agent.Settings("old", "host", 1, 1)
            )
        self.assertIn("is not installed", message)

    def test_models_json_contains_schema_version(self):
        with temporary_home():
            local_agent.save_config({"model": "coder:latest"})
            side_effect = [
                {"models": [{"name": "coder:latest", "size": 10}]},
                {"details": {}, "capabilities": [], "model_info": {}},
                {"models": []},
            ]
            with (
                mock.patch.object(local_agent, "request_json", side_effect=side_effect),
                mock.patch.object(
                    local_agent, "inspect_system_memory", return_value=self._memory()
                ),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                status = local_agent.main(["models", "--json", "--host", "http://host"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(stdout.getvalue())["schema_version"], 2)

    def test_models_json_contract_remains_stable(self):
        with temporary_home():
            local_agent.save_config({"model": "coder:latest"})
            side_effect = [
                {"models": [{"name": "coder:latest", "size": 10}]},
                {"details": {}, "capabilities": [], "model_info": {}},
                {"models": []},
            ]
            with (
                mock.patch.object(local_agent, "request_json", side_effect=side_effect),
                mock.patch.object(
                    local_agent, "inspect_system_memory", return_value=self._memory()
                ),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                status = local_agent.main(["models", "--json", "--host", "http://host"])
            self.assertEqual(status, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(
                set(payload),
                {
                    "schema_version",
                    "host",
                    "default_model",
                    "effective_num_ctx",
                    "models",
                    "running_models",
                    "system",
                    "cache",
                    "warnings",
                },
            )
            self.assertEqual(
                set(payload["models"][0]),
                {
                    "name",
                    "size_bytes",
                    "digest",
                    "family",
                    "families",
                    "parameter_size",
                    "parameter_count",
                    "quantization",
                    "quantization_rank",
                    "capabilities",
                    "context_length",
                    "coding_signal",
                    "base_model_key",
                    "kv_bytes_per_token_f16",
                    "running",
                    "memory",
                },
            )

    def test_recommend_model_warm_cache_uses_tags_and_ps_but_not_show(self):
        with temporary_home():
            calls = []

            def fake_request(_host, endpoint, payload=None, **_kwargs):
                calls.append(endpoint)
                if endpoint == "/api/tags":
                    return {
                        "models": [
                            {
                                "name": "qwen-coder:latest",
                                "digest": "sha256:a",
                                "size": 4 * local_agent.GIB,
                            }
                        ]
                    }
                if endpoint == "/api/show":
                    return {
                        "details": {
                            "family": "qwen",
                            "families": ["qwen"],
                            "parameter_size": "7B",
                            "quantization_level": "Q4_K_M",
                        },
                        "capabilities": ["completion"],
                        "model_info": {"qwen.context_length": 32768},
                    }
                if endpoint == "/api/ps":
                    return {"models": []}
                raise AssertionError(endpoint)

            with (
                mock.patch.object(local_agent, "request_json", side_effect=fake_request),
                mock.patch.object(
                    local_agent, "inspect_system_memory", return_value=self._memory()
                ),
            ):
                first = local_agent.recommend_model("http://host", command="review", num_ctx=8192)
                calls.clear()
                second = local_agent.recommend_model("http://host", command="review", num_ctx=8192)

        self.assertEqual(first["recommendation"]["model"], "qwen-coder:latest")
        self.assertEqual(second["performance"]["show_requests"], 0)
        self.assertEqual(calls.count("/api/tags"), 1)
        self.assertEqual(calls.count("/api/ps"), 1)
        self.assertNotIn("/api/show", calls)

    def test_recommend_model_rejects_unsafe_preferred_model(self):
        with temporary_home():

            def fake_request(_host, endpoint, payload=None, **_kwargs):
                if endpoint == "/api/tags":
                    return {
                        "models": [
                            {
                                "name": "huge-coder:latest",
                                "digest": "sha256:huge",
                                "size": 40 * local_agent.GIB,
                            },
                            {
                                "name": "small-coder:latest",
                                "digest": "sha256:small",
                                "size": 4 * local_agent.GIB,
                            },
                        ]
                    }
                if endpoint == "/api/show":
                    parameter = "80B" if payload["model"].startswith("huge") else "7B"
                    return {
                        "details": {
                            "family": "qwen",
                            "parameter_size": parameter,
                            "quantization_level": "Q4_K_M",
                        },
                        "capabilities": ["completion"],
                        "model_info": {"qwen.context_length": 32768},
                    }
                if endpoint == "/api/ps":
                    return {"models": []}
                raise AssertionError(endpoint)

            with (
                mock.patch.object(local_agent, "request_json", side_effect=fake_request),
                mock.patch.object(
                    local_agent,
                    "inspect_system_memory",
                    return_value=self._memory(32 * local_agent.GIB, 12 * local_agent.GIB),
                ),
            ):
                payload = local_agent.recommend_model(
                    "http://host",
                    command="review",
                    num_ctx=8192,
                    preferred_models=("huge-coder:latest",),
                )
        self.assertEqual(payload["recommendation"]["model"], "small-coder:latest")
        self.assertIn("unsafe-memory", payload["excluded"][0]["reasons"])

    def test_fast_and_strong_profiles_rank_differently(self):
        small = local_agent.InstalledModel(
            "small-coder:latest",
            None,
            4 * local_agent.GIB,
            "qwen",
            (),
            "7B",
            7_000_000_000,
            "Q4_K_M",
            ("completion",),
            32768,
            "strong",
            "qwen-7b",
            5,
            None,
        )
        large = local_agent.InstalledModel(
            "large-coder:latest",
            None,
            8 * local_agent.GIB,
            "qwen",
            (),
            "14B",
            14_000_000_000,
            "Q4_K_M",
            ("completion",),
            32768,
            "strong",
            "qwen-14b",
            5,
            None,
        )
        candidates_fast, _excluded, _warnings = local_agent.build_candidates(
            [large, small],
            [],
            self._memory(64 * local_agent.GIB, 48 * local_agent.GIB),
            command="find",
            num_ctx=8192,
            quality=None,
            preferred=set(),
            excluded=set(),
        )
        candidates_strong, _excluded, _warnings = local_agent.build_candidates(
            [small, large],
            [],
            self._memory(64 * local_agent.GIB, 48 * local_agent.GIB),
            command="review",
            num_ctx=8192,
            quality=None,
            preferred=set(),
            excluded=set(),
        )
        self.assertEqual(candidates_fast[0].installed.name, "small-coder:latest")
        self.assertEqual(candidates_strong[0].installed.name, "large-coder:latest")

    def test_running_models_match_by_digest_before_name(self):
        installed = local_agent.InstalledModel(
            "installed-alias:latest",
            "sha256:shared",
            4 * local_agent.GIB,
            "qwen",
            (),
            "7B",
            7_000_000_000,
            "Q4_K_M",
            ("completion",),
            32768,
            "strong",
            "qwen-7b",
            5,
            None,
        )
        running = local_agent.RunningModel(
            "loaded-alias:latest",
            "sha256:shared",
            5 * local_agent.GIB,
            0,
            32768,
            None,
        )
        candidates, _excluded, _warnings = local_agent.build_candidates(
            [installed],
            [running],
            self._memory(),
            command="review",
            num_ctx=8192,
            quality=None,
            preferred=set(),
            excluded=set(),
        )
        self.assertEqual(candidates[0].running, running)
        self.assertEqual(candidates[0].memory.status, "resident")

    def test_recommend_model_name_only_stdout_has_only_model_name(self):
        with temporary_home():
            responses = [
                {
                    "models": [
                        {
                            "name": "qwen-coder:latest",
                            "digest": "sha256:a",
                            "size": 4 * local_agent.GIB,
                        }
                    ]
                },
                {
                    "details": {
                        "family": "qwen",
                        "parameter_size": "7B",
                        "quantization_level": "Q4_K_M",
                    },
                    "capabilities": ["completion"],
                    "model_info": {"qwen.context_length": 32768},
                },
                {"models": []},
            ]
            with (
                mock.patch.object(local_agent, "request_json", side_effect=responses),
                mock.patch.object(
                    local_agent, "inspect_system_memory", return_value=self._memory()
                ),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
                contextlib.redirect_stderr(io.StringIO()) as stderr,
            ):
                status = local_agent.main(
                    ["recommend-model", "review", "--host", "http://host", "--name-only"]
                )
        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "qwen-coder:latest\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_localhost_does_not_require_remote_consent(self):
        self.assertEqual(local_agent.classify_host("http://localhost:11434"), "local")
        local_agent.ensure_host_allowed("http://localhost:11434", allow_remote_host=False)

    def test_loopback_ip_does_not_require_remote_consent(self):
        self.assertEqual(local_agent.classify_host("http://127.0.0.1:11434"), "local")
        self.assertEqual(local_agent.classify_host("http://[::1]:11434"), "local")
        local_agent.ensure_host_allowed("http://127.0.0.1:11434", allow_remote_host=False)

    def test_remote_https_requires_consent(self):
        message = self._error(local_agent.ensure_host_allowed, "https://example.com", False, False)
        self.assertIn("--allow-remote-host", message)

    def test_remote_http_requires_insecure_consent(self):
        message = self._error(local_agent.ensure_host_allowed, "http://example.com", True, False)
        self.assertIn("--allow-insecure-remote-host", message)

    def test_url_with_credentials_is_rejected(self):
        message = self._error(local_agent.normalize_host, "http://user:pass@example.com")
        self.assertIn("embedded credentials", message)

    def test_ollama_invalid_utf8_response(self):
        with RawResponseServer(b"\xff\xfe") as server:
            message = self._error(local_agent.request_json, server.host, "/api/tags")
        self.assertIn("invalid JSON", message)

    def test_ollama_response_body_size_limit(self):
        payload = b"{" + b'"' + b"a" * local_agent.MAX_OLLAMA_RESPONSE_BYTES + b'":1}'
        with RawResponseServer(payload) as server:
            message = self._error(local_agent.request_json, server.host, "/api/tags")
        self.assertIn("more than", message)
