# Postmortem — DR Drill Lab 23 (TEMPLATE)

Theo đúng template §4 "Sau Failover: Blameless Postmortem". Blameless: câu hỏi là
"hệ thống/process nào cho phép chuyện này", không phải "ai làm sai".

## 1. Timeline (mọi dòng phải có evidence path:line)

| ISO time | Sự kiện | Evidence |
|---|---|---|
| 2026-10-09T13:32:13 | outage bắt đầu | `chaos/chaos-events.jsonl:1` |
| 2026-10-09T13:32:13 | user đầu tiên bị ảnh hưởng | `reports/drill-2-withdr.jsonl:25` |
| 2026-10-09T13:32:28 | health check alert | `reports/health-events.jsonl:2` |
| 2026-10-09T13:32:44 | operator confirm cutover | `reports/failover-events.jsonl:5` |
| 2026-10-09T13:32:47 | resolved (request đầu tiên OK từ region phụ) | `reports/drill-2-withdr.jsonl:42` |

## 2. RTO/RPO đo được vs mục tiêu — gap ở bước nào?

- RTO mục tiêu: 300s · đo được: `34.3s` · gap: `-265.7s` (Vượt mục tiêu)
- RPO mục tiêu: 300s · đo được: `14.03s` (`7` doc bị mất) · gap: `-285.97s` (Vượt mục tiêu)
- **Bước tốn nhiều giây nhất:** `Health check detect floor + Operator trễ` (tốn hơn 20s) — vì Health check phải đợi đủ 3 lần fail (15s) để chống flap, sau đó operator mất thêm mười mấy giây nữa để thao tác chạy runbook.

## 3. Root cause (5 whys)

1. Tại sao RTO lại bị cộng thêm 15 giây detect floor?
   -> Vì hệ thống được thiết kế bắt buộc phải bắt 3 nhịp fail liên tiếp của health check.
2. Tại sao phải chờ 3 nhịp fail?
   -> Để chống false-positive (báo động giả) do mạng bị lag giật 1-2 giây.
3. Tại sao GPU warm-up tốn tới 6 giây?
   -> Vì model vector embedding khá nặng, việc nạp nó từ ổ đĩa (FS) vào bộ nhớ GPU (vRAM) của Region B bị chậm.
4. Tại sao model không được nạp sẵn?
   -> Vì muốn tiết kiệm chi phí, Region B đang chạy cấu hình pool_state=cold chứ không phải hot-standby.
5. Bài học rút ra: Thiết kế DR phải đánh đổi giữa "Phí duy trì (Cold vs Hot)" và "Thời gian RTO".

## 4. Action items (có owner + deadline)

| # | Action | Owner | Deadline | Giảm RTO/RPO bao nhiêu giây |
|---|---|---|---|---|
| 1 | Thử nghiệm rút ngắn interval health check xuống 3s (detect floor = 9s) | Hệ thống | Tuần tới | ~6s RTO |
| 2 | Nạp sẵn (pre-warm) model size nhỏ vào Region B | Operator | Quý sau | ~6s RTO |

## 5. Ba câu hỏi bắt buộc trả lời

1. `interval × threshold` của bạn là bao nhiêu giây? Nó chiếm bao nhiêu % RTO?
   - Là 5s × 3 = 15 giây. Chiếm gần **44%** tổng thời gian RTO (15 / 34.3).
2. Nếu hạ interval xuống 1s, RTO giảm mấy giây — và bạn trả giá gì (§4 flapping)?
   - RTO có thể giảm tới 12s, nhưng bạn trả giá bằng việc hệ thống sẽ liên tục tự động failover (flapping) chéo qua lại hai Region mỗi khi mạng bị giật nhẹ một tích tắc, gây downtime giả còn nghiêm trọng hơn outage thật.
3. Nếu outage kéo dài 6 giờ và region chính mất dữ liệu vĩnh viễn, `docs_lost` của bạn có nghĩa gì với khách hàng?
   - `docs_lost=7` có nghĩa là có 7 tài liệu được người dùng upload vào hệ thống vào sát nút giờ sập sẽ bị mất vĩnh viễn. Khách hàng sẽ thấy "Tôi vừa upload file thành công mà sao giờ tìm không ra?". Cần có giải pháp đối soát (Reconciliation) để nhắc user upload lại.
