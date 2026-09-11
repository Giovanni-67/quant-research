"""Atomic publication and exact artifact verification, for one local worker."""
import json
import shutil
from uuid import uuid4
from pathlib import Path

from .serialization import canonical, digest


def publish(root: Path, identity: str, artifacts: dict[str, bytes]) -> Path:
    if not artifacts or "checksums.json" in artifacts:
        raise ValueError("invalid artifact set")
    if any(Path(name).name != name or name in (".", "..") for name in artifacts):
        raise ValueError("artifacts must have plain filenames")
    if not identity or any(c not in "0123456789abcdef" for c in identity):
        raise ValueError("identity must be hexadecimal")
    root.mkdir(parents=True, exist_ok=True)
    final = root / identity
    checksums = {name: digest(data) for name, data in sorted(artifacts.items())}
    expected = {**artifacts, "checksums.json": canonical(checksums).encode()}
    if final.exists():
        # Compare against THIS computation, not merely the saved checksum file.
        if {p.name for p in final.iterdir()} != set(expected):
            raise ValueError("existing bundle has an incomplete or unexpected artifact set")
        if any((final / name).read_bytes() != payload for name, payload in expected.items()):
            raise ValueError("existing bundle differs from this computation or failed integrity check")
        return final
    # TemporaryDirectory applies private Windows ACLs; those survive a rename and
    # can make published output unreadable by the user's other local processes.
    # A normal directory inherits this workspace's existing permissions instead.
    staged = root / f".staging-{uuid4().hex}"
    staged.mkdir()
    try:
        for name, payload in expected.items():
            (staged / name).write_bytes(payload)
        # Rename on the same filesystem. A failure never leaves a partial final bundle.
        staged.rename(final)
    finally:
        if staged.exists():
            if staged.resolve().parent != root.resolve():
                raise RuntimeError("refusing cleanup outside the output root")
            shutil.rmtree(staged)
    return final


def verify(directory: Path, required: set[str]) -> None:
    try:
        checksums = json.loads((directory / "checksums.json").read_text(encoding="utf-8"))
        if not isinstance(checksums, dict) or set(checksums) != required:
            raise ValueError("unexpected checksum manifest")
        if {p.name for p in directory.iterdir()} != required | {"checksums.json"}:
            raise ValueError("unexpected artifact set")
        for name in required:
            if digest((directory / name).read_bytes()) != checksums[name]:
                raise ValueError(f"integrity check failed: {name}")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"incomplete or unreadable bundle: {exc}") from exc
