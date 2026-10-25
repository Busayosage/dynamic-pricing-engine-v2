"""Restore the protected research results from a release archive and verify every file (Python 3.11, any OS).

  python scripts/restore_research_release.py <archive.zip> [--project-root PATH] [--dry-run] [--force]
  python scripts/restore_research_release.py --verify-only [--project-root PATH]

Steps (nothing is written unless every check passes):
  1  read RELEASE_MANIFEST.json; every archive member must be listed, relative, inside an allowed folder
  2  every listed file must also be in the project's docs/CHECKSUMS.sha256 with the same SHA-256
  3  existing files: identical ones are skipped; different ones stop the restore unless --force is given
  4  extract into a temporary folder inside the project, verify size and SHA-256 of every file, then move into place
  5  re-verify every placed file; --verify-only checks the whole registry against the project
Exit codes: 0 success; 1 verification failure; 2 usage error or conflict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED = ("outputs/runs/", "data/reference/", "legacy/")
MANIFEST = "RELEASE_MANIFEST.json"
WINDOWS_MAX_PATH = 260  # without Windows long-path support


class RestoreError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_registry(root: Path) -> dict[str, str]:
    reg = root / "docs" / "CHECKSUMS.sha256"
    if not reg.is_file():
        raise RestoreError(f"{reg} not found — run this from a complete clone of the repository", 2)
    out = {}
    for line in reg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            digest, rel = line.split(None, 1)
            out[rel.strip().lstrip("*")] = digest.lower()
    return out


def safe_rel(name: str) -> str:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name or (p.parts and ":" in p.parts[0]):
        raise RestoreError(f"unsafe path in archive: {name!r}")
    if not name.startswith(ALLOWED):
        raise RestoreError(f"archive file outside the allowed folders {ALLOWED}: {name!r}")
    return name


def load_manifest(z: zipfile.ZipFile) -> dict:
    try:
        m = json.loads(z.read(MANIFEST).decode("utf-8"))
    except KeyError:
        raise RestoreError(f"{MANIFEST} missing — not a Dynamic Pricing Engine V2 release archive", 2)
    if m.get("format") != 1 or not isinstance(m.get("files"), list):
        raise RestoreError("unsupported manifest format", 2)
    listed = {e["path"] for e in m["files"]}
    members = {n for n in z.namelist() if not n.endswith("/")} - {MANIFEST}
    if members - listed:
        raise RestoreError(f"archive contains files not in its manifest: {sorted(members - listed)[:5]}")
    if listed - members:
        raise RestoreError(f"manifest lists files missing from the archive: {sorted(listed - members)[:5]}")
    for e in m["files"]:
        safe_rel(e["path"])
    return m


def restore(archive: Path, root: Path, dry_run: bool = False, force: bool = False) -> dict:
    if not archive.is_file():
        raise RestoreError(f"archive not found: {archive}", 2)
    registry = read_registry(root)
    with zipfile.ZipFile(archive) as z:
        m = load_manifest(z)
        files = m["files"]
        bad = [e["path"] for e in files if registry.get(e["path"]) != e["sha256"].lower()]
        if bad:
            raise RestoreError(f"{len(bad)} archive file(s) do not match docs/CHECKSUMS.sha256 (wrong archive version?): "
                               f"{bad[:5]}")
        skip, conflicts, todo = [], [], []
        for e in files:
            target = root / e["path"]
            if target.exists():
                (skip if target.is_file() and sha256(target) == e["sha256"] else conflicts).append(e["path"])
            else:
                todo.append(e)
        if conflicts and not force:
            raise RestoreError(f"{len(conflicts)} existing file(s) differ from the release and would be overwritten "
                               f"(re-run with --force to replace them): {conflicts[:10]}", 2)
        if force:
            todo += [e for e in files if e["path"] in conflicts]
        report = {"archive": m["archive"], "listed": len(files), "to_write": len(todo), "already_identical": len(skip),
                  "replaced": len(conflicts) if force else 0}
        tmp = root / f".restore-staging-{uuid.uuid4().hex[:8]}"
        longest = max((len(str(tmp / e["path"])) for e in todo), default=0)
        report["longest_path_chars"] = longest
        if os.name == "nt" and longest >= WINDOWS_MAX_PATH:
            raise RestoreError(f"the project folder path is too long for Windows ({longest} characters needed, limit "
                               f"{WINDOWS_MAX_PATH - 1}). Move the project to a shorter folder such as C:\\dev\\dpe-v2, "
                               "or enable Windows long-path support, then run again. Nothing was written.", 2)
        if dry_run or not todo:
            return report
        try:
            for e in todo:  # extract and verify everything before placing anything
                dest = tmp / e["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(e["path"]) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                if dest.stat().st_size != e["size"] or sha256(dest) != e["sha256"]:
                    raise RestoreError(f"extracted file failed verification: {e['path']}")
            for e in todo:
                target = root / e["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp / e["path"], target)
        except OSError as err:
            raise RestoreError(f"could not write {getattr(err, 'filename', '') or 'a file'}: {err.strerror or err}. "
                               "Check free disk space, permissions and (on Windows) path length.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    failed = [e["path"] for e in files if sha256(root / e["path"]) != e["sha256"]]
    if failed:
        raise RestoreError(f"{len(failed)} placed file(s) failed final verification: {failed[:5]}")
    return report


def verify_all(root: Path) -> dict:
    """Verify the whole registry. The private legacy/ reference copies are optional only when the entire legacy/
    folder is absent (a public clone); if legacy/ exists, all of its registered files are required."""
    registry = read_registry(root)
    optional = [r for r in registry if r.startswith("legacy/")] if not (root / "legacy").exists() else []
    required = {r: d for r, d in registry.items() if r not in optional}
    missing = [r for r in required if not (root / r).is_file()]
    altered = [r for r in required if (root / r).is_file() and sha256(root / r) != required[r]]
    return {"registered": len(registry), "verified": len(required) - len(missing) - len(altered),
            "optional_absent": optional, "missing": missing, "altered": altered}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("archive", nargs="?", type=Path)
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--dry-run", action="store_true", help="check everything, write nothing")
    ap.add_argument("--force", action="store_true", help="replace existing files that differ from the release")
    ap.add_argument("--verify-only", action="store_true", help="verify the whole checksum registry and exit")
    a = ap.parse_args(argv)
    root = a.project_root.resolve()
    try:
        if a.verify_only:
            v = verify_all(root)
            print(f"Registry: {v['registered']} files | verified {v['verified']} | missing {len(v['missing'])} | "
                  f"altered {len(v['altered'])} | private legacy copies not present (optional): {len(v['optional_absent'])}")
            for label in ("missing", "altered"):
                for r in v[label][:20]:
                    print(f"  {label}: {r}")
            return 0 if not v["altered"] and not v["missing"] else 1
        if a.archive is None:
            ap.error("an archive path is required (or use --verify-only)")
        r = restore(a.archive.resolve(), root, a.dry_run, a.force)
        if a.dry_run:
            print(f"Dry run {r['archive']}: {r['to_write']} file(s) would be written, {r['already_identical']} already "
                  f"identical; all checks passed. Nothing was written.")
        else:
            print(f"Restored {r['archive']}: {r['to_write']} file(s) written, {r['already_identical']} already identical, "
                  f"{r['replaced']} replaced; all {r['listed']} files verified against RELEASE_MANIFEST.json and "
                  "docs/CHECKSUMS.sha256.")
        return 0
    except RestoreError as e:
        print(f"RESTORE STOPPED: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
