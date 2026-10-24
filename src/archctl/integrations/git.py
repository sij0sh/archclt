"""Git task scope shared by ordinary context and the explicit gate workflow."""

from pathlib import Path
import subprocess

from archctl.core.io import InputError


def git(root: Path, *arguments: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, check=False)
    if result.returncode:
        raise InputError(f"Git {' '.join(arguments[:2])} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="strict").strip()


def changed_paths(root: Path, base: str) -> list[str]:
    if not base or base.startswith("-"):
        raise InputError("--base-ref must name a Git revision")
    raw = git(root, "diff", "--relative", "--name-only", "--no-renames", "-z", base, "--", ".", binary=True)
    raw += git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".", binary=True)
    # Preserve the existing scope contract, including nested repository roots.
    return sorted({p.decode("utf-8") for p in raw.split(b"\0") if p
                   and not p.startswith((b".archctl/", b".briefcase/"))})
