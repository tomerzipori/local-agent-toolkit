#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any


def run_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def parse_models(stdout: str) -> tuple[list[str], str | None]:
    payload = json.loads(stdout)
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("models inventory is missing a models list")
    names: list[str] = []
    for entry in models:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    default_model = payload.get("default_model")
    if default_model is not None and not isinstance(default_model, str):
        raise ValueError("default_model must be a string when present")
    return names, default_model


def parse_recommendation(stdout: str) -> tuple[str | None, bool]:
    payload = json.loads(stdout)
    recommendation = payload.get("recommendation")
    if recommendation is None:
        return None, False
    if not isinstance(recommendation, dict):
        raise ValueError("recommendation must be an object or null")
    model = recommendation.get("model")
    if not isinstance(model, str):
        raise ValueError("recommendation.model must be a string")
    return model, recommendation.get("memory_status") in {"resident", "safe", "tight"}


def collect_status() -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    result: dict[str, Any] = {
        "ok": False,
        "local_agent_path": None,
        "local_agent_version": None,
        "ollama_path": None,
        "models_available": [],
        "configured_default_model": None,
        "recommendation_supported": False,
        "recommended_default_model": None,
        "metadata_cache_usable": False,
        "memory_inspection_available": False,
        "ps_available": False,
        "safe_candidate_for_default_context": False,
        "warnings": warnings,
        "errors": errors,
    }

    local_agent_path = shutil.which("local-agent")
    if local_agent_path is None:
        errors.append("local-agent was not found on PATH")
        return result
    result["local_agent_path"] = local_agent_path

    try:
        version = run_command(["local-agent", "--version"], timeout=5.0)
    except subprocess.TimeoutExpired:
        errors.append("local-agent --version timed out")
        return result
    if version.returncode != 0:
        errors.append(f"local-agent --version failed with exit code {version.returncode}")
        return result
    result["local_agent_version"] = version.stdout.strip()

    try:
        inventory = run_command(["local-agent", "models", "--json"], timeout=15.0)
    except subprocess.TimeoutExpired:
        errors.append("local-agent models --json timed out")
        return result
    if inventory.returncode != 0:
        errors.append(f"local-agent models --json failed with exit code {inventory.returncode}")
    else:
        try:
            models, default_model = parse_models(inventory.stdout)
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"local-agent models --json returned invalid JSON: {exc}")
        else:
            result["models_available"] = models
            result["configured_default_model"] = default_model
            if not models:
                errors.append("local-agent models --json returned no installed models")
            try:
                inventory_payload = json.loads(inventory.stdout)
            except json.JSONDecodeError:
                inventory_payload = {}
            cache = inventory_payload.get("cache") if isinstance(inventory_payload, dict) else None
            system = (
                inventory_payload.get("system") if isinstance(inventory_payload, dict) else None
            )
            result["metadata_cache_usable"] = isinstance(cache, dict)
            result["memory_inspection_available"] = (
                isinstance(system, dict)
                and isinstance(system.get("available_bytes"), int)
                and isinstance(system.get("model_budget_bytes"), int)
            )
            result["ps_available"] = isinstance(inventory_payload.get("running_models"), list)

    try:
        recommendation = run_command(
            ["local-agent", "recommend-model", "diagnose", "--num-ctx", "4096", "--json"],
            timeout=15.0,
        )
    except subprocess.TimeoutExpired:
        errors.append("local-agent recommend-model timed out")
    else:
        result["recommendation_supported"] = recommendation.returncode in {0, 1}
        if recommendation.returncode == 0:
            try:
                recommended, safe = parse_recommendation(recommendation.stdout)
            except (ValueError, json.JSONDecodeError) as exc:
                errors.append(f"local-agent recommend-model returned invalid JSON: {exc}")
            else:
                result["recommended_default_model"] = recommended
                result["safe_candidate_for_default_context"] = safe
        elif recommendation.returncode == 1:
            warnings.append(
                "local-agent recommend-model found no safe candidate for a small default context"
            )
        else:
            errors.append(
                f"local-agent recommend-model failed with exit code {recommendation.returncode}"
            )

    ollama_path = shutil.which("ollama")
    result["ollama_path"] = ollama_path
    if ollama_path is None:
        warnings.append("ollama was not found on PATH")
    else:
        try:
            ollama_ps = run_command(["ollama", "ps"], timeout=5.0)
        except subprocess.TimeoutExpired:
            warnings.append("ollama ps timed out")
        else:
            if ollama_ps.returncode != 0:
                warnings.append(f"ollama ps failed with exit code {ollama_ps.returncode}")

    result["ok"] = (
        not errors
        and bool(result["models_available"])
        and bool(result["recommendation_supported"])
        and bool(result["memory_inspection_available"])
        and bool(result["ps_available"])
        and bool(result["safe_candidate_for_default_context"])
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local-agent skill prerequisites.")
    parser.add_argument("--json", action="store_true", help="Print JSON status.")
    args = parser.parse_args()

    result = collect_status()
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"ok: {result['ok']}")
        print(f"local_agent_path: {result['local_agent_path']}")
        print(f"local_agent_version: {result['local_agent_version']}")
        print(f"ollama_path: {result['ollama_path']}")
        print(f"models_available: {', '.join(result['models_available']) or '(none)'}")
        print(f"configured_default_model: {result['configured_default_model']}")
        print(f"recommendation_supported: {result['recommendation_supported']}")
        print(f"recommended_default_model: {result['recommended_default_model']}")
        print(f"metadata_cache_usable: {result['metadata_cache_usable']}")
        print(f"memory_inspection_available: {result['memory_inspection_available']}")
        print(f"ps_available: {result['ps_available']}")
        print(f"safe_candidate_for_default_context: {result['safe_candidate_for_default_context']}")
        if result["warnings"]:
            print("warnings:")
            for warning in result["warnings"]:
                print(f"  - {warning}")
        if result["errors"]:
            print("errors:")
            for error in result["errors"]:
                print(f"  - {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
