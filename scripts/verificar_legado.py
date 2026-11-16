"""Verifica preservação dos paths e blobs históricos sem executar experimentos."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "desenvolvimento" / "legado-inventario.json"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tracked = {}
    for record in git("ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _, blob, stage = metadata.decode("ascii").split()
        if stage != "0":
            print("ERRO: conflito não resolvido no índice.", file=sys.stderr)
            return 1
        tracked[raw_path.decode("utf-8")] = blob

    errors = []
    paths = [item["path"] for item in manifest["files"]]
    for item in manifest["files"]:
        if tracked.get(item["path"]) != item["git_blob"]:
            errors.append(f"Blob removido ou alterado: {item['path']}")

    # Git considera as regras de normalização da plataforma ao comparar o worktree.
    changed = git("diff-files", "--name-only", "-z", "--", *paths)
    for raw_path in changed.split(b"\0"):
        if raw_path:
            errors.append(f"Alteração local: {raw_path.decode('utf-8')}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: {len(paths)} arquivos históricos preservados no índice e no worktree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
