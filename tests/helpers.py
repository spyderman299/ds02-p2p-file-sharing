"""Tien ich cho test: dung tracker va peer that (moi node 1 tien trinh, giao tiep qua mang)."""
import os, shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
os.environ.setdefault("TRACKER_API_KEY", "test-key")
from common import API_KEY, make_meta, http_json, sha  # noqa: E402,F401


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait(cond, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


class Cluster:
    def __init__(s):
        s.tmp = tempfile.mkdtemp()
        s.procs, s.ports, s.files = {}, {}, []
        s.tport = free_port()
        s.tr = f"http://127.0.0.1:{s.tport}"

    def _run(s, name, *args):
        f = open(os.path.join(s.tmp, f"{name}.log"), "a")
        s.files.append(f)
        s.procs[name] = subprocess.Popen([sys.executable, "-u", *args], cwd=SRC, stdout=f, stderr=subprocess.STDOUT)
        return s.procs[name]

    def tracker(s):
        s._run("TRACKER", "tracker.py", "--port", str(s.tport))
        assert wait(lambda: http_json(f"{s.tr}/files") is not None), "tracker khong khoi dong"

    def make_file(s, kb):
        path = os.path.join(s.tmp, "file.bin")
        with open(path, "wb") as f:
            f.write(os.urandom(kb * 1024))
        return path, make_meta(path, s.tr)

    def peer(s, name, mode, target, *extra):
        s.ports[name] = s.ports.get(name) or free_port()
        return s._run(name, "peer.py", mode, target, "--id", name, "--port", str(s.ports[name]), "--tracker", s.tr,
                      "--dir", os.path.join(s.tmp, name), *extra)

    def seed(s, name, path, fid, *extra):
        p = s.peer(name, "seed", path, *extra)
        assert wait(lambda: any(x["peer_id"] == name for x in http_json(f"{s.tr}/peers/{fid}")["peers"])), "seeder chua join"
        return p

    def log(s, name):
        with open(os.path.join(s.tmp, f"{name}.log"), encoding="utf-8", errors="ignore") as f:
            return f.read()

    def output_ok(s, name, meta):
        p = os.path.join(s.tmp, name, meta["name"])
        with open(p, "rb") as f:
            return os.path.exists(p) and sha(f.read()) == meta["file_hash"]

    def dl_time(s, name):
        import re
        return float(re.search(r"Tai xong \d+ chunk trong ([\d.]+)s", s.log(name)).group(1))

    def stop(s):
        for p in s.procs.values():
            p.kill()
            p.wait()
        for f in s.files:
            f.close()
        shutil.rmtree(s.tmp, ignore_errors=True)


def raw(url, method="GET", body=b"", key=None, headers=None):
    """Gui request tuy y (de test du lieu sai); tra ve ma HTTP."""
    h = {"X-API-Key": API_KEY if key is None else key, **(headers or {})}
    req = urllib.request.Request(url, data=body if method == "POST" else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
