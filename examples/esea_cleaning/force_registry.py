"""Registry of police forces and their on-disk attachment locations.

Reads `examples/esea_data/fetch_manifest.json` (produced by
`examples/esea_fetch_data_attachments.py`) and joins it with per-force YAML
configs under `examples/esea_cleaning/mappings/` to produce ForceEntry objects
that the orchestrator iterates over.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "examples" / "esea_data"
MAPPINGS_DIR = REPO_ROOT / "examples" / "esea_cleaning" / "mappings"
MANIFEST_PATH = DATA_DIR / "fetch_manifest.json"


@dataclass(frozen=True)
class ForceEntry:
    force_id: str
    display_name: str
    data_dir: Path
    attachment_files: tuple[Path, ...]
    config_path: Path | None


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s


def _find_config(force_id: str) -> Path | None:
    candidate = MAPPINGS_DIR / f"{force_id}.yaml"
    return candidate if candidate.exists() else None


def list_forces() -> list[ForceEntry]:
    """Return one ForceEntry per authority — with attachments from every wave
    combined. A given authority may have 2–4 entries in the manifest (one per
    FOI campaign wave); we aggregate their attachments into a single entry so
    the orchestrator processes each force exactly once.
    """
    with MANIFEST_PATH.open() as f:
        manifest = json.load(f)

    by_force: dict[str, dict] = {}
    for item in manifest:
        attachments = item.get("attachments") or []
        if not attachments:
            continue
        authority = item["authority"]
        force_id = _slugify(authority)
        if force_id not in by_force:
            by_force[force_id] = {
                "force_id": force_id,
                "display_name": authority,
                "data_dir": DATA_DIR / authority,
                "files": [],
            }
        by_force[force_id]["files"].extend(REPO_ROOT / p for p in attachments)

    entries: list[ForceEntry] = []
    for agg in by_force.values():
        entries.append(
            ForceEntry(
                force_id=agg["force_id"],
                display_name=agg["display_name"],
                data_dir=agg["data_dir"],
                attachment_files=tuple(agg["files"]),
                config_path=_find_config(agg["force_id"]),
            )
        )
    return entries


def find_force(force_id: str) -> ForceEntry | None:
    for entry in list_forces():
        if entry.force_id == force_id:
            return entry
    return None
