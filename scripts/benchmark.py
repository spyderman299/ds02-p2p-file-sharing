"""Do hieu nang: thoi gian tai theo so nguon, theo so ket noi, thoi gian phat hien loi.
Dung: python scripts/benchmark.py  -> ket qua in ra man hinh va ghi docs/benchmark.md"""
import os, re, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from common import make_meta  # noqa: E402

os.environ.setdefault("TRACKER_API_KEY", "demo-key")
D = os.path.join(ROOT, "bench_data")
TR = "http://127.0.0.1:8100"
SLOW = "0.05"  # gia lap bang thong: moi chunk 64KB mat 50ms de gui


def run(name, *args):
    f = open(os.path.join(D, f"{name}.log"), "w")
    return subprocess.Popen([sys.executable, "-u", *args], cwd=os.path.join(ROOT, "src"), stdout=f, stderr=subprocess.STDOUT)


def logtxt(name):
    with open(os.path.join(D, f"{name}.log"), encoding="utf-8", errors="ignore") as f:
        return f.read()


def ts(line):  # "HH:MM:SS.mmm" -> giay
    h, m, s = line[:12].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def scenario(tag, seeders, workers, kill_after=None):
    shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
    src = os.path.join(D, "file.bin")
    with open(src, "wb") as f:
        f.write(os.urandom(4 * 1024 * 1024))
    fid = make_meta(src, TR)["file_id"]
    ps = [run("T", "tracker.py", "--port", "8100")]; time.sleep(0.8)
    for k in range(seeders):
        ps.append(run(f"S{k}", "peer.py", "seed", src, "--id", f"S{k}", "--port", str(9101 + k), "--tracker", TR,
                      "--dir", os.path.join(D, f"S{k}"), "--slow", SLOW, "--upload-slots", "2"))
        time.sleep(0.5)
    t0 = time.time()
    c = run("C", "peer.py", "get", fid, "--id", "C", "--port", "9200", "--tracker", TR, "--dir", os.path.join(D, "C"),
            "--workers", str(workers), "--exit-when-done")
    detect = None
    if kill_after:
        time.sleep(kill_after); ps[1].kill(); kill_t = time.time()
    c.wait(120)
    total = time.time() - t0
    log = logtxt("C")
    dl = float(re.search(r"trong ([\d.]+)s", log).group(1))
    ok = "HASH TOAN FILE KHOP" in log
    if kill_after:
        lines = [l for l in log.splitlines() if "DOI NGUON" in l]
        if lines:
            kt = time.localtime(kill_t)
            detect = ts(lines[0]) - (kt.tm_hour * 3600 + kt.tm_min * 60 + kt.tm_sec + kill_t % 1)
    for p in ps:
        p.kill()
    return {"tag": tag, "seeders": seeders, "workers": workers, "dl": dl, "total": total, "ok": ok, "detect": detect}


def main():
    rows = [scenario("1 nguon", 1, 4), scenario("2 nguon", 2, 4), scenario("3 nguon", 3, 4),
            scenario("3 nguon, 1 ket noi", 3, 1), scenario("3 nguon, 8 ket noi", 3, 8),
            scenario("3 nguon, tat S0 sau 0.3s", 3, 4, kill_after=0.3)]
    md = ["| Kich ban | So nguon | So ket noi | Thoi gian tai (s) | Toc do (MB/s) | Hash cuoi | Phat hien loi (s) |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['tag']} | {r['seeders']} | {r['workers']} | {r['dl']:.2f} | {4 / r['dl']:.2f} | "
                  f"{'Khop' if r['ok'] else 'Sai'} | {'' if r['detect'] is None else '%.3f' % r['detect']} |")
    out = "\n".join(md)
    print(out)
    with open(os.path.join(ROOT, "docs", "benchmark.md"), "w", encoding="utf-8") as f:
        f.write(f"# Ket qua do hieu nang\nFile 4 MB, chunk 64 KB (64 chunk), moi lan upload tre {SLOW}s/chunk, "
                f"moi seeder toi da 2 luot upload cung luc.\n\n{out}\n")
    shutil.rmtree(D, ignore_errors=True)


if __name__ == "__main__":
    main()
