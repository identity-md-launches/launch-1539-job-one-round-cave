#!/usr/bin/env python3
"""Reproducible SHA-256 ZIP handoffs; no extraction, network, or external files."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

VERSION = 1
MANIFEST = "HANDOFF.json"
MAX_FILES = 1000
MAX_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE = MAX_BYTES + 2 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    parts = name.split("/")
    if (not name or "\\" in name or ":" in name or
            any(p in ("", ".", "..") for p in parts) or
            any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError("unsafe archive path: " + repr(name))
    return name


def workspace_path(raw, must_exist=True):
    """Accept only relative paths inside cwd, without following any symlinks."""
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("use a relative workspace path without '..'")
    current = Path.cwd()
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlinks are not allowed: " + str(path))
    if must_exist and not current.exists():
        raise ValueError("path does not exist: " + str(path))
    return current


def regular_bytes(path, limit):
    # O_NOFOLLOW closes the final-component symlink race on platforms supporting it.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("only regular files are allowed")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("size limit exceeded")
    return data


def collect(raw, output):
    root = workspace_path(raw)
    if not root.is_dir():
        raise ValueError("source must be a directory")
    files = {}
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        # Refuse symlinks instead of quietly packaging an incomplete handoff.
        for name in dirs + names:
            if (Path(directory) / name).is_symlink():
                raise ValueError("source contains a symlink: " + name)
        for name in sorted(names):
            path = Path(directory) / name
            if path == output:
                raise ValueError("output must be outside source directory")
            relative = safe_name(path.relative_to(root).as_posix())
            if relative == MANIFEST:
                raise ValueError(MANIFEST + " is reserved")
            if len(files) >= MAX_FILES:
                raise ValueError("too many files")
            data = regular_bytes(path, MAX_BYTES - total)
            total += len(data)
            files[relative] = data
    if not files:
        raise ValueError("source is empty")
    return files


def build(files):
    if not files or len(files) > MAX_FILES:
        raise ValueError("invalid file count")
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("size limit exceeded")
    entries = []
    for name in sorted(files):
        safe_name(name)
        if name == MANIFEST:
            raise ValueError("reserved manifest path")
        entries.append({"path": name, "bytes": len(files[name]),
                        "sha256": digest(files[name])})
    manifest = {"version": VERSION, "algorithm": "sha256", "files": entries}
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in [(MANIFEST, payload)] + sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_STORED
            archive.writestr(entry, data)
    return result.getvalue()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def verify(data, expected=None):
    if len(data) > MAX_ARCHIVE:
        raise ValueError("archive too large")
    actual = digest(data)
    if expected is not None and expected.lower() != actual:
        raise ValueError("archive SHA-256 differs from trusted digest")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if not 2 <= len(infos) <= MAX_FILES + 1:
            raise ValueError("invalid archive entry count")
        names = [safe_name(info.filename) for info in infos]
        if len(set(names)) != len(names) or MANIFEST not in names:
            raise ValueError("duplicate entries or missing manifest")
        total = 0
        for info in infos:
            mode = info.external_attr >> 16
            if (info.is_dir() or stat.S_ISLNK(mode) or
                    info.flag_bits & 1 or info.compress_type != zipfile.ZIP_STORED):
                raise ValueError("only unencrypted, stored regular entries supported")
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("nonregular archive entry")
            total += info.file_size
            if total > MAX_ARCHIVE:
                raise ValueError("archive content too large")
        manifest_data = archive.read(MANIFEST)
        if len(manifest_data) > 512 * 1024:
            raise ValueError("manifest too large")
        manifest = json.loads(manifest_data, object_pairs_hook=unique_object)
        if (not isinstance(manifest, dict) or
                set(manifest) != {"version", "algorithm", "files"} or
                type(manifest["version"]) is not int or
                manifest["version"] != VERSION or manifest["algorithm"] != "sha256" or
                not isinstance(manifest["files"], list)):
            raise ValueError("unsupported manifest")
        declared = set()
        total = 0
        for item in manifest["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
                raise ValueError("invalid manifest entry")
            name = item["path"]
            if not isinstance(name, str):
                raise ValueError("invalid path type")
            safe_name(name)
            if name == MANIFEST or name in declared or name not in names:
                raise ValueError("duplicate, missing, or reserved declared path")
            declared.add(name)
            if type(item["bytes"]) is not int or item["bytes"] < 0:
                raise ValueError("invalid byte count")
            content = archive.read(name)
            total += len(content)
            if total > MAX_BYTES:
                raise ValueError("payload too large")
            if len(content) != item["bytes"] or digest(content) != item["sha256"]:
                raise ValueError("integrity mismatch: " + name)
        if declared != set(names) - {MANIFEST}:
            raise ValueError("archive has unlisted files")
    return {"verified": True, "files": len(declared), "bytes": total, "sha256": actual}


def demo():
    files = {"hello.py": b'print("handoff received")\n', "README.md": b"Run python3 hello.py\n"}
    packed = build(files)
    if packed != build(dict(reversed(list(files.items())))):
        raise ValueError("determinism check failed")
    result = verify(packed, digest(packed))
    changed = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(packed)) as original, zipfile.ZipFile(changed, "w") as altered:
        for entry in original.infolist():
            content = original.read(entry.filename)
            if entry.filename == "hello.py":
                content = b"changed\n"
            altered.writestr(entry, content)
    try:
        verify(changed.getvalue())
    except ValueError:
        result.update(deterministic=True, tampering_rejected=True)
        return result
    raise ValueError("tampering was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="in-memory reproducibility and tamper check")
    pack = commands.add_parser("pack", help="package a workspace directory")
    pack.add_argument("source")
    pack.add_argument("output", help="new ZIP path outside source, inside workspace")
    check = commands.add_parser("verify", help="check without extracting or executing")
    check.add_argument("archive")
    check.add_argument("--sha256", help="trusted digest obtained separately")
    args = parser.parse_args()
    try:
        if args.command == "demo":
            result = demo()
        elif args.command == "pack":
            output = workspace_path(args.output, must_exist=False)
            root = workspace_path(args.source)
            if output == root or root in output.parents:
                raise ValueError("output must be outside source directory")
            data = build(collect(args.source, output))
            result = verify(data)
            with output.open("xb") as handle:
                handle.write(data)
            result["output"] = args.output
        else:
            result = verify(regular_bytes(workspace_path(args.archive), MAX_ARCHIVE), args.sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile,
            UnicodeError, RecursionError, NotImplementedError) as error:
        print("handoff: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
