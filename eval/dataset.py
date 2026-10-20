import json
from pathlib import Path
from typing import List
from eval.models import BenchmarkTask

_TASKS_DIR = Path(__file__).parent / "tasks"

def get_golden_dataset() -> List[BenchmarkTask]:
    """
    Load the benchmark evaluation dataset.
    Discovers tasks defined in eval/tasks/ if present, loading task metadata,
    initial fixture files, and verification scripts.
    """
    tasks: List[BenchmarkTask] = []
    
    if _TASKS_DIR.is_dir():
        for task_dir in sorted(_TASKS_DIR.iterdir()):
            if not task_dir.is_dir():
                continue
            task_json = task_dir / "task.json"
            verify_file = task_dir / "verify.py"
            if not task_json.is_file() or not verify_file.is_file():
                continue
                
            try:
                meta = json.loads(task_json.read_text(encoding="utf-8"))
                initial_files = {}
                fixture_dir = task_dir / "fixture"
                if fixture_dir.is_dir():
                    for fpath in fixture_dir.rglob("*"):
                        if fpath.is_file():
                            rel_path = fpath.relative_to(fixture_dir).as_posix()
                            initial_files[rel_path] = fpath.read_text(encoding="utf-8")
                            
                verification_script = verify_file.read_text(encoding="utf-8")
                
                tasks.append(
                    BenchmarkTask(
                        id=meta["id"],
                        goal=meta["goal"],
                        category=meta.get("category", "feature"),
                        initial_files=initial_files,
                        verification_script=verification_script
                    )
                )
            except Exception:
                continue

    if tasks:
        return tasks

    # Fallback built-in definitions if tasks directory is absent
    return [
        BenchmarkTask(
            id="easy-01",
            goal="Write a Python function `add(a, b)` in `math_utils.py` that returns the sum of two numbers.",
            initial_files={},
            verification_script="""import sys
try:
    from math_utils import add
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
        ),
        BenchmarkTask(
            id="easy-02",
            goal="Fix the bug in `calculator.py`. The `multiply` function currently adds instead of multiplying.",
            initial_files={
                "calculator.py": "def multiply(a: float, b: float) -> float:\n    return a + b\n"
            },
            verification_script="""import sys
try:
    from calculator import multiply
    assert multiply(3, 4) == 12
    assert multiply(0, 5) == 0
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
        )
    ]
