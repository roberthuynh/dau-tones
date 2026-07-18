"""Keep librosa's lazy imports working in stripped serverless bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import lazy_loader  # type: ignore[import-untyped]

_STUB_ROOT = Path(__file__).with_name("_librosa_stubs")
_ORIGINAL_ATTACH_STUB = lazy_loader.attach_stub


def _attach_stub_with_fallback(package_name: str, filename: str) -> tuple[Any, Any, Any]:
    """Use vendored upstream stubs only when a packager removed package data."""

    try:
        return cast(tuple[Any, Any, Any], _ORIGINAL_ATTACH_STUB(package_name, filename))
    except ValueError as error:
        if "non-existent stub" not in str(error) or not package_name.startswith("librosa"):
            raise
        fallback = _STUB_ROOT.joinpath(*package_name.split("."), "__init__.pyi")
        if not fallback.is_file():
            raise
        return cast(
            tuple[Any, Any, Any],
            _ORIGINAL_ATTACH_STUB(package_name, str(fallback)),
        )


# Vercel's Python packager strips dependency ``.pyi`` files. Librosa uses those
# files at runtime to define lazy imports, so install a narrowly scoped fallback
# before importing it. Normal local installs continue to use their own stubs.
lazy_loader.attach_stub = _attach_stub_with_fallback

import librosa as librosa  # noqa: E402

__all__ = ["librosa"]
