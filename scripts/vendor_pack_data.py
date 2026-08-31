#!/usr/bin/env python3
"""Copy Athena Run/Data files into packs/<id>/vendor/ for committed pack data.

Maintainer-only: requires a local sources/<REPO>-ASS clone (see SOURCES.md).
Runtime and Docker no longer depend on sources/ after vendoring.

Usage:
  python scripts/vendor_pack_data.py mhfu
  python scripts/vendor_pack_data.py mhp3
  python scripts/vendor_pack_data.py --all
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# pack_id -> (source_repo, data_dir under clone, locale subdir name under Languages/)
PACK_SOURCES: dict[str, tuple[str, str, str]] = {
    "mhfu": (
        "sources/MHFU-ASS",
        "Run/Data",
        "English MHFU",
    ),
    "mhp3": (
        "sources/MHP3-ASS",
        "Run/Data",
        "English (TMO)",
    ),
}

DATA_FILES = (
    "head", "body", "arms", "waist", "legs",
    "skills", "decorations",
)
LOCALE_FILES = (
    "head", "body", "arms", "waist", "legs",
    "skills", "decorations",
)


def vendor_pack(pack_id: str, *, force: bool = False) -> None:
    if pack_id not in PACK_SOURCES:
        raise SystemExit(f"unknown pack {pack_id!r}; known: {', '.join(PACK_SOURCES)}")

    source_repo, data_dir, locale_name = PACK_SOURCES[pack_id]
    source_root = REPO_ROOT / source_repo / data_dir
    if not source_root.is_dir():
        raise SystemExit(
            f"source data not found at {source_root} — restore clone per SOURCES.md"
        )

    pack_dir = REPO_ROOT / "packs" / pack_id
    vendor_data = pack_dir / "vendor" / "data"
    vendor_locale = pack_dir / "vendor" / "locales" / "en"

    manifest = pack_dir / "manifest.yaml"
    if not manifest.is_file():
        raise SystemExit(f"no manifest at {manifest}")

    import yaml  # noqa: PLC0415 — script entry point

    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    ext = raw.get("formats", {}).get("armor_file_ext", "csv")

    if vendor_data.exists() and not force:
        print(f"[skip] {pack_id}: vendor/data already exists (use --force)")
        return

    if vendor_data.exists():
        shutil.rmtree(vendor_data.parent)
    vendor_data.mkdir(parents=True)
    vendor_locale.mkdir(parents=True)

    def data_ext(stem: str) -> str:
        if stem == "skills":
            return "txt"
        return ext

    for stem in DATA_FILES:
        file_ext = data_ext(stem)
        src = source_root / f"{stem}.{file_ext}"
        if not src.is_file():
            raise SystemExit(f"missing source file {src}")
        shutil.copy2(src, vendor_data / src.name)
        print(f"[copy] {src.relative_to(REPO_ROOT)} -> {vendor_data / src.name}")

    source_locale = source_root / "Languages" / locale_name
    if not source_locale.is_dir():
        raise SystemExit(f"missing locale overlay {source_locale}")

    for stem in LOCALE_FILES:
        src = source_locale / f"{stem}.txt"
        if not src.is_file():
            raise SystemExit(f"missing locale file {src}")
        shutil.copy2(src, vendor_locale / src.name)
        print(f"[copy] {src.relative_to(REPO_ROOT)} -> {vendor_locale / src.name}")

    notice = pack_dir / "vendor" / "NOTICE"
    notice.write_text(
        f"Game data in this directory is derived from Athena's Armor Set Search (ASS),\n"
        f"published by AthenaADP under the MIT License.\n\n"
        f"Upstream: {source_repo.replace('sources/', 'AthenaADP/')}\n"
        f"See SOURCES.md for the pinned commit hash.\n",
        encoding="utf-8",
    )
    print(f"[write] {notice.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", nargs="?", help="pack id (mhfu, mhp3)")
    parser.add_argument("--all", action="store_true", help="vendor every known pack")
    parser.add_argument("--force", action="store_true", help="overwrite existing vendor/")
    args = parser.parse_args(argv)

    if args.all:
        for pack_id in PACK_SOURCES:
            vendor_pack(pack_id, force=args.force)
        return 0

    if not args.pack:
        parser.error("pack id required unless --all")
    vendor_pack(args.pack, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
