"""Optimize the seven approved Echo image generations and write their receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from dau.models import IMAGE_MODEL

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO_ROOT / "tmp" / "imagegen" / "output"
PROMPTS_PATH = REPO_ROOT / "tmp" / "imagegen" / "dau-scenes.jsonl"
OUTPUT_ROOT = REPO_ROOT / "web" / "public" / "art" / "scenes"
MAX_WEBP_BYTES = 350_000
ASSETS = (
    (1, "meet-family"),
    (2, "family-dinner"),
    (3, "pho-shop"),
    (4, "around-ward"),
    (5, "mistake-ghost-dinner"),
    (6, "mistake-ward-mother"),
    (7, "mistake-seedling-code"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_for_index(source_root: Path, index: int) -> Path:
    matches = sorted(source_root.glob(f"{index:03d}-*.png"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one generated PNG for job {index}, found {matches}")
    return matches[0]


def _save_bounded_webp(image: Image.Image, destination: Path) -> int:
    prepared = ImageOps.fit(image.convert("RGB"), (1600, 900), Image.Resampling.LANCZOS)
    for quality in (80, 76, 72, 68, 64, 60):
        prepared.save(destination, "WEBP", quality=quality, method=6)
        if destination.stat().st_size <= MAX_WEBP_BYTES:
            return quality
    raise RuntimeError(f"{destination.name} remains over {MAX_WEBP_BYTES} bytes")


def _contact_sheet(entries: list[dict[str, Any]]) -> None:
    tile_size = (560, 315)
    label_height = 31
    columns = 2
    rows = (len(entries) + columns - 1) // columns
    dimensions = (columns * tile_size[0], rows * (tile_size[1] + label_height))
    sheet = Image.new("RGB", dimensions, "#0e0d0c")
    draw = ImageDraw.Draw(sheet)
    for position, entry in enumerate(entries):
        image = Image.open(OUTPUT_ROOT / entry["file"])
        tile = ImageOps.fit(image, tile_size, Image.Resampling.LANCZOS)
        x = (position % columns) * tile_size[0]
        y = (position // columns) * (tile_size[1] + label_height)
        sheet.paste(tile, (x, y))
        draw.text((x + 10, y + tile_size[1] + 9), entry["id"], fill="#f3eadb")
    sheet.save(OUTPUT_ROOT / "contact-sheet.webp", "WEBP", quality=82, method=6)


def build(source_root: Path = DEFAULT_SOURCE) -> list[dict[str, Any]]:
    prompts = [json.loads(line) for line in PROMPTS_PATH.read_text(encoding="utf-8").splitlines()]
    if len(prompts) != len(ASSETS):
        raise RuntimeError(f"Expected {len(ASSETS)} image prompts, found {len(prompts)}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for (index, asset_id), prompt in zip(ASSETS, prompts, strict=True):
        source = _source_for_index(source_root, index)
        destination = OUTPUT_ROOT / f"{asset_id}.webp"
        with Image.open(source) as image:
            quality = _save_bounded_webp(image, destination)
        entries.append(
            {
                "id": asset_id,
                "file": destination.name,
                "model": IMAGE_MODEL,
                "size_requested": prompt["size"],
                "quality_requested": prompt["quality"],
                "webp_quality": quality,
                "dimensions": [1600, 900],
                "prompt": prompt["prompt"],
                "prompt_sha256": hashlib.sha256(prompt["prompt"].encode()).hexdigest(),
                "file_sha256": _sha256(destination),
                "bytes": destination.stat().st_size,
                "source_job": index,
            }
        )
    _contact_sheet(entries)
    manifest = {
        "schema_version": 1,
        "model": IMAGE_MODEL,
        "style": (
            "warm near-black cinematic flat 2D story illustration; "
            "recurring cast; no text or border"
        ),
        "assets": entries,
        "contact_sheet": "contact-sheet.webp",
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    entries = build(args.source)
    print(
        f"Optimized {len(entries)} scene assets: "
        + ", ".join(f"{entry['id']}={entry['bytes'] // 1024}KiB" for entry in entries)
    )


if __name__ == "__main__":
    main()
