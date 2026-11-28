"""Chay tu dong toan bo kich ban demo bat buoc tren 1 may (nhieu tien trinh).
Dung: python scripts/demo.py      Log tung node: demo_data/logs/*.log"""
import hashlib, os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from common import make_meta  # noqa: E402  (dong nay cung nap file .env neu co)

os.environ.setdefault("TRACKER_API_KEY", "demo-key")  # chua co .env thi dung khoa demo
D = os.path.join(ROOT, "demo_data")
LOGS = os.path.join(D, "logs")
TR = "http://127.0.0.1:8000"
procs = []
SLOW = os.getenv("DEMO_SLOW", "0.15")  # do tre moi lan gui manh (giay); trang trinh bay dat 0.4 cho de xem


def start(name, *args):
    f = open(os.path.join(LOGS, f"{name}.log"), "w")
    p = subprocess.Popen([sys.executable, "-u", *args], cwd=os.path.join(ROOT, "src"), stdout=f, stderr=subprocess.STDOUT)
    procs.append(p)
    return p


def peer(name, port, mode, target, *extra):
    return start(name, "peer.py", mode, target, "--id", name, "--port", str(port), "--tracker", TR,
                 "--dir", os.path.join(D, name), *extra)


def wait_for(cond, timeout):
    """Cho den khi dieu kien dung (thay vi ngu thoi gian co dinh) de demo on dinh tren moi may."""
    t = time.time()
    while time.time() - t < timeout and not cond():
        time.sleep(0.1)


def grep(name, key):
    with open(os.path.join(LOGS, f"{name}.log"), encoding="utf-8", errors="ignore") as f:
        return [l.rstrip() for l in f if key in l]


def fhash(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    shutil.rmtree(D, ignore_errors=True)
    os.makedirs(LOGS)
    src = os.path.join(D, "video.bin")
    with open(src, "wb") as f:
        f.write(os.urandom(4 * 1024 * 1024))  # file 4 MB -> 64 chunk
    fid = make_meta(src, TR)["file_id"]
    try:
        print("[1] Khoi dong tracker + 2 seeder (A tot, B gui hong chunk 0-31)")
        start("TRACKER", "tracker.py", "--port", "8000")
        wait_for(lambda: grep("TRACKER", "Tracker chay"), 30)  # cho tracker san sang
        peer("A", 9001, "seed", src, "--slow", SLOW)
        b = peer("B", 9002, "seed", src, "--slow", SLOW, "--corrupt", "0-31")
        wait_for(lambda: grep("TRACKER", "JOIN peer A") and grep("TRACKER", "JOIN peer B"), 30)  # cho A, B dang ky xong

        print(f"[2] C va D cung tai file {fid} song song (moi peer toi da 4 ket noi)")
        c = peer("C", 9003, "get", fid, "--workers", "4", "--slow", SLOW, "--exit-when-done")
        d = peer("D", 9004, "get", fid, "--workers", "4", "--slow", SLOW, "--exit-when-done")
        # cho toi khi da co chunk hong bi phat hien (hoac C tai duoc 1/3 file) roi moi tat B
        wait_for(lambda: grep("C", "CHUNK KHONG HOP LE") or grep("D", "CHUNK KHONG HOP LE")
                 or len(grep("C", "OK chunk")) >= 20, 20)
        print("[3] Tat dot ngot seeder B giua luc dang tai")
        b.kill()
        c.wait(120); d.wait(120)

        print("[4] Kiem tra tiep tuc tai: E tai, bi tat giua chung, chay lai")
        e = peer("E", 9005, "get", fid, "--workers", "2", "--slow", SLOW, "--exit-when-done")
        wait_for(lambda: len(grep("E", "OK chunk")) >= 10, 30)  # cho E tai duoc 10 chunk roi moi tat
        e.kill(); e.wait(); os.replace(os.path.join(LOGS, "E.log"), os.path.join(LOGS, "E_lan1.log"))
        peer("E", 9005, "get", fid, "--workers", "4", "--exit-when-done").wait(120)

        print("\n===== KET QUA =====")
        orig = fhash(src)
        for n in ("C", "D", "E"):
            out = os.path.join(D, n, "video.bin")
            print(f"{n}: hash file tai ve {'KHOP' if os.path.exists(out) and fhash(out) == orig else 'SAI'} voi file goc")
        for n in ("C", "D"):
            src_peers = {l.split(" tu ")[1].split()[0] for l in grep(n, "OK chunk")}
            print(f"{n}: tai tu cac peer {sorted(src_peers)}")
            print(f"   chunk hong bi phat hien: {len(grep(n, 'CHUNK KHONG HOP LE'))}, lan doi nguon: {len(grep(n, 'DOI NGUON'))}")
        up = [l for l in grep("C", "UPLOAD") + grep("D", "UPLOAD") if "(minh dang co" in l and "/64)" in l
              and "(minh dang co 64/64)" not in l]
        print(f"Upload khi chua tai xong: {len(up)} lan, vd: {up[0] if up else '-'}")
        print("E:", (grep("E", "TIEP TUC TAI") or ["khong thay log tiep tuc"])[0])
    finally:
        for p in procs:
            p.kill()


if __name__ == "__main__":
    main()
