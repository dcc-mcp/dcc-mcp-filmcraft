"""Offline extraction of one exact, already downloaded official FilmCraft CLI.

No network API or dependency installer is invoked. The CLI entry point always
uses the reviewed release hashes; alternate hashes exist only on the pure byte
validator so ordinary tests can use clearly synthetic, non-vendor TAR content.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path

VERSION = "0.12.0"
ARCHIVE_SHA256 = "ddff0a2ec0d89e5e9e65644ed724b5b79959600b1602fd4ea6653b5a54bf88fd"
CLI_SHA256 = "05982fe44214f6174ffb54166d100e2362cf90811f2480235f3ecbaa0a3a75c2"
MEMBER = f"filmcraft-{VERSION}-linux-x86_64/bin/filmcraft-cli"
MAX_BYTES = 80 * 1024 * 1024


def verify_tar(raw, *, archive_sha=ARCHIVE_SHA256, cli_sha=CLI_SHA256, max_bytes=MAX_BYTES):
    if not raw or len(raw) > max_bytes or hashlib.sha256(raw).hexdigest() != archive_sha:
        raise ValueError("bounded official archive SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        matches = [member for member in archive.getmembers() if member.name == MEMBER]
        if len(matches) != 1:
            raise ValueError("exact native CLI member must occur once")
        member = matches[0]
        if not member.isfile() or member.issym() or member.islnk() or member.sparse or not 0 < member.size <= max_bytes:
            raise ValueError("bounded ordinary CLI archive member required; links are refused")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("CLI member missing")
        with source:
            binary = source.read(member.size + 1)
        if len(binary) != member.size or hashlib.sha256(binary).hexdigest() != cli_sha:
            raise ValueError("official extracted CLI SHA-256 mismatch")
    return binary


def read_archive(path):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
        raise ValueError("archive must be a bounded regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("archive identity changed before read")
        raw = source.read(MAX_BYTES + 1)
        after = os.fstat(source.fileno())
    current = path.lstat()
    keys = [(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) for info in (before, opened, after, current)]
    if len(set(keys)) != 1 or len(raw) != opened.st_size:
        raise ValueError("archive identity or bytes changed while reading")
    return raw


def write_new(path, binary):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(binary)
        output.flush()
        os.fsync(output.fileno())
    path.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("native CLI output must be a new file")
    binary = verify_tar(read_archive(args.archive))
    write_new(args.output, binary)
    print(
        json.dumps(
            {
                "version": VERSION,
                "archive_sha256": ARCHIVE_SHA256,
                "cli_sha256": CLI_SHA256,
                "cli_bytes": len(binary),
                "exact_member": MEMBER,
                "network_access": False,
            }
        )
    )


if __name__ == "__main__":
    main()
