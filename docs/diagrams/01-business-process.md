# 01 — Business process (As-Is / To-Be)

repo นี้คือ **library + boundary contract** ของ capability `observability` (logs, metrics, traces, alerts, status) ไม่ใช่ service ที่ host อยู่
`PRODUCT.md` ระบุว่า status เป็น `scaffolded`, DOCPACK verdict `template` และ "No service in production uses it yet"
implementation ปัจจุบันตาม registry คือ `infra/self-hosted-stack` ใน `solo-empire` (ซึ่ง gate doc บันทึกว่าถูกลบออกจาก solo-empire HEAD แล้วใน `9f44f602`, 2026-10-11)

ดังนั้น "business process" ของ repo นี้มี 2 เส้น: (1) การเปลี่ยน contract/policy แล้วให้ CI พิสูจน์ (2) service ที่ใช้ library เรียก `instrument(app, ...)` แล้วผลิต telemetry ที่ถูก redact

## As-Is (จากโค้ดวันนี้)

```mermaid
flowchart TD
  subgraph Change["Contract and policy change (owner or agent)"]
    A["Edit contract.json / schema / telemetry policy / src"] --> B["Push branch or open PR"]
    B --> C["GitHub Actions: Check workflow"]
    C --> D{"contract + offline + security green?"}
    D -- no --> A
    D -- yes --> E["Merge to main (local merge, then push)"]
  end
  subgraph Gate["Migration gate evidence"]
    E --> F["Gate record in docs/gates and fixtures/gates"]
    F --> G{"Owner decision recorded?"}
    G -- "BOO-160 accepted 2026-10-16" --> H["Gate status accepted; runtime still not moved"]
  end
  subgraph Runtime["Consumer runtime (outside this repo)"]
    I["FastAPI service calls instrument(app, service_name, metrics_token, endpoint)"] --> J["Middleware counts requests, records span, writes one JSON log line"]
    J --> K["/metrics served only with Bearer METRICS_TOKEN"]
    J --> L["Spans exported to explicit HTTPS OTLP endpoint, bounded queue"]
  end
  E -.->|"wheel built from a pinned SHA"| I
```

Sources: `PRODUCT.md`, `README.md`, `contract.json`, `.github/workflows/check.yml`, `docs/gates/BOO-160-telemetry-redaction-retention.md`, `fixtures/gates/telemetry-redaction-retention.json`, `src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `docs/shared-runtime.md`; ops record: merge-locally (2026-11-03)

## To-Be (จากเอกสารใน repo เท่านั้น)

แหล่ง To-Be: `docs/UPGRADE-PLAN.md`, migration gates ใน `contract.json`, "Still open" ใน gate doc และ `docs/shared-runtime.md`

```mermaid
flowchart TD
  P0a["P0: redaction contract for telemetry events (done as BOO-160)"] --> P0b["P0: inventory alert rules and retention for alert-drill gate"]
  P0b --> G2["Fix producers: G2 telemetry.ts attrs, G3 system_health text, G7 Loki/Tempo retention"]
  G2 --> G5["Owner decisions: G5 client X-Request-ID, G6 unkeyed subject_hash, G10 envelope and 3600s cap"]
  G5 --> Drill["Alert drill: synthetic failure to test receiver, verify notify and recovery"]
  Drill --> Dash["Connect dashboards (deferred by owner decision option 4)"]
  Dash --> P1["P1: replace vendored schema with backend-core package; sanitized fixtures success/duplicate/timeout/provider failure"]
  P1 --> Cut["Shadow parity, rollback rehearsal, then cutover (migration.cutover pending)"]
  Cut --> P2["P2: health endpoint and rollback instructions once a runtime exists"]
```

Sources: `docs/UPGRADE-PLAN.md`, `contract.json` (`migration`, `migration_gates`), `docs/gates/BOO-160-telemetry-redaction-retention.md` §Gaps, §Still open, `docs/shared-runtime.md`

## Open questions

- เกณฑ์ cutover สำหรับเปิด runtime (`PRODUCT.md` Measures ติด `[ต้องยืนยัน]`)
- ops record book-platforms-status (2026-11-03) บันทึกว่า "observability = library, decision open" และ scraper จะปลุก service ที่ sleep อยู่: owner ยังไม่ตัดสินว่าจะ host collector/scraper หรือไม่
- implementation เดิม `infra/self-hosted-stack` ไม่อยู่ใน solo-empire HEAD แล้ว แต่ `contract.json` ยังชี้ไปที่ path นั้น: จะแก้ `current_implementation` อย่างไร
