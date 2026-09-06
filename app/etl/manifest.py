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
class PackProvenance:
    upstream: str
    commit: str
    license: str


@dataclass(frozen=True)
class PackManifest:
    id: str
    name: str
    generation: int
    data_version: int
    data: dict[str, Any]  # armor_dir, locale_overlays
    provenance: PackProvenance
    features: dict[str, bool]
    progression: dict[str, int]  # guild_rank, village_stars — per-pack caps
    desired_skills_max: int  # Athena Form1.h NumSkills
    charm_points: dict[str, int] | None  # inventory steppers; None if no talismans
    formats: dict[str, Any]
    locales: list[str]
    pack_dir: Path
    translation: str | None = None  # ADR 0009: "fan" for unofficial English names

    @property
    def source_data_path(self) -> Path:
        """Absolute path to vendored armor/skills/decoration files."""
        return self.pack_dir / self.data["armor_dir"]

    @property
    def english_locale_path(self) -> Path | None:
        """Absolute path to the English name overlay directory, if declared."""
        overlays = self.data.get("locale_overlays") or {}
        rel = overlays.get("en")
        if not rel:
            return None
        return self.pack_dir / rel


def _parse_provenance(raw: dict[str, Any], path: Path) -> PackProvenance:
    prov = raw.get("provenance")
    if not isinstance(prov, dict):
        raise ManifestError(f"{path}: missing required key 'provenance'")
    for key in ("upstream", "commit", "license"):
        if key not in prov:
            raise ManifestError(f"{path}: provenance.{key} is required")
    return PackProvenance(
        upstream=str(prov["upstream"]),
        commit=str(prov["commit"]),
        license=str(prov["license"]),
    )


def load_manifest(pack_dir: Path) -> PackManifest:
    pack_dir = pack_dir.resolve()
    path = pack_dir / "manifest.yaml"
    if not path.is_file():
        raise ManifestError(f"no manifest.yaml in {pack_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: manifest must be a mapping")

    for key in (
        "id",
        "name",
        "generation",
        "data_version",
        "data",
        "provenance",
        "features",
        "progression",
        "desired_skills_max",
        "formats",
        "locales",
    ):
        if key not in raw:
            raise ManifestError(f"{path}: missing required key {key!r}")

    data = raw["data"]
    if not isinstance(data, dict) or "armor_dir" not in data:
        raise ManifestError(f"{path}: data.armor_dir is required")

    data_version = raw["data_version"]
    if not isinstance(data_version, int) or data_version < 1:
        raise ManifestError(f"{path}: data_version must be an integer ≥ 1")

    features = raw["features"]
    for flag in REQUIRED_FEATURES:
        if not isinstance(features.get(flag), bool):
            raise ManifestError(f"{path}: features.{flag} must be a boolean")

    formats = raw["formats"]
    for key in REQUIRED_FORMATS:
        if key not in formats:
            raise ManifestError(f"{path}: formats.{key} is required")

    progression = raw["progression"]
    if not isinstance(progression, dict):
        raise ManifestError(f"{path}: progression must be a mapping")
    for key in ("guild_rank", "village_stars"):
        value = progression.get(key)
        if not isinstance(value, int) or value < 1:
            raise ManifestError(f"{path}: progression.{key} must be an integer ≥ 1")

    desired_skills_max = raw["desired_skills_max"]
    if not isinstance(desired_skills_max, int) or desired_skills_max < 1:
        raise ManifestError(f"{path}: desired_skills_max must be an integer ≥ 1")

    charm_points = None
    if features.get("talismans"):
        charm_points = raw.get("charm_points")
        if not isinstance(charm_points, dict):
            raise ManifestError(f"{path}: charm_points is required when talismans is true")
        for key in ("skill1_min", "skill1_max", "skill2_min", "skill2_max"):
            value = charm_points.get(key)
            if not isinstance(value, int):
                raise ManifestError(f"{path}: charm_points.{key} must be an integer")

    manifest = PackManifest(
        id=str(raw["id"]),
        name=str(raw["name"]),
        generation=int(raw["generation"]),
        data_version=int(data_version),
        data=dict(data),
        provenance=_parse_provenance(raw, path),
        features={k: bool(v) for k, v in features.items()},
        progression={
            "guild_rank": int(progression["guild_rank"]),
            "village_stars": int(progression["village_stars"]),
        },
        desired_skills_max=int(desired_skills_max),
        charm_points=dict(charm_points) if charm_points else None,
        formats=dict(formats),
        locales=[str(loc) for loc in raw["locales"]],
        pack_dir=pack_dir,
        translation=str(raw["translation"]) if raw.get("translation") else None,
    )
    if not manifest.source_data_path.is_dir():
        raise ManifestError(
            f"{path}: vendored data not found at {manifest.source_data_path} "
            "(run scripts/vendor_pack_data.py or restore pack vendor/ tree)"
        )
    locale = manifest.english_locale_path
    if locale is not None and not locale.is_dir():
        raise ManifestError(f"{path}: English locale overlay not found at {locale}")
    return manifest


def list_pack_dirs(packs_root: Path | None = None) -> list[Path]:
    """Return pack directories that contain a manifest.yaml, sorted by id."""
    root = (packs_root or Path(__file__).resolve().parents[2] / "packs").resolve()
    dirs = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.yaml").is_file()]
    return sorted(dirs, key=lambda p: p.name)
