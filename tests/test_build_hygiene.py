"""Offline supply-chain gate: every workflow `uses:` is pinned to a full commit SHA.

This repository is a library (no Dockerfile, no service), so only the pin check applies.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s'\"#]+)", re.MULTILINE)
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def unpinned_uses(text: str) -> list[str]:
    """Every remote `uses:` reference that is not a full 40-hex commit SHA."""
    return [ref for ref in USES.findall(text) if not ref.startswith("./") and not PINNED.match(ref)]


class WorkflowPinTests(unittest.TestCase):
    def test_checker_flags_tags_and_short_shas(self) -> None:
        sample = (
            "steps:\n"
            "  - uses: actions/checkout@v4\n"
            "  - uses: actions/setup-python@a26af69\n"
            "  - uses: './local-action'\n"
            "  - uses: actions/cache@0123456789abcdef0123456789abcdef01234567 # v4\n"
            "    uses: org/repo/.github/workflows/x.yml@main\n"
        )
        self.assertEqual(
            unpinned_uses(sample),
            ["actions/checkout@v4", "actions/setup-python@a26af69", "org/repo/.github/workflows/x.yml@main"],
        )

    def test_every_workflow_action_is_sha_pinned(self) -> None:
        files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
        self.assertTrue(files)
        found = {path.name: unpinned_uses(path.read_text(encoding="utf-8")) for path in files}
        self.assertEqual({name: refs for name, refs in found.items() if refs}, {})

    def test_no_dockerfile_to_gate(self) -> None:
        # If a Dockerfile is ever added, port the clean-checkout image gates from the service repos.
        self.assertFalse((ROOT / "Dockerfile").exists())


if __name__ == "__main__":
    unittest.main()
