import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
stream = io.StringIO()
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
report = {"executed_at": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0], "tests_run": result.testsRun, "successful": result.wasSuccessful(), "failures": len(result.failures), "errors": len(result.errors), "log": stream.getvalue()}
path = ROOT / "examples/test-results.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(stream.getvalue())
raise SystemExit(not result.wasSuccessful())
