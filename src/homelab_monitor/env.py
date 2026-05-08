"""Load environment files for homelab monitor scripts."""

from __future__ import annotations

import os
import sys


ENV_SOURCES: dict[str, str] = {}


def env_source(name: str) -> str:
    if name in ENV_SOURCES:
        return ENV_SOURCES[name]
    return "env" if name in os.environ else "default"


def clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        print(f"Env file not found, skipping: {path}", file=sys.stderr)
        return
    except OSError as exc:
        print(f"Could not read env file, skipping: {path}, error={exc}", file=sys.stderr)
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            print(f"Ignoring invalid env line in {path}: {line}", file=sys.stderr)
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            print(f"Ignoring env line with empty key in {path}", file=sys.stderr)
            continue
        if key in os.environ:
            continue

        os.environ[key] = clean_env_value(value)
        ENV_SOURCES[key] = path


def load_env_files(paths: tuple[str, ...]) -> None:
    for path in paths:
        load_env_file(path)
