from __future__ import annotations

import base64
import hashlib
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK_DIR = ROOT / "scripts" / "warning_patch_chunks"
PARTS = [
    "part01.txt",
    "part02.txt",
    "part03.txt",
    "part04.txt",
    "part05a.txt",
    "part05b.txt",
    "part05c.txt",
    "part05d.txt",
    "part06.txt",
    "part07.txt",
]
EXPECTED_ENCODED_SHA256 = "6cceaf0f845e4e022604e4eef054ad1b04b0678a32fffe547353920173f29e9a"
EXPECTED_COMPRESSED_SHA256 = "632da48fee4b7c74839d4d85b0fe5cb0c89b3b5f5a7c6e3b79867d9b60887c0b"
EXPECTED_PATCH_SHA256 = "41dfefc45a4d9cf9f2b69a20bb900799a84e7da36d8ffce316b77e217c1cdec7"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    encoded = "".join(
        (CHUNK_DIR / name).read_text(encoding="ascii").strip()
        for name in PARTS
    ).encode("ascii")
    if _sha256(encoded) != EXPECTED_ENCODED_SHA256:
        raise RuntimeError("warning patch base64 integrity check failed")

    compressed = base64.b64decode(encoded, validate=True)
    if _sha256(compressed) != EXPECTED_COMPRESSED_SHA256:
        raise RuntimeError("warning patch compressed integrity check failed")

    patch = zlib.decompress(compressed)
    if _sha256(patch) != EXPECTED_PATCH_SHA256:
        raise RuntimeError("warning patch content integrity check failed")

    subprocess.run(
        ["git", "apply", "--whitespace=fix", "-"],
        cwd=ROOT,
        input=patch,
        check=True,
    )


if __name__ == "__main__":
    main()
