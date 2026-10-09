"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


def step(n, name, **kw):
    """TODO: ghi 1 dòng {ts, iso, step, name, ...} vào LOG."""
    import datetime
    kw["ts"] = time.time()
    kw["iso"] = datetime.datetime.fromtimestamp(kw["ts"]).isoformat()
    kw["step"] = n
    kw["name"] = name
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(kw) + "\n")


def confirm(auto: bool, msg: str) -> bool:
    """TODO: auto=True -> True; ngược lại hỏi y/N. Đừng bỏ hàm này đi."""
    if auto:
        return True
    try:
        ans = input(f"{msg} [y/N]: ").strip().lower()
        return ans == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    """TODO: 7 bước ở trên."""
    from dr import health_checker
    
    t_start = time.time()

    # Bước 1: xac_nhan_outage (probe nhiều lần)
    fails = 0
    for _ in range(3):
        ready, _ = health_checker.probe(primary, 2.0)
        if not ready:
            fails += 1
        time.sleep(1.0)
    outage_confirmed = fails >= 3
    step(1, "xac_nhan_outage", primary=primary, outage_confirmed=outage_confirmed)
    if not outage_confirmed:
        return {"ok": False, "reason": "No outage confirmed"}

    # Lấy t_outage từ chaos/chaos-events.jsonl cho bước 2
    t_outage = None
    try:
        lines = pathlib.Path("chaos/chaos-events.jsonl").read_text().splitlines()
        for ln in reversed(lines):
            ev = json.loads(ln)
            if ev.get("action") == "kill":
                t_outage = ev["ts"]
                break
    except Exception:
        pass

    # Bước 2: thong_bao_incident
    if not confirm(auto, f"Failover from {primary} to {target}?"):
        return {"ok": False, "reason": "user_aborted"}
    step(2, "thong_bao_incident", msg="operator confirmed failover", t_outage=t_outage)

    # Bước 3: scale_gpu_pool (gọi failover.failover)
    fo_result = fo.failover(target, backend, 60.0)
    step(3, "scale_gpu_pool", result=fo_result)
    if not fo_result.get("ok"):
        return {"ok": False, "reason": "failover_failed"}

    # Bước 4: verify_state_replica
    try:
        r = httpx.get(f"{URL[target]}/v1/state", timeout=2.0)
        target_state = r.json()
    except Exception as e:
        target_state = {"error": str(e)}
    step(4, "verify_state_replica", target_state=target_state)

    # Bước 5: dns_cutover
    active_region = ""
    try:
        active_region = pathlib.Path("edge/active_region").read_text().strip()
    except Exception:
        pass
    cutover_ok = active_region == target
    step(5, "dns_cutover", active_region=active_region, ok=cutover_ok)

    # Bước 6: verify_golden_signals
    latencies = []
    errors = 0
    for _ in range(10):
        t0 = time.time()
        try:
            r = httpx.get(f"{URL[target]}/v1/infer?q=test", timeout=2.0)
            if r.status_code == 200:
                latencies.append(time.time() - t0)
            else:
                errors += 1
        except Exception:
            errors += 1
    
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else None
    step(6, "verify_golden_signals", p95_latency=p95, error_rate=errors/10.0)

    # Bước 7: post_incident
    elapsed = time.time() - t_start
    step(7, "post_incident", elapsed_s=elapsed)

    return {"ok": True, "elapsed_s": elapsed}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
