"""Build the protected-research release archive(s) from a project folder (READ-ONLY on the project).

Packages every file registered in docs/CHECKSUMS.sha256 that is not shipped in the Git repository, byte for byte, at
its original relative path, plus a RELEASE_MANIFEST.json (path, size, SHA-256 of every packaged file).

  python build_release_archive.py <project_root> <output_dir> [--version 1.0.0]

Two archives:
  dpe-v2-research-results-<v>.zip    outputs/runs/<registered runs>/... and data/reference/...  (for the GitHub Release)
  dpe-v2-legacy-reference-<v>.zip    legacy/...  (contains local paths from the original project; NOT for public release)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PUBLISHED_PREFIXES = ("app/", "src/", "tests/", "scripts/", "config/", "docs/", "notebooks/", "data/raw/")
PUBLISHED_FILES = {"README.md", ".gitignore", ".env.example", "pytest.ini", "run_dashboard.cmd", "requirements.txt",
                   "requirements-dashboard.txt", "requirements-dev.txt", "requirements-challenger.txt"}
ARCHIVES = {"research-results": ("outputs/runs/", "data/reference/"), "legacy-reference": ("legacy/",)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def registry(root: Path) -> dict[str, str]:
    out = {}
    for line in (root / "docs" / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            digest, rel = line.split(None, 1)
            out[rel.strip().lstrip("*")] = digest
    return out


def build(root: Path, out_dir: Path, version: str) -> list[Path]:
    reg = registry(root)
    shipped = lambda r: r in PUBLISHED_FILES or r.startswith(PUBLISHED_PREFIXES)  # noqa: E731
    need = sorted(r for r in reg if not shipped(r))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, prefixes in ARCHIVES.items():
        files = [r for r in need if r.startswith(prefixes)]
        entries = []
        for rel in files:
            p = root / rel
            digest = sha256(p)
            if digest != reg[rel]:
                raise SystemExit(f"ABORT: {rel} does not match the registry - nothing packaged")
            entries.append({"path": rel, "size": p.stat().st_size, "sha256": digest})
        manifest = {"archive": f"dpe-v2-{name}-{version}", "format": 1, "version": version,
                    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "source_registry": "docs/CHECKSUMS.sha256", "registry_sha256": sha256(root / "docs" / "CHECKSUMS.sha256"),
                    "file_count": len(entries), "total_bytes": sum(e["size"] for e in entries),
                    "status": "Protected research outputs, unchanged. SIMULATED / HYPOTHETICAL_UNAPPROVED / NOT_EXECUTED.",
                    "files": entries}
        target = out_dir / f"dpe-v2-{name}-{version}.zip"
        if target.exists():
            raise SystemExit(f"ABORT: {target} already exists - never overwrite a release archive")
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr("RELEASE_MANIFEST.json", json.dumps(manifest, indent=2))
            for e in entries:
                z.write(root / e["path"], arcname=e["path"])
        (out_dir / f"{target.name}.sha256").write_text(f"{sha256(target)}  {target.name}\n", encoding="utf-8")
        print(f"{target.name}: {len(entries)} files, {manifest['total_bytes'] / 1048576:.1f} MB raw -> "
              f"{target.stat().st_size / 1048576:.1f} MB")
        written.append(target)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project_root", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--version", default="1.0.0")
    a = ap.parse_args()
    build(a.project_root.resolve(), a.output_dir.resolve(), a.version)
