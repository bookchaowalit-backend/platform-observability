"""Tests for scripts/check_schema_pin.py and scripts/check_registry_alignment.py."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pin = _load("platform_schema_pin", "scripts/check_schema_pin.py")
align = _load("platform_registry_alignment", "scripts/check_registry_alignment.py")


class SchemaPinTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name) / "repo"
        (self.root / "schema").mkdir(parents=True)
        for relative in (pin.SCHEMA_RELATIVE, pin.PIN_RELATIVE):
            shutil.copyfile(ROOT / relative, self.root / relative)
        self.schema = self.root / pin.SCHEMA_RELATIVE
        self.pin_file = self.root / pin.PIN_RELATIVE

    def tearDown(self) -> None:
        self._temp.cleanup()

    def canonical_repo(self, content: bytes) -> Path:
        core = Path(self._temp.name) / "bookchaowalit-backend-core"
        (core / "contracts").mkdir(parents=True, exist_ok=True)
        (core / pin.CANONICAL_RELATIVE).write_bytes(content)
        return core

    def test_repository_schema_matches_pin(self) -> None:
        self.assertEqual(pin.validate(ROOT), [])

    def test_pin_matches_sha256sum_of_vendored_schema(self) -> None:
        digest = hashlib.sha256((ROOT / pin.SCHEMA_RELATIVE).read_bytes()).hexdigest()
        self.assertEqual(pin.read_pin(ROOT / pin.PIN_RELATIVE), (digest, None))

    def test_edited_schema_fails(self) -> None:
        self.schema.write_bytes(self.schema.read_bytes() + b"\n")
        errors = pin.validate(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("does not match pinned canonical", errors[0])

    def test_missing_pin_fails(self) -> None:
        self.pin_file.unlink()
        self.assertEqual(pin.validate(self.root), [f"{pin.PIN_RELATIVE} is missing"])

    def test_malformed_pin_fails(self) -> None:
        self.pin_file.write_text("not-a-digest  book-platform.contract.v1.schema.json\n", encoding="utf-8")
        self.assertIn("64 lowercase hex", pin.validate(self.root)[0])

    def test_pin_for_other_file_fails(self) -> None:
        self.pin_file.write_text(f"{'a' * 64}  other.json\n", encoding="utf-8")
        self.assertIn("expected", pin.validate(self.root)[0])

    def test_matching_canonical_passes(self) -> None:
        core = self.canonical_repo(self.schema.read_bytes())
        self.assertEqual(pin.validate(self.root, pin.resolve_canonical(str(core))), [])

    def test_changed_canonical_reports_drift_and_stale_pin(self) -> None:
        core = self.canonical_repo(self.schema.read_bytes() + b"\n")
        errors = pin.validate(self.root, pin.resolve_canonical(str(core)))
        self.assertTrue(any("differs from canonical" in error for error in errors), errors)
        self.assertTrue(any("is stale" in error for error in errors), errors)

    def test_missing_canonical_fails(self) -> None:
        missing = Path(self._temp.name) / "absent.json"
        self.assertIn("is missing", pin.validate(self.root, missing)[0])

    def test_main_exit_codes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pin.main([str(self.root)]), 0)
            self.schema.write_text("{}", encoding="utf-8")
            self.assertEqual(pin.main([str(self.root)]), 1)


REGISTRY = """\
# comment
schema_version: book-platform-repository-registry.v1
platforms:
  - id: sample
    repository: book-sample-platform
    data_owner: none
    capabilities: [alpha, beta]
    depends_on: []
    source_status: current-implementation-in-solo-empire
    source_paths: [infra/sample, infra/extra.ts]
    migration_gates: [shadow parity, rollback]

  - id: other
    repository: book-other-platform
    capabilities: [gamma]
notes:
  - id: ignored
"""


class RegistryAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = align.parse_registry(REGISTRY)["sample"]
        self.contract: dict[str, Any] = {
            "platform_id": "sample",
            "repository": "book-sample-platform",
            "data_owner": "none",
            "capabilities": ["alpha", "beta"],
            "depends_on": [],
            "migration_gates": ["shadow parity", "rollback"],
            "current_implementation": {
                "repository": "solo-empire",
                "source_path": "infra/sample",
                "source_paths": ["infra/sample", "infra/extra.ts"],
                "source_status": "current-implementation-in-solo-empire",
            },
            "interfaces": [
                {"id": "sample.http.x", "direction": "provides", "source": "infra/sample/x.ts"},
                {"id": "sample.consumes.y", "direction": "consumes", "source": "infra/api/auth.ts"},
            ],
        }

    def test_parser_reads_only_platform_entries(self) -> None:
        platforms = align.parse_registry(REGISTRY)
        self.assertEqual(sorted(platforms), ["other", "sample"])
        self.assertEqual(self.entry["capabilities"], ["alpha", "beta"])
        self.assertEqual(self.entry["depends_on"], [])
        self.assertEqual(self.entry["migration_gates"], ["shadow parity", "rollback"])

    def test_aligned_contract_passes(self) -> None:
        self.assertEqual(align.compare(self.contract, self.entry, None), ([], []))

    def test_source_path_drift_fails(self) -> None:
        self.contract["current_implementation"]["source_paths"] = ["infra/sample"]
        errors, _ = align.compare(self.contract, self.entry, None)
        self.assertTrue(any("source_paths" in error for error in errors), errors)

    def test_capability_and_dependency_drift_fail(self) -> None:
        self.contract["capabilities"] = ["alpha"]
        self.contract["depends_on"] = ["identity"]
        errors, _ = align.compare(self.contract, self.entry, None)
        self.assertEqual(len(errors), 2, errors)

    def test_provided_interface_outside_source_paths_warns(self) -> None:
        self.contract["interfaces"][0]["source"] = "infra/api/server.ts"
        errors, warnings = align.compare(self.contract, self.entry, None)
        self.assertEqual(errors, [])
        self.assertTrue(any("outside source_paths" in warning for warning in warnings), warnings)

    def test_missing_paths_warn_against_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            solo = Path(temp)
            (solo / "infra/sample").mkdir(parents=True)
            (solo / "infra/sample/x.ts").write_text("", encoding="utf-8")
            _, warnings = align.compare(self.contract, self.entry, solo)
        self.assertEqual(len(warnings), 2, warnings)

    def test_main_reads_registry_from_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            solo = Path(temp) / "solo-empire"
            registry = solo / align.REGISTRY_RELATIVE
            registry.parent.mkdir(parents=True)
            registry.write_text(REGISTRY, encoding="utf-8")
            repo = Path(temp) / "repo"
            repo.mkdir()
            (repo / "contract.json").write_text(json.dumps(self.contract), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(align.main(["--solo-empire", str(solo), "--root", str(repo)]), 0)
                self.assertEqual(align.main(["--solo-empire", str(solo), "--root", str(repo), "--strict-paths"]), 1)


if __name__ == "__main__":
    unittest.main()
