from pathlib import Path

def fetch_log_data(path: str, max_bytes: int = 200_000) -> str:
    """Fetch a local log file as text (bounded).

    This is intentionally scoped to files within the repository root to avoid arbitrary host reads.
    """
    # We assume this file is in src/tools/, so repo root is two levels up
    repo_root = Path(__file__).resolve().parents[2]
    target = (repo_root / path).resolve()
    if repo_root not in target.parents and target != repo_root:
        raise ValueError(f"Path must be within repo root: {path}")
    if not target.is_file():
        raise FileNotFoundError(str(target))
    data = target.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def get_available_files() -> list[str]:
    """Return the available sample log file paths (repo-relative)."""
    # We assume this file is in src/tools/, so repo root is two levels up
    repo_root = Path(__file__).resolve().parents[2]
    sample_dir = (repo_root / "src" / "optimize_agent" / "sample_logs").resolve()
    if repo_root not in sample_dir.parents and sample_dir != repo_root:
        raise ValueError("Sample log directory must be within repo root.")
    if not sample_dir.is_dir():
        raise FileNotFoundError(str(sample_dir))

    files = sorted(p.name for p in sample_dir.glob("*.log") if p.is_file())
    return [f"src/optimize_agent/sample_logs/{name}" for name in files]
