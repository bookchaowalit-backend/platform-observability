# ADR-0002 — Telemetry ต้องผ่าน allow-list schema ที่ไม่มี free text และ retention 30/14/7/90 วัน

- **Status:** accepted (retro-documented; owner decision 2026-10-16)
- **วันที่:** PR #2 `e1b2a86` (2026-10-15), owner decision PR #3 `99313d2` (2026-10-16)

## Context

contract ต้นทางกำหนดว่า credential ต้องไม่อยู่ใน log และ access metadata ต้องถูก redact (gate doc §Contract sections) source เดิม (`telemetry.ts`, `system_health.py`) ส่ง raw path, `error.message`, ยอดเงินและ `str(e)` ออกมา

## Decision

- `schema/telemetry/redacted-telemetry-event.v1.schema.json`: หนึ่ง `log` / `metric` / `trace` / `health_snapshot` ต่อเอกสาร ทุก object `additionalProperties: false` และ `x-forbidden` scan keys และ value patterns (bearer, JWT, provider keys, เบอร์โทร, บัตร ฯลฯ)
- retention ผูกกับ signal: `metric-30d`, `log-14d`, `trace-7d`, `health-90d`, purge ≤ 24 h, ไม่อยู่ใน backup
- dashboard ยังไม่เชื่อมจนกว่า G2/G3/G7 แก้และ G5/G6 มี owner decision

## Consequences

- gateway events ที่มี client-supplied `X-Request-ID` ถูก reject (G5)
- envelope (`schema_version`, `signal`, …) เพิ่มที่ collector ผ่าน `envelope_access_log()`; G10 ยังเปิด
- retention ยังไม่ถูก apply กับ Prometheus/Loki/Tempo ใด ๆ

## Evidence

`docs/gates/BOO-160-telemetry-redaction-retention.md`, `fixtures/gates/telemetry-redaction-retention.json`, `scripts/telemetry_policy.py`, `tests/test_telemetry_policy.py`, `gh pr list` (#2, #3)
