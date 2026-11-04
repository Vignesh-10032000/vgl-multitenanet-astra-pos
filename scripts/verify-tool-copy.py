"""Verify a tool-directory copy before the separate migration removes its source."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys


def files_under(root: Path) -> dict[str, Path]:
    """Enumerate ordinary files without following directory links."""
    return {
        str((Path(directory) / name).relative_to(root)): Path(directory) / name
        for directory, _, names in os.walk(root, followlinks=False)
        for name in names
    }


def digest(path: Path) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def main() -> None:
    source, destination = (Path(value).resolve() for value in sys.argv[1:])
    original = files_under(source)
    copied = files_under(destination)
    if original.keys() != copied.keys():
        raise ValueError("Source and destination file sets differ; retain both copies")

    def verify(name: str) -> int:
        size = original[name].stat().st_size
        if size != copied[name].stat().st_size or digest(original[name]) != digest(copied[name]):
            raise ValueError("Copy checksum mismatch; retain source")
        return size

    with ThreadPoolExecutor(max_workers=4) as pool:
        total = sum(pool.map(verify, original, chunksize=100))
    print(json.dumps({"files": len(original), "bytes": total}))


if __name__ == "__main__":
    main()
