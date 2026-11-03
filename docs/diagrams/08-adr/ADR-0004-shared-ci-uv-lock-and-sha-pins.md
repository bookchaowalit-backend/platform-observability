# ADR-0004 — CI ผ่าน shared workflows ที่ pin SHA, lock ด้วย uv และ coverage gate 90%

- **Status:** accepted (retro-documented)
- **วันที่:** `3795e27` (2026-10-22), `2fafa3c` (2026-10-24), `5ca3296` / merge `60fac76` (2026-10-28/29)

## Context

repo เป็น public จึงใช้ GitHub-hosted runner (ops record: ci-hosting-policy, 2026-11-03) และต้องตาม TDD/SDD standard (coverage gate ratchet ตาม ADR-0004 ของ platform)

## Decision

- `check.yml` เรียก `bookchaowalit/platform-ci-workflows` `ci-python.yml` และ `security.yml` ที่ `87dc5e1c` (v1.1.1)
- dependency lock ใน `uv.lock` (`uv sync --frozen --all-extras`), Ruff + mypy, coverage threshold `90` (วัดได้ 90.21% เมื่อ 2026-10-24)
- ทุก `uses:` ต้อง pin SHA และมี test ป้องกัน (`tests/test_build_hygiene.py`)

## Consequences

- การอัปเกรด workflow ต้องเปลี่ยน SHA เอง
- gateway parity tests นับเฉพาะใน job `contract` ไม่นับใน coverage

## Evidence

`.github/workflows/check.yml`, `pyproject.toml`, `uv.lock`, `tests/test_build_hygiene.py`, `.gitleaksignore`, `git log` `3795e27`, `2fafa3c`, `5ca3296`
