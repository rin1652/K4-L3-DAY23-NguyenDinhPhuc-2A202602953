# Runbook 1 trang — Region chính down (TEMPLATE, sinh viên điền)

Runbook phải chạy được lúc 3h sáng bởi người KHÔNG viết nó. Mỗi bước: lệnh copy-paste
được + cách biết bước đó xong.

| # | Bước | Lệnh | Biết là xong khi | Ai làm |
|---|---|---|---|---|
| 1 | Xác nhận outage | `python chaos/kill_region.py status` | `a.alive=false` 3 lần liên tiếp | on-call |
| 2 | Mở incident + bấm giờ RTO | `python dr/runbook.py --primary a --target b --backend fs` (nhập 'y') | ts ghi vào `reports/runbook-run.jsonl` | on-call |
| 3 | Restore state ở region phụ | `python dr/runbook.py ...` (Tự động trong runbook) | thấy log `2_restore_snapshot` thành công | hệ thống / automation |
| 4 | Scale pool warm→full | `python dr/runbook.py ...` (Tự động trong runbook) | `/readyz` của b trả 200 | hệ thống / automation |
| 5 | DNS/LB cutover | `python dr/runbook.py ...` (Tự động trong runbook) | check `edge/active_region` là `b` | hệ thống / automation |
| 6 | Verify golden signals | `python loadgen/traffic.py` (hoặc curl) | p95 < `500`ms, error rate < `1.0`% | on-call |
| 7 | Đo RTO + postmortem | `python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl` | `rto_verdict` != null | on-call |

**Rollback (failover ngược):** điều kiện nào thì trả traffic về region A? Ai quyết định?
Chỉ trả về khi Region A đã hoạt động ổn định trở lại ít nhất 30 phút, được kiểm tra kỹ lưỡng bởi Dev và phê duyệt bởi Incident Commander (Tránh tình trạng flap qua lại do mạng chập chờn). Cần trigger kịch bản failover thủ công để đưa traffic ngược từ b về a.
