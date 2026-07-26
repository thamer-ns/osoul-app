from __future__ import annotations

import base64
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK_DIR = ROOT / "scripts" / "warning_patch_chunks"


def main() -> None:
    parts = sorted(CHUNK_DIR.glob("part*.txt"))
    if len(parts) != 7:
        raise RuntimeError(f"expected 7 patch chunks, found {len(parts)}")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in parts)
    patch = zlib.decompress(base64.b64decode(encoded, validate=True))
    subprocess.run(
        ["git", "apply", "--whitespace=fix", "-"],
        cwd=ROOT,
        input=patch,
        check=True,
    )


if __name__ == "__main__":
    main()
