# 18 — Git & release workflow

ทาง merge ที่เห็นใน history: PR squash บน GitHub (#2, #3), merge commit แบบ local แล้ว push (PR #1 → `47a91c1` และ gh แสดง PR #1 เป็น CLOSED ไม่ใช่ MERGED; `build-hygiene` → `60fac76`) และ commit ตรงบน main
ไม่มี tag, ไม่มี release และไม่มี deploy: "release" คือ commit บน main ที่ Check เขียว ซึ่ง consumer ต้อง pin SHA เอง

```mermaid
gitGraph
  commit id: "57b74a2 scaffold"
  branch claude-session
  commit id: "9dce378"
  checkout main
  merge claude-session id: "86295f7"
  commit id: "671efdd license"
  commit id: "36d0af7 rename"
  commit id: "fc91a8e re-pin"
  commit id: "3cdebbf"
  branch shared-infra
  commit id: "e2d1ab3 PR1 head"
  checkout main
  commit id: "e1b2a86 PR2 squash"
  commit id: "99313d2 PR3 squash"
  commit id: "9928e98"
  commit id: "3d41131 fix"
  checkout shared-infra
  commit id: "55c636e"
  checkout main
  merge shared-infra id: "47a91c1 merge PR1"
  commit id: "2fafa3c uv lock"
  branch build-hygiene
  commit id: "5ca3296 pin actions"
  commit id: "50ecc21"
  checkout main
  merge build-hygiene id: "60fac76"
```

```mermaid
flowchart LR
  a["Branch or direct commit"] --> b["Push: Check runs (contract, offline, security)"]
  b --> c{"green?"}
  c -- no --> a
  c -- yes --> d["Merge locally and push main, or squash PR"]
  d --> e["Check on main"]
  e --> f["Consumer updates pinned SHA and rebuilds wheel"]
```

Sources: `git log --first-parent --format="%h %ad %p %s" origin/main`, `gh pr list -R bookchaowalit-backend/platform-observability --state all`, `gh run list -R bookchaowalit-backend/platform-observability -L 100`, `.github/workflows/check.yml`; ops record: merge-locally (2026-11-03)

## Open questions

- ไม่มี branch protection หรือ required checks ที่อ่านได้จาก repo: main รับ direct push (เช่น `4a03324` ที่ Check แดง)
