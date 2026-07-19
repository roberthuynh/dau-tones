"""Fail the release gate on tracked secrets or unapproved active model IDs."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from dau.models import ACTIVE_MODEL_IDS  # noqa: E402

SOURCE_ROOTS = (
    Path("api/dau"),
    Path("api/scripts"),
    Path("api/index.py"),
    Path("api/eval.py"),
    Path("web/src"),
)
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".ts", ".tsx"}

SECRET_PATTERNS = (
    (
        "OpenAI API key",
        re.compile(r"\bsk-" + r"(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    ),
    (
        "GitHub token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    ),
    (
        "GitHub fine-grained token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)
MODEL_PATTERN = re.compile(r"gpt-[a-z0-9][a-z0-9.\-]*")


def _tracked_paths(root: Path = REPO_ROOT) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return tuple(
        root / value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    )


def _text_files(paths: Iterable[Path]) -> Iterable[tuple[Path, str]]:
    for path in paths:
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            continue
        try:
            yield path, raw.decode("utf-8")
        except UnicodeDecodeError:
            continue


def secret_findings(files: Mapping[str, str]) -> list[str]:
    """Return human-readable secret findings for decoded tracked files."""

    findings: list[str] = []
    for name, content in files.items():
        normalized = Path(name)
        if normalized.name.startswith(".env") and normalized.name != ".env.example":
            findings.append(f"{name}: tracked environment file")
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                findings.append(f"{name}:{line}: possible {label}")
    return findings


def model_findings(files: Mapping[str, str]) -> list[str]:
    """Return active model IDs that are outside the centralized allowlist."""

    found: set[str] = set()
    locations: dict[str, list[str]] = {}
    for name, content in files.items():
        path = Path(name)
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        if not any(path == root or root in path.parents for root in SOURCE_ROOTS):
            continue
        for match in MODEL_PATTERN.finditer(content):
            model = match.group(0)
            found.add(model)
            locations.setdefault(model, []).append(name)

    findings = [
        f"unapproved active model {model!r} in {', '.join(sorted(set(locations[model])))}"
        for model in sorted(found - ACTIVE_MODEL_IDS)
    ]
    missing = ACTIVE_MODEL_IDS - found
    if missing:
        findings.append(
            "active model registry IDs not found in product source: "
            + ", ".join(sorted(missing))
        )
    return findings


def main() -> int:
    decoded = {
        str(path.relative_to(REPO_ROOT)): content
        for path, content in _text_files(_tracked_paths())
    }
    findings = secret_findings(decoded) + model_findings(decoded)
    if findings:
        print("Release guard failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print(f"Release guards passed across {len(decoded)} tracked text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
