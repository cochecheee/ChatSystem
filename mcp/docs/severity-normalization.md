# Chuẩn hoá mức độ rủi ro (Severity Normalization) — V4.1

> Trả lời cho vấn đề: **các tool phân loại mức độ lỗ hổng KHÔNG giống nhau** — có tool dùng **điểm số**
> (CVSS), có tool dùng **chữ** (high/critical), có tool dùng **thang riêng** (SpotBugs priority 1–5,
> ESLint 0/1/2, ZAP riskcode 0–3). Hệ thống quy tất cả về **một thang chuẩn** và ghi lại "vì sao".

Code: `mcp/src/services/normalizers/severity.py` (`resolve_severity`). Mọi normalizer gọi chung 1 hàm.

## 1. Thang chuẩn (canonical)

`critical > high > medium > low > info`. Mặc định khi không suy ra được: **`medium`** (chờ triage) —
KHÔNG bao giờ tụt về `info` một cách âm thầm (âm thầm hạ bậc = giấu lỗi thật).

## 2. Hai nguồn tín hiệu & chính sách "lấy mức nghiêm trọng hơn"

Mỗi finding có thể có **nhãn chữ** và/hoặc **điểm số**. Ta tính band từ mỗi nguồn rồi lấy **max**:

```
band_label = band_from_label(nhãn)      # vd "HIGH" -> high
band_score = band_from_score(điểm, kind) # vd 9.5 (v3) -> critical
severity   = max(band_label, band_score) theo thứ tự canonical
```

- **Vì sao lấy max:** không bao giờ đánh giá NHẸ hơn thực tế. VD Trivy gắn `HIGH` nhưng CVSS = 9.5 →
  chuẩn hoá **critical** (trước đây bug: giữ `high` vì code ưu tiên nhãn dù docstring nói ưu tiên điểm).
- **Khi lệch nhau** (`band_label != band_score`) → đánh dấu `disagreement=true` để log + hiện trên UI.
- **Ngoại lệ SARIF:** `security-severity` (điểm CVSS-style của CodeQL) là **AUTHORITATIVE**, KHÔNG max
  với `level=error/warning`. Lý do: CodeQL gắn `error` cho hầu hết rule bảo mật bất kể rủi ro thật →
  nếu max thì mọi finding CodeQL đều bị đẩy lên high. `error/warning` là *loại vấn đề*, không phải mức
  độ. Nhãn thật của SARIF (`problem.severity=recommendation`, `properties.severity=CRITICAL`) vẫn được
  dùng khi không có điểm.

## 3. CVSS v2 vs v3 (band khác nhau)

`band_from_score(score, kind)` phân biệt phiên bản — đây là lỗi phổ biến khi trộn v2/v3:

| Band | CVSS v3 / GitHub `security-severity` | CVSS v2 |
|------|--------------------------------------|---------|
| critical | ≥ 9.0 | *(v2 không có band critical)* |
| high | 7.0 – 8.9 | 7.0 – 10.0 |
| medium | 4.0 – 6.9 | 4.0 – 6.9 |
| low | 0.1 – 3.9 | 0.1 – 3.9 |

→ CVSS **v2 = 9.5** cho ra **high** (không phải critical). `kind` được ghi lại (`v3`/`v2`/
`security-severity`). Trivy: `nvd.V3Score`→v3, `nvd.V2Score`→v2. Dependency-Check: `cvssv3`→v3,
`cvssv2`→v2.

## 4. Bảng ánh xạ nhãn → chuẩn (crosswalk)

`band_from_label()` — bảng superset, KHÔNG phân biệt hoa/thường. Nhãn lạ / `UNKNOWN` → `None`
(rồi rơi về điểm hoặc `medium`).

| Nhãn gốc (nguồn) | → chuẩn |
|------------------|---------|
| `CRITICAL` | critical |
| `HIGH`, `ERROR` (Semgrep/SARIF) | high |
| `MEDIUM`, `MODERATE` (npm), `WARNING` (Semgrep/SARIF) | medium |
| `LOW`, `NOTE` (SARIF), `RECOMMENDATION` (CodeQL) | low |
| `INFO`, `INFORMATIONAL`, `NONE` (SARIF) | info |
| **SonarQube** `BLOCKER` | critical |
| **SonarQube** `MAJOR` | medium |
| **SonarQube** `MINOR` | low |

Thang số riêng (không đi qua bảng chữ — normalizer tự map sang band rồi truyền `label_band`):

| Tool | Thang gốc | → chuẩn |
|------|-----------|---------|
| SpotBugs | priority 1 / 2 / 3 / 4–5 | high / medium / low / info |
| ESLint | 2 / 1 / 0 | high / low / info |
| OWASP ZAP | riskcode 3 / 2 / 1 / 0 | high / medium / low / info |

> Ghi chú SonarQube: hiện chưa ingest SonarQube nên crosswalk mang tính phòng thủ; `CRITICAL`/`INFO`
> của Sonar rơi vào bảng chung (critical/info). Chỉ 3 nhãn không trùng canonical (`BLOCKER/MAJOR/MINOR`)
> được thêm.

## 5. Nâng bậc DAST (giữ nguyên hành vi cũ)

ZAP: `high` + CWE thuộc `_CRITICAL_CWE_IDS` (injection/RCE: CWE-77/78/89/94/95/502/917) + confidence cao
→ **critical** (`source="promoted-dast"`). Logic gate theo confidence nằm trong `zap.py` (không đưa vào
resolver để không nâng bậc quá tay các finding confidence thấp).

## 6. Provenance — lưu "vì sao" (không cần migration DB)

Mỗi finding lưu khối `raw_data["_severity"]`:

```json
{
  "original_label": "HIGH",        // nhãn/thang gốc tool báo (vd "priority=1", "riskcode=3")
  "cvss": 9.5, "cvss_kind": "v3",  // điểm gốc + phiên bản
  "band_label": "high",            // band suy từ nhãn
  "band_score": "critical",        // band suy từ điểm
  "normalized": "critical",        // kết quả cuối
  "source": "max(label,score)",    // label | score | sarif-level | promoted-dast | default
  "disagreement": true,            // nhãn & điểm lệch nhau
  "cvss_source": "tool"            // tool (thật) | derived-from-label (ước lượng) | none
}
```

- `cvss_source` phân biệt **CVSS thật** (từ tool/NVD) với **CVSS ước lượng** từ nhãn (enricher điền
  `critical→9.5, high→7.5, medium→5.0, low→2.0` khi tool không có điểm) → dashboard không trình bày số
  ước lượng như thể tool báo.

## 7. Hiển thị trên dashboard

- **SevChip** (list): tooltip `Tool: HIGH · CVSS 9.8 (v3) → CRITICAL (lấy mức cao hơn)` + dấu **▲** khi
  bị nâng bậc / lệch nhãn-điểm.
- **FindingDetail**: dòng **"Đánh giá mức độ"** ghi rõ nhãn gốc + điểm(+phiên bản+thật/ước lượng) →
  chuẩn hoá + lý do.

## 8. Ảnh hưởng & lưu ý

- **Thay đổi hành vi:** chính sách max làm một số finding **nâng bậc** (vd Trivy HIGH+CVSS≥9 → critical)
  → thay đổi số liệu **Security Gate / KPI** và `severity_max`/keeper của cross-tool dedup. Đây là chủ
  đích (chính xác hơn) — nhớ khi demo/phản biện.
- Kiểm thử: `mcp/tests/test_severity_resolver.py` (band v2/v3, crosswalk, max policy, provenance,
  tích hợp normalizer) + `test_normalizer_severity_v38.py` (SARIF vẫn score-first).
