"""Opt-in CI helper: verify the official archive and extract only its native CLI."""

import hashlib
import io
import tarfile
from pathlib import Path
from urllib.request import urlopen

URL = "https://github.com/storytold/filmcraft/releases/download/v0.7.2/filmcraft-0.7.2-linux-x86_64.tar.gz"
ARCHIVE_SHA256 = "4171c4bf5f57fd29475655f8a6df4719feda8c8f3ed95b2475d8dc112ad3be86"
CLI_SHA256 = "33129b52859e83106b027d41fcbc65d994bb0b5db32cf1ad2b3187bd547c498c"


def main():
    destination = Path("runtime/filmcraft-cli")
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("runtime/filmcraft-cli must be a new file")
    with urlopen(URL, timeout=120) as response:
        archive = response.read(80 * 1024 * 1024 + 1)
    if hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("official native archive SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        member = bundle.getmember("filmcraft-0.7.2-linux-x86_64/bin/filmcraft-cli")
        if not member.isfile() or member.size > 80 * 1024 * 1024:
            raise RuntimeError("unexpected official native CLI archive member")
        stream = bundle.extractfile(member)
        if stream is None:
            raise RuntimeError("native CLI missing from verified archive")
        binary = stream.read(member.size + 1)
    if hashlib.sha256(binary).hexdigest() != CLI_SHA256:
        raise RuntimeError("official native CLI SHA-256 mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(binary)
    destination.chmod(0o755)
    print("Official FilmCraft CLI archive and binary SHA-256 verified.")


if __name__ == "__main__":
    main()
