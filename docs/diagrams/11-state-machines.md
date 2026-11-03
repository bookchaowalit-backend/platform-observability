# 11 — State machines

ไม่มี entity ที่มี status field ใน database มี lifecycle จริงสองแบบ: export processor ใน runtime และสถานะ contract/migration ใน `contract.json`

## BoundedProcessor lifecycle

```mermaid
stateDiagram-v2
  [*] --> Running: __init__ starts daemon thread
  Running --> Exporting: span batch taken from queue
  Exporting --> Running: export returns or raises
  Running --> Stopping: shutdown sets stop
  Exporting --> Stopping: shutdown sets stop
  Stopping --> Stopped: thread joined within 2.5s, queue drained and dropped
  Stopping --> Detached: join timed out, daemon thread may finish later
  Stopped --> [*]
  Detached --> [*]
```

`on_end` ไม่รับ span เมื่อ stop ถูก set หรือ span ไม่ sampled และทิ้ง span เมื่อ queue เต็ม

## Contract status (schema enum)

```mermaid
stateDiagram-v2
  [*] --> scaffolded
  scaffolded --> pilot
  pilot --> active
  active --> retired
  scaffolded --> retired
  retired --> [*]
  note right of scaffolded: current value in contract.json
```

ลำดับการเปลี่ยนเป็นการตีความจากความหมายของ enum (`scaffolded`, `pilot`, `active`, `retired`) schema ไม่ได้บังคับ transition

## Gate decision (BOO-160)

```mermaid
stateDiagram-v2
  [*] --> proposed: PR 2 merged 2026-10-15
  proposed --> accepted: owner decision 2026-10-16 (PR 3)
  accepted --> [*]
```

Sources: `src/platform_observability/export.py`, `contract.json`, `schema/book-platform.contract.v1.schema.json` (`status` enum), `docs/gates/BOO-160-telemetry-redaction-retention.md`, `fixtures/gates/telemetry-redaction-retention.json` (`status`)

## Open questions

- ลำดับ transition ของ contract status ไม่ได้เขียนไว้ใน repo
