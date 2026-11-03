# ADR-0001 — แยก capability observability เป็น boundary contract repo ก่อนย้าย runtime

- **Status:** accepted (retro-documented)
- **วันที่:** scaffold 2026-09-17 (`57b74a2`), เปลี่ยนชื่อเป็น `platform-observability` 2026-10-13 (`36d0af7`)

## Context

capability `observability` (logs, metrics, traces, alerts, status) เคยอยู่ใน `solo-empire` ที่ `infra/self-hosted-stack` (Docker Compose profile `observability`) consumer ต้องไม่ import database หรือ private module ของ platform อื่น (`README.md` §Boundary)

## Decision

สร้าง repo ที่มี `contract.json` (`book-platform.contract.v1`, status `scaffolded`), vendored schema ที่ pin sha256 กับสำเนา canonical ใน backend-core, `docs/CONTRACT-SURFACE.md` และ migration gates (`telemetry redaction`, `retention policy`, `alert drill`) โดย `migration.cutover: pending` และ `rollback: required`

## Consequences

- runtime ไม่ย้ายจนกว่าจะมี parity และ rollback evidence (`README.md` §Migration gate)
- ต้องรักษา contract ให้ตรงกับ registry `platforms.yaml` (`check_registry_alignment.py`, local only)
- DOCPACK verdict `template`: ห้ามอ้างเป็นผลิตภัณฑ์

## Evidence

`contract.json`, `schema/book-platform.contract.v1.schema.json.sha256`, `scripts/check.py`, `scripts/check_schema_pin.py`, `README.md`, `DOCPACK/00-product-card.md`, `git log` `57b74a2`, `36d0af7`
