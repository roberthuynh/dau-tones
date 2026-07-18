"""Generate one cached meaning illustration for every committed word."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from openai import OpenAI
from PIL import Image, ImageDraw

from dau.content import inventory_document, word_surface
from dau.models import IMAGE_MODEL
from dau.settings import WEB_PUBLIC_ROOT, openai_api_key
from dau.spend import approve, load_ledger, record

STYLE_PROMPT = (
    "Flat 2D minimal illustration, warm palette on near-black, single centered subject, "
    "no text, no letters, no numbers, no border. Strong silhouette, generous negative space, "
    "high contrast, readable as a small square thumbnail."
)
ESTIMATED_IMAGE_USD = 0.05


def prompt_for(word: dict[str, Any]) -> str:
    concept = word.get("art_concept") or word.get("meaning_en")
    return (
        f"{STYLE_PROMPT} Subject concept: {concept}. "
        f"Vietnamese vocabulary meaning: {word['meaning_en']}."
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def usage_payload(usage: Any) -> dict[str, Any] | None:
    """Convert SDK response usage into a JSON-safe ledger payload."""

    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return {"raw": str(usage)}


def manifest_entry(word: dict[str, Any], prompt: str, destination: Path) -> dict[str, Any]:
    return {
        "word_id": word["id"],
        "surface": word_surface(word),
        "model": IMAGE_MODEL,
        "size": "1024x1024",
        "quality": "medium",
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "file_sha256": sha256(destination),
    }


def contact_sheet(paths: list[Path], destination: Path) -> None:
    size = 220
    columns = 5
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * size, rows * size), "#0e0d0c")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((size - 16, size - 36), Image.Resampling.LANCZOS)
        x = (index % columns) * size + (size - image.width) // 2
        y = (index // columns) * size + 8
        sheet.paste(image, (x, y))
        draw.text(
            (index % columns * size + 10, index // columns * size + size - 24),
            path.stem,
            fill="#f4ead6",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, "PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=0, help="Generate at most this many uncached words"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = openai_api_key()
    output_dir = WEB_PUBLIC_ROOT / "art"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    existing_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {"images": []}
    )
    existing_by_id = {item["word_id"]: item for item in existing_manifest.get("images", [])}
    words = inventory_document().get("words", [])
    recorded_labels = {
        event.get("label") for event in load_ledger().get("events", []) if event.get("label")
    }
    for word in words:
        destination = output_dir / f"{word['id']}.png"
        if destination.exists() and word["id"] not in existing_by_id:
            prompt = prompt_for(word)
            existing_by_id[word["id"]] = manifest_entry(word, prompt, destination)
            label = f"art:{word['id']}"
            if label not in recorded_labels:
                record(label, ESTIMATED_IMAGE_USD, {"recovered_from_cached_file": True})
            print(f"recovered cached {destination}; not regenerating")
    pending = [word for word in words if not (output_dir / f"{word['id']}.png").exists()]
    if args.limit:
        pending = pending[: args.limit]
    approve(len(pending) * ESTIMATED_IMAGE_USD, f"meaning art ({len(pending)} images)")
    if args.dry_run:
        print("\n".join(f"{word['id']}: {prompt_for(word)}" for word in pending))
        return
    if pending and not key:
        raise SystemExit(
            "OPENAI_API_KEY is required for uncached art; existing images are never regenerated"
        )
    client = OpenAI(api_key=key, timeout=120, max_retries=1) if key else None
    for word in pending:
        prompt = prompt_for(word)
        assert client is not None
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="medium",
            output_format="png",
            n=1,
        )
        image_bytes = base64.b64decode(result.data[0].b64_json)
        destination = output_dir / f"{word['id']}.png"
        destination.write_bytes(image_bytes)
        existing_by_id[word["id"]] = manifest_entry(word, prompt, destination)
        record(
            f"art:{word['id']}",
            ESTIMATED_IMAGE_USD,
            usage_payload(getattr(result, "usage", None)),
        )
        print(f"generated {destination}")
    entries = [existing_by_id[word["id"]] for word in words if word["id"] in existing_by_id]
    manifest_path.write_text(
        json.dumps(
            {"model": IMAGE_MODEL, "style_prompt": STYLE_PROMPT, "images": entries},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths = [
        output_dir / f"{word['id']}.png"
        for word in words
        if (output_dir / f"{word['id']}.png").exists()
    ]
    if paths:
        contact_sheet(paths, output_dir / "contact-sheet.png")
        print(f"inspect {output_dir / 'contact-sheet.png'} before integration")


if __name__ == "__main__":
    main()
