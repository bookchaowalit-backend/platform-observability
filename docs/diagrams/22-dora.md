# 22 — DORA metrics

ช่วงเวลา: 90 วันถึง 2026-11-03 (ครอบคลุมทั้ง history เพราะ commit แรก 2026-09-17) repo นี้ **ไม่มี deploy** จึงใช้ "change ที่ลง main" เป็น proxy ของ deployment และใช้ผล workflow `Check` บน main เป็นสัญญาณ failure

| Metric | วิธีวัดสำหรับ repo นี้ | ค่า (90 วัน) | คำสั่ง |
|---|---|---|---|
| Deployment frequency | **ไม่มี deploy**; proxy = first-parent commits บน main | 17 changes (≈ 1.3 ต่อสัปดาห์); 13 Check runs บน main | `git log --first-parent --since="90 days ago" --oneline origin/main \| wc -l`; `gh run list -R bookchaowalit-backend/platform-observability -L 100 --json headBranch,event,conclusion` |
| Lead time for changes | เวลาจาก commit แรกของ change ถึงลง main (merge) หรือ PR open → merge (squash) | median 22 นาที จาก 5 change ที่ผ่าน branch: 7 นาที (`60fac76`), 8 นาที (PR #3), 22 นาที (PR #2), 8 ชม. 39 นาที (`86295f7`), 8 วัน 8 ชม. (PR #1 → `47a91c1`); direct commit = 0 (ไม่มี push time ให้วัด) | `git log -1 --format=%cI <merge>` กับ `git log --reverse --format=%aI <p1>..<p2> \| head -1`; `gh pr list --state all --json createdAt,mergedAt` |
| Change fail rate | Check run บน main ที่ `failure` / Check runs บน main | 3 / 13 = 23% (`36d0af7`, `fc41535`, `4a03324`) | `gh run list ... --json headBranch,conclusion` แล้วกรอง `headBranch=main` |
| Failed deployment recovery time | เวลาจาก run แดงบน main ถึง run เขียวถัดไปบน main | 2 เหตุการณ์: 2 ชม. 1 นาที (03:36Z → `fc91a8e` 05:37Z, 2026-10-13) และ 3 นาที (09:41Z → `3d41131` 09:44Z, 2026-10-22); median ≈ 1 ชม. 2 นาที | `gh run list ... --json createdAt,headSha,conclusion` |
| Deployment rework rate | change บน main ที่เป็น `fix:` แก้ change ก่อนหน้าบน main โดยตรง / changes ทั้งหมด | 2 / 17 = 12% (`fc91a8e` แก้ pin หลัง `fc41535`; `3d41131` แก้ exec bit หลัง `4a03324`) | `git log --first-parent --format="%h %s" origin/main` |

หมายเหตุ

- ไม่มีการ deploy ใด ๆ ดังนั้นค่าทั้งห้าวัด "การเปลี่ยนที่ลง main" ไม่ใช่ production
- runs ที่ `cancelled` (`a0fc05b`) ไม่นับ เพราะอยู่บน branch `build-hygiene` และถูก concurrency ยกเลิก
- commit `9928e98`, `3795e27`, `4a03324` ถูก push พร้อมกัน มี run บน main เพียงตัวเดียว (`4a03324`)

Sources: `git log --first-parent origin/main`, `gh run list -R bookchaowalit-backend/platform-observability -L 100`, `gh pr list -R bookchaowalit-backend/platform-observability --state all`, `.github/workflows/check.yml`

## Open questions

- ถ้า consumer (platform-infra-kit) เริ่ม pin SHA ใหม่เป็นประจำ ควรนับ "การ bump pin ใน consumer" เป็น deployment ของ library นี้หรือไม่
