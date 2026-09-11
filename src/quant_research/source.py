from pathlib import Path

from .serialization import canonical, digest


def source_snapshot() -> tuple[dict[str, str], str]:
    root = Path(__file__).parent
    contents = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
                for p in sorted(root.rglob("*"))
                if p.is_file() and p.suffix in (".py", ".json", ".csv")}
    return contents, digest(canonical(contents).encode())


# Fail on source edits in a running process rather than falsely describing loaded code.
_LOADED_SNAPSHOT, _LOADED_DIGEST = source_snapshot()


def checked_source() -> tuple[dict[str, str], str]:
    if source_snapshot()[1] != _LOADED_DIGEST:
        raise ValueError("package source changed in this process; restart before computing/saving")
    return dict(_LOADED_SNAPSHOT), _LOADED_DIGEST
