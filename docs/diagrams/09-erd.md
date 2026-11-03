# 09 — ERD

library **ไม่มี database และไม่ persist ข้อมูล** (metrics อยู่ใน `CollectorRegistry` ในหน่วยความจำของ process, spans อยู่ใน queue ที่ทิ้งเมื่อ shutdown) แต่ repo กำหนด data model ที่ตรวจได้ใน JSON Schema ภาพนี้จึงเป็น logical model ของ telemetry event (`redacted-telemetry-event.v1`) และ boundary contract

```mermaid
erDiagram
  ENVELOPE ||--o| LOG : "signal=log"
  ENVELOPE ||--o| METRIC : "signal=metric"
  ENVELOPE ||--o| TRACE : "signal=trace"
  ENVELOPE ||--o| HEALTH_SNAPSHOT : "signal=health_snapshot"
  METRIC ||--o{ METRIC_LABEL : has
  TRACE ||--o{ SPAN_ATTRIBUTE : has
  CONTRACT ||--|{ INTERFACE : declares
  CONTRACT ||--|{ MIGRATION_GATE : requires

  ENVELOPE {
    string schema_version
    string signal
    string retention_class
    string service
    string environment
    string observed_at
  }
  LOG {
    string level
    string event
    string method
    string route
    int status
    number duration_seconds
    number latency_ms
    string request_id
    string correlation_id
    string trace_id
    string subject_hash
    string error_class
  }
  METRIC {
    string name
    string type
    string unit
    number value
  }
  METRIC_LABEL {
    string key
    string value
  }
  TRACE {
    string trace_id
    string span_id
    string parent_span_id
    string name
    string kind
    number duration_seconds
    string status_code
  }
  SPAN_ATTRIBUTE {
    string key
    string value
  }
  HEALTH_SNAPSHOT {
    string source_schema_version
    object grades
    object sections
  }
  CONTRACT {
    string schema_version
    string platform_id
    string repository
    string status
    string api_version
    string data_owner
  }
  INTERFACE {
    string id
    string kind
    string direction
    string name
    string status
    string source
  }
  MIGRATION_GATE {
    string name
  }
```

| Signal | `retention_class` | Store ที่วางแผน | Retention (accepted) |
|---|---|---|---|
| metric | `metric-30d` | Prometheus TSDB | 30 วัน |
| log | `log-14d` | Loki | 14 วัน |
| trace | `trace-7d` | Tempo | 7 วัน |
| health_snapshot | `health-90d` | file/object store | 90 วัน |

Runtime in-memory metric series ที่ library สร้าง: `platform_requests_total{service,method,route,status}` และ `platform_request_duration_seconds{service,method,route}` (buckets .005–10 s)

Sources: `schema/telemetry/redacted-telemetry-event.v1.schema.json`, `contract.json`, `schema/book-platform.contract.v1.schema.json`, `docs/gates/BOO-160-telemetry-redaction-retention.md` §Retention policy, `src/platform_observability/middleware.py`

## Open questions

- store จริงของ metric/log/trace/health ยังไม่มี (retention ยังไม่ถูก apply) ตาม gate doc
