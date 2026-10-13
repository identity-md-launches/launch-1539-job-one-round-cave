#!/usr/bin/env python3
"""Stream-check a HANDOFF.json v1 ZIP and print a receipt without extraction."""

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import zipfile


MANIFEST = "HANDOFF.json"
CHUNK = 64 * 1024
HEX = re.compile(r"[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 66 * 1024 * 1024
    payload_bytes: int = 64 * 1024 * 1024
    manifest_bytes: int = 512 * 1024
    metadata_bytes: int = 512 * 1024
    files: int = 1000

    def validate(self):
        if any(type(v) is not int or v < 1 for v in vars(self).values()):
            raise ValueError("limits must be positive integers")


def safe_name(name):
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(p in ("", ".", "..") for p in name.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError("unsafe archive path: " + repr(name))
    return name


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + repr(key))
        result[key] = value
    return result


def read_exact(handle, size):
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated ZIP metadata")
    return data


def preflight(handle, size, limits):
    """Bound and validate metadata BEFORE ZipFile allocates its entry objects.

    Accept classic single-disk stored ZIPs, including UTF-8 names, comments and
    ordinary extra fields. Reject ZIP64, descriptors, prefixes, trailing data,
    overlapping entries and inconsistent local/central headers.
    """
    if size < 22:
        raise ValueError("truncated ZIP archive")
    handle.seek(max(0, size - 65557))
    tail = handle.read(65557)
    pos = tail.rfind(b"PK\x05\x06")
    if pos < 0 or len(tail) - pos < 22:
        raise ValueError("missing ZIP end record")
    signature, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment = (
        struct.unpack("<4s4H2IH", tail[pos:pos + 22]))
    if pos + 22 + comment != len(tail):
        raise ValueError("trailing data or malformed ZIP comment")
    if disk or cd_disk or disk_count != count:
        raise ValueError("multi-disk ZIP is unsupported")
    if count == 65535 or cd_size == 0xffffffff or cd_offset == 0xffffffff:
        raise ValueError("ZIP64 is unsupported")
    if not 2 <= count <= limits.files + 1:
        raise ValueError("archive entry count exceeds limits or is empty")
    if cd_size > limits.metadata_bytes:
        raise ValueError("central directory exceeds metadata limit")
    end_offset = size - len(tail) + pos
    if cd_offset + cd_size != end_offset:
        raise ValueError("invalid central directory extent")
    handle.seek(cd_offset)
    central = io.BytesIO(read_exact(handle, cd_size))
    entries = {}
    spans = []
    payload_size = 0
    for _ in range(count):
        fields = struct.unpack("<4s6H3I5H2I", read_exact(central, 46))
        (sig, made, needed, flags, method, mtime, mdate, crc, compressed,
         expanded, name_len, extra_len, comment_len, entry_disk, internal,
         external, offset) = fields
        if sig != b"PK\x01\x02" or not name_len:
            raise ValueError("malformed central directory entry")
        raw_name = read_exact(central, name_len)
        name = safe_name(raw_name.decode("utf-8" if flags & 0x800 else "cp437"))
        read_exact(central, extra_len + comment_len)
        if name in entries:
            raise ValueError("duplicate archive path: " + name)
        if needed > 20 or entry_disk or offset == 0xffffffff:
            raise ValueError("unsupported ZIP version, ZIP64 or disk")
        if flags & ~0x800 or method != zipfile.ZIP_STORED or compressed != expanded:
            raise ValueError("only unencrypted stored entries without descriptors supported")
        mode = external >> 16
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or external & 0x10:
            raise ValueError("only regular file entries supported")
        if name == MANIFEST:
            if expanded > limits.manifest_bytes:
                raise ValueError("manifest exceeds size limit")
        else:
            payload_size += expanded
            if payload_size > limits.payload_bytes:
                raise ValueError("payload exceeds size limit")
        if offset + 30 > cd_offset:
            raise ValueError("invalid local header offset")
        handle.seek(offset)
        local = struct.unpack("<4s5H3I2H", read_exact(handle, 30))
        (lsig, lneeded, lflags, lmethod, ltime, ldate, lcrc, lcompressed,
         lexpanded, lname_len, lextra_len) = local
        if (lsig != b"PK\x03\x04" or
                (lneeded, lflags, lmethod, ltime, ldate, lcrc, lcompressed, lexpanded)
                != (needed, flags, method, mtime, mdate, crc, compressed, expanded)):
            raise ValueError("local and central headers disagree")
        if read_exact(handle, lname_len) != raw_name:
            raise ValueError("local and central paths disagree")
        start = offset + 30 + lname_len + lextra_len
        stop = start + compressed
        if stop > cd_offset:
            raise ValueError("entry extends into central directory")
        spans.append((offset, stop))
        entries[name] = expanded
    if central.tell() != cd_size or MANIFEST not in entries:
        raise ValueError("extra central metadata or missing manifest")
    previous = 0
    for start, stop in sorted(spans):
        if start != previous:
            raise ValueError("overlapping entries, prefix or unlisted local data")
        previous = stop
    if previous != cd_offset:
        raise ValueError("unlisted data before central directory")
    return entries


def parse_manifest(data, entries):
    # UTF-8 is the producer's encoding; reject non-standard NaN/Infinity too.
    def invalid_constant(value):
        raise ValueError("non-standard JSON constant: " + value)

    manifest = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=invalid_constant)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"version", "algorithm", "files"}
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or manifest["algorithm"] != "sha256"
            or not isinstance(manifest["files"], list)):
        raise ValueError("unsupported HANDOFF manifest")
    declared = {}
    for item in manifest["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise ValueError("invalid manifest file entry")
        name = safe_name(item["path"])
        if name == MANIFEST or name in declared or name not in entries:
            raise ValueError("duplicate, missing or reserved declared path")
        if type(item["bytes"]) is not int or item["bytes"] != entries[name]:
            raise ValueError("manifest byte count differs from ZIP: " + name)
        if not isinstance(item["sha256"], str) or not HEX.fullmatch(item["sha256"]):
            raise ValueError("invalid file SHA-256: " + name)
        # v1 producer writes lowercase; accept only that canonical digest form.
        if item["sha256"] != item["sha256"].lower():
            raise ValueError("file SHA-256 must be lowercase")
        declared[name] = item
    if set(declared) != set(entries) - {MANIFEST}:
        raise ValueError("missing or unlisted payload files")
    return declared


def inspect_stream(handle, limits=None, expected=None):
    """Inspect a seekable binary stream. Never extract or execute its payload."""
    limits = limits or Limits()
    limits.validate()
    if expected is not None and (not isinstance(expected, str) or not HEX.fullmatch(expected)):
        raise ValueError("trusted SHA-256 must contain exactly 64 hexadecimal digits")
    handle.seek(0, 2)
    size = handle.tell()
    if size > limits.archive_bytes:
        raise ValueError("archive exceeds size limit")
    entries = preflight(handle, size, limits)
    handle.seek(0)
    hasher = hashlib.sha256()
    remaining = size
    while remaining:
        block = handle.read(min(CHUNK, remaining))
        if not block:
            raise ValueError("archive changed or was truncated during inspection")
        remaining -= len(block)
        hasher.update(block)
    archive_hash = hasher.hexdigest()
    if expected is not None and archive_hash != expected.lower():
        raise ValueError("archive SHA-256 differs from trusted digest")
    handle.seek(0)
    with zipfile.ZipFile(handle) as archive:
        infos = archive.infolist()
        if len(infos) != len(entries) or {i.filename: i.file_size for i in infos} != entries:
            raise ValueError("ZIP parser and preflight disagree")
        with archive.open(MANIFEST) as source:
            manifest = source.read(limits.manifest_bytes + 1)
        if len(manifest) > limits.manifest_bytes:
            raise ValueError("manifest exceeds size limit")
        declared = parse_manifest(manifest, entries)
        for name, item in sorted(declared.items()):
            hasher = hashlib.sha256()
            total = 0
            with archive.open(name) as source:
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    total += len(block)
                    if total > item["bytes"]:
                        raise ValueError("entry grew beyond declared size")
                    hasher.update(block)
            if total != item["bytes"] or hasher.hexdigest() != item["sha256"]:
                raise ValueError("integrity mismatch: " + name)
    return {"format": "handoff-inspection-v1", "verified": True,
            "archive_sha256": archive_hash, "archive_bytes": size,
            "trusted_digest_matched": expected is not None,
            "file_count": len(declared), "payload_bytes": sum(entries[n] for n in declared),
            "files": [declared[n] for n in sorted(declared)], "limits": vars(limits)}


def inspect_path(raw, limits=None, expected=None):
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("use a relative workspace path without '..'")
    current = Path.cwd()
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlinks are not allowed")
    fd = os.open(current, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("only regular workspace files are allowed")
        receipt = inspect_stream(handle, limits, expected)
        after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("archive changed during inspection")
    return receipt


def demo():
    # Inspect the actual inherited handoff, without writes or payload execution.
    receipt = inspect_path("line-2/handoff.zip")
    confirmed = inspect_path("line-2/handoff.zip", expected=receipt["archive_sha256"])
    if not confirmed["trusted_digest_matched"]:
        raise ValueError("digest comparison failed")
    rejected = []
    for label, limits, expected in (
            ("archive_budget", Limits(archive_bytes=receipt["archive_bytes"] - 1), None),
            ("payload_budget", Limits(payload_bytes=receipt["payload_bytes"] - 1), None),
            ("digest_mismatch", Limits(), "f" * 64)):
        try:
            inspect_path("line-2/handoff.zip", limits, expected)
        except ValueError:
            rejected.append(label)
        else:
            raise ValueError("demo failed to reject " + label)
    return {"demo": "actual inherited handoff", "receipt": receipt,
            "rejected": rejected,
            "note": "The demo calculates its own digest; this does not establish authenticity."}


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="inspect the real inherited bundle and exercise refusals")
    check = commands.add_parser("inspect", help="verify a workspace ZIP; emit JSON to stdout")
    check.add_argument("archive")
    check.add_argument("--sha256", help="independently trusted archive SHA-256")
    check.add_argument("--max-archive-bytes", type=positive, default=Limits.archive_bytes)
    check.add_argument("--max-payload-bytes", type=positive, default=Limits.payload_bytes)
    check.add_argument("--max-manifest-bytes", type=positive, default=Limits.manifest_bytes)
    check.add_argument("--max-metadata-bytes", type=positive, default=Limits.metadata_bytes)
    check.add_argument("--max-files", type=positive, default=Limits.files)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            result = demo()
        else:
            limits = Limits(args.max_archive_bytes, args.max_payload_bytes,
                            args.max_manifest_bytes, args.max_metadata_bytes, args.max_files)
            result = inspect_path(args.archive, limits, args.sha256)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError,
            zipfile.BadZipFile, EOFError, NotImplementedError, struct.error) as error:
        print("handoff-inspect: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
