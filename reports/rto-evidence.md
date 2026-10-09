# RTO/RPO Evidence — Lab 23

Quy tắc duy nhất: mỗi con số ở đây phải trỏ được về **một dòng log thật**
(`đường/dẫn.jsonl:số_dòng`). `pytest tests/test_rto_evidence.py` sẽ mở từng file ra kiểm tra.
Con số không có evidence = trượt, bất kể các phần khác.

## 1. Drill 1 — không có DR (baseline)

| Chỉ số | Giá trị | Cách đo | Evidence |
|---|---|---|---|
| t_outage | `<iso>` | chaos kill | `chaos/chaos-events.jsonl:1` |
| Request fail đầu tiên | `+0.0s` | dòng `ok:false` đầu tiên sau t_outage | `reports/drill-1-nodr.jsonl:6` |
| Request thành công sau đó | không có | không có dòng `ok:true` nào sau t_outage | `reports/measure-drill-1.json` |
| RTO | `NO_RECOVERY` | `tools/measure_rto.py` | `reports/measure-drill-1.json` |

## 2. Drill 2 — có DR

| Mốc | +giây từ t_outage | Cách đo | Evidence |
|---|---|---|---|
| t_outage (mốc 0) | 0 | `action:kill` | `chaos/chaos-events.jsonl:1` |
| User thấy lỗi đầu tiên | +0.1s | dòng `ok:false` đầu | `reports/drill-2-withdr.jsonl:25` |
| Health check phát hiện | +15.0s | `to:UNHEALTHY, region:a` | `reports/health-events.jsonl:2` |
| Snapshot restore xong | +25.2s | `step:2_restore_snapshot` | `reports/failover-events.jsonl:2` |
| Region phụ ready | +25.2s | `step:4_wait_ready` | `reports/failover-events.jsonl:4` |
| DNS cutover | +31.3s | `step:5_dns_cutover` | `reports/failover-events.jsonl:6` |
| **RTO đo được** | +34.3s | dòng `ok:true` đầu sau lỗi | `reports/drill-2-withdr.jsonl:42` |

| Chỉ số | Đo được | Mục tiêu (slide §1) | Verdict |
|---|---|---|---|
| RTO — Inference API | `34.3s` | 300s (5 phút) | PASS |
| RPO — Vector DB | `14.03s` / `7` doc | 300s (5 phút) | PASS |

## 3. RTO của tôi gồm những gì (bắt buộc — đây là phần chấm điểm hiểu bài)

| Thành phần | Giây | Nó đến từ đâu | Giảm được bằng cách nào |
|---|---|---|---|
| Health-check detect floor | 15.0s | `interval_s × threshold` trong `reports/health-events.jsonl:2` | Giảm thời gian interval hoặc threshold, đổi cơ chế Push thay vì Pull |
| Snapshot restore | 0.0s | 2_restore → 3_scale | Dùng network attached storage (NFS, EFS) thay vì copy file lớn |
| GPU pool warm-up | 6.0s | `waited_s` ở `4_wait_ready` | Duy trì một lượng warm-pool nhỏ luôn sẵn sàng phục vụ |
| DNS/LB TTL cache | 3.0s | t_recovered − t_cutover | Giảm TTL của Edge Proxy hoặc DNS xuống tối thiểu |
