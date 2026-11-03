# 15 — CI/CD pipeline

workflow เดียว `.github/workflows/check.yml` (name `Check`) มีสาม job ที่ไม่มี `needs` ต่อกัน (รันขนาน) ไม่มีขั้น deploy
concurrency `check-${{ github.ref }}` cancel-in-progress, `permissions: contents: read`

```mermaid
flowchart TD
  trg["Triggers: push (any branch), pull_request, workflow_dispatch"] --> c311
  trg --> c312
  trg --> off
  trg --> sec

  subgraph contract["job contract, matrix Python 3.11 and 3.12, ubuntu-latest, 10 min"]
    c311["3.11"] --> s1["checkout repo (SHA pinned)"]
    c312["3.12"] --> s1
    s1 --> s2["checkout platform-api-gateway at 6e1fb34 into .ci, persist-credentials false"]
    s2 --> s3["setup-python"]
    s3 --> s4["scripts/check_schema_pin.py"]
    s4 --> s5["bash scripts/check.sh with REQUIRE_GATEWAY_TESTS=1"]
  end

  subgraph offline["job offline: platform-ci-workflows ci-python.yml at 87dc5e1c v1.1.1"]
    off["Checkout"] --> o2["Set up uv and Python 3.12"]
    o2 --> o3["uv sync --frozen --all-extras"]
    o3 --> o4["Lint Ruff (format-check false)"]
    o4 --> o5["Typecheck mypy"]
    o5 --> o6["Test: check.sh, pytest --cov, uv build --wheel"]
    o6 --> o7["Coverage gate 90"]
  end

  subgraph security["job security: security.yml at 87dc5e1c"]
    sec["gitleaks"]
    sec2["semgrep p/default"]
    sec3["osv-scanner"]
    sec4["trivy-fs HIGH,CRITICAL"]
  end
  trg --> sec2
  trg --> sec3
  trg --> sec4
```

ประวัติ: workflow `Shared runtime` (มาจาก PR #1) รันครั้งสุดท้าย 2026-10-23 แล้วถูกรวมเข้า job `offline` (comment ใน `check.yml`: "formerly shared-runtime.yml")

Sources: `.github/workflows/check.yml`, `scripts/check.sh`, `pyproject.toml`; `bookchaowalit/platform-ci-workflows` `.github/workflows/ci-python.yml` และ `security.yml` ที่ `87dc5e1` (local clone, read-only); `gh run list -R bookchaowalit-backend/platform-observability -L 100`

## Open questions

- ไม่มี
