# Project Documentation

Tài liệu chính thức cho project **chat-system** — DevSecOps template + SAST/SCA dashboard với AI fix tiếng Việt.

> Đối tượng đọc: bản thân khi quay lại sau pause, người mới onboard, panel defense thesis.

---

## Mục lục

| # | File | Nội dung |
|---|---|---|
| 01 | [overview.md](01-overview.md) | Project là gì, vì sao tồn tại, v0.1.0 vs V2 |
| 02 | [architecture.md](02-architecture.md) | 3-repo topology, vai trò từng component, bản chất "MCP" |
| 03 | [data-flow.md](03-data-flow.md) | End-to-end: code push → CI → webhook → AI fix → dashboard |
| 04 | [deploy.md](04-deploy.md) | Render Blueprint, env vars, secrets, lifecycle |
| 05 | [reusable-workflow.md](05-reusable-workflow.md) | Hợp đồng `sast-action`, tools per language, artifact schema |
| 06 | [verify.md](06-verify.md) | Checklist verify từng tầng + curl commands |
| 07 | [history.md](07-history.md) | Lịch sử commit V2 (chronological) |
| 08 | [limitations.md](08-limitations.md) | Bug đã biết, TODO, scope cut, security gaps |
| 09 | [roadmap.md](09-roadmap.md) | V2.2 → V2.5 + v0.3 vision |
| 10 | [quick-reference.md](10-quick-reference.md) | Common task — copy-paste commands |

---

## Đọc theo mục tiêu

- **Tao mới onboard, cần hiểu tổng quan**: 01 → 02 → 03
- **Tao cần deploy hoặc trouble-shoot deploy**: 04 → 06
- **Tao tạo inheritor repo mới** (Java/Node/Go app dùng SAST): 05 → 10
- **Tao defense thesis sắp tới**: 01 → 02 → 03 → 08 → 09
- **Tao quay lại sau pause, cần biết đang ở đâu**: 07 → 09

---

## Cập nhật

Mỗi khi commit feature lớn (V2.2, V2.3, ...) — update `07-history.md` + `09-roadmap.md`. Các file khác chỉ cập nhật khi architecture đổi.
