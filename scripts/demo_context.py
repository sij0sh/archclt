"""A cold agent recovers a reuse reason, evolves it and verifies without adoption."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from archctl.core.io import write_json


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="archclt-context-demo-") as directory:
        root = Path(directory)
        source = root / "src/api/batching.py"
        source.parent.mkdir(parents=True)
        source.write_text("request_batch = []\ndef batch(item):\n    request_batch.append(item)\n")
        worker = root / "src/worker/jobs.py"
        worker.parent.mkdir()
        worker.write_text("def work(): return 'job'\n")
        def cli(*args):
            result = subprocess.run([sys.executable, "-m", "archctl", "--root", str(root), *args],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(result.stdout + result.stderr)
            return json.loads(result.stdout)
        note = {"schema_version": "archctl.memory.v1", "id": "batch-lifetime",
            "statement": "API batching has request-scoped mutable state",
            "rationale": "Overlapping worker jobs have a different lifetime; extract a pure operation before reuse.",
            "origin": "agent_inferred", "references": ["conversation:demo/task-1"],
            "paths": ["src/api/batching.py"], "topics": ["batching", "concurrency"]}
        write_json(root / "reason.json", note)
        cli("memory", "record", "--input", "reason.json")
        cold = cli("context", "Reuse batching for worker concurrency", "--paths", "src/worker/jobs.py")
        assert cold["memories"][0]["origin"] == "agent_inferred"
        assert cold["memories"][0]["references"] == ["conversation:demo/task-1"]
        source.write_text("def batch(items): return tuple(items)\n")
        stale = cli("context", "Reuse batching")
        assert stale["memories"][0]["freshness"]["status"] == "stale"
        write_json(root / "new-reason.json", {**note, "id": "pure-batching", "origin": "agent_chosen",
            "statement": "Batching is now a pure operation usable by workers",
            "rationale": "The extracted function no longer retains request state; concurrency checks exercise overlapping callers.",
            "supersedes": ["batch-lifetime"], "references": ["conversation:demo/task-2"]})
        cli("memory", "record", "--input", "new-reason.json")
        execution = cli("verify", "run", "--task", "Batching concurrency", "--paths", "src/api/batching.py",
            "--command", json.dumps([sys.executable, "-c",
                "import sys; sys.path.insert(0, 'src'); from api.batching import batch; "
                "from concurrent.futures import ThreadPoolExecutor; "
                "pool=ThreadPoolExecutor(4); assert list(pool.map(batch, [[1], [2], [3], [4]])) == [(1,), (2,), (3,), (4,)]; pool.shutdown()" ]))
        final = cli("context", "Batching concurrency")
        assert len(final["memories"]) == 2
        assert final["executions"][0]["result"]["status"] == "passed"
        assert not (root / "architecture/model.yaml").exists()
        assert not (root / ".git").exists()
        print(json.dumps({"cold_start_reason_recovered": True, "stale_reason_flagged": True,
            "replacement_preserves_history": True, "verification": execution["result"]["status"],
            "applicability": execution["applicability"]["status"], "architecture_adoption_required": False,
            "limitations_retained": bool(final["limitations"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
