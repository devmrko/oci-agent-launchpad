"""Internal unittest worker. Run trusted repository code only."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest


def main():
    path, case, output = sys.argv[1:]
    path = Path(path).resolve()
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("_evidence_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cls, method = case.split(".")
    test_class = getattr(module, cls)
    if not issubclass(test_class, unittest.TestCase):
        raise ValueError("Mapped class must inherit unittest.TestCase")
    result = unittest.TestResult()
    unittest.TestSuite([test_class(method)]).run(result)
    counts = {"run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped),
              "expected_failures": len(result.expectedFailures),
              "unexpected_successes": len(result.unexpectedSuccesses)}
    Path(output).write_text(json.dumps(counts))


if __name__ == "__main__":
    main()
