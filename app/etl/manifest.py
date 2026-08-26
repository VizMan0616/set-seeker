"""Pack manifest loading and validation (docs/specs/data-pack-spec.md)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FEATURES = (
    "talismans",
    "charm_tables",
    "charm_generation",
    "excavated_gear",
    "weapon_search",
    "charm_up",
    "skill_plus_two",
    "compound_skills",
)

REQUIRED_FORMATS = (
    "armor_file_ext",
    "armor_header_lines",
    "skills_leading_index_columns",
)


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PackManifest:
    id: str
    name: str
    generation: int
    source_repo: str
    data_dir: str
    features: dict[str, bool]
    formats: dict[str, Any]
    locales: list[str]
    pack_dir: Path

    @property
    def source_data_path(self) -> Path:
        """Absolute path to the legacy data files (read-only, see AGENTS.md rule 1)."""
        return self.pack_dir.parent.parent / self.source_repo / self.data_dir


def load_manifest(pack_dir: Path) -> PackManifest:
    pack_dir = pack_dir.resolve()
    path = pack_dir / "manifest.yaml"
    if not path.is_file():
        raise ManifestError(f"no manifest.yaml in {pack_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: manifest must be a mapping")

    for key in ("id", "name", "generation", "source_repo", "data_dir", "features",
                "formats", "locales"):
        if key not in raw:
            raise ManifestError(f"{path}: missing required key {key!r}")

    features = raw["features"]
    for flag in REQUIRED_FEATURES:
        if not isinstance(features.get(flag), bool):
            raise ManifestError(f"{path}: features.{flag} must be a boolean")

    formats = raw["formats"]
    for key in REQUIRED_FORMATS:
        if key not in formats:
            raise ManifestError(f"{path}: formats.{key} is required")

    manifest = PackManifest(
        id=str(raw["id"]),
        name=str(raw["name"]),
        generation=int(raw["generation"]),
        source_repo=str(raw["source_repo"]),
        data_dir=str(raw["data_dir"]),
        features={k: bool(v) for k, v in features.items()},
        formats=dict(formats),
        locales=[str(loc) for loc in raw["locales"]],
        pack_dir=pack_dir,
    )
    if not manifest.source_data_path.is_dir():
        raise ManifestError(
            f"{path}: source data not found at {manifest.source_data_path} "
            "(restore per SOURCES.md)"
        )
    return manifest
