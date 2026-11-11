"""Build an allowlisted source ZIP and hash manifest, never packaging the parent workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    ".gitignore",
    ".gitattributes",
}
DIRECTORIES = {"src", "tests", "examples", "docs", "tools", ".github"}
EXTENSIONS = {".py", ".toml", ".cl", ".md", ".svg", ".yml", ".yaml"}
SECRET_PATTERN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", ".git"}


def collect_files() -> list[Path]:
    result = [ROOT / name for name in ROOT_FILES]
    for folder in sorted(DIRECTORIES):
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if path.is_file() and not set(relative.parts) & EXCLUDED_PARTS and path.suffix in EXTENSIONS:
                result.append(path)
    result.sort(key=lambda path: path.relative_to(ROOT).as_posix())
    for path in result:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Missing or unsafe source path: {path.name}")
        text = path.read_text(encoding="utf-8")
        if SECRET_PATTERN.search(text):
            raise ValueError(f"Credential-like content in {path.relative_to(ROOT)}")
    return result


def package(output_dir: Path) -> dict[str, object]:
    files = collect_files()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "closure-lab-v0.1.0.zip"
    entries = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in files
    ]
    manifest = {
        "project": "closure-lab",
        "version": "0.1.0",
        "files": entries,
        "policy": "New implementation only; no original exercises, binaries, caches or credentials.",
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            info = zipfile.ZipInfo("closure-lab/" + path.relative_to(ROOT).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("closure-lab/RELEASE-MANIFEST.json")
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, manifest_bytes)
    with zipfile.ZipFile(archive) as bundle:
        corrupt = bundle.testzip()
        if corrupt is not None:
            raise ValueError(f"Corrupt archive entry: {corrupt}")
        for entry in entries:
            data = bundle.read("closure-lab/" + str(entry["path"]))
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError(f"Archive hash mismatch: {entry['path']}")
        if len(bundle.namelist()) != len(entries) + 1:
            raise ValueError("Unexpected archive contents")
    result = {
        "archive": archive.name,
        "source_files": len(files),
        "zip_integrity": "passed",
        "entry_hashes": "passed",
        "credential_pattern_scan": "passed",
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    (output_dir / "closure-lab-release-manifest.json").write_bytes(manifest_bytes)
    (output_dir / "closure-lab-release-check.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    options = parser.parse_args()
    print(json.dumps(package(options.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
