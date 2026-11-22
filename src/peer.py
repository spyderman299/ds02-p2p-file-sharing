"""Peer: vua phuc vu (upload) chunk dang co, vua tai (download) chunk con thieu."""
import argparse, hashlib, hmac, json, os, random, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from common import API_KEY, DEFAULT_CHUNK, MAX_CHUNK, sha, read, make_meta, http_json, log_setup

DEAD_TTL = 10  # peer loi bi tam bo qua trong 10 giay
log = None


def parse_range(s):  # "0-3,7" -> {0,1,2,3,7}
    out = set()
    for part in filter(None, s.split(",")):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


class Peer:
    def __init__(s, a):
        s.a, s.id = a, a.id
        s.addr = f"http://{a.host}:{a.port}"
        s.tracker = a.tracker.rstrip("/")
        s.corrupt = parse_range(a.corrupt)
        s.have, s.lock, s.peers = set(), threading.Lock(), []
        s.dead, s.bad, s.stats = {}, set(), {}
        s.slots = threading.Semaphore(a.upload_slots)  # gioi han so luot upload cung luc (gia lap bang thong)

    def path(s, i):
        return os.path.join(s.dir, f"{i}.chunk")

    def setup(s, meta):
        """Luu metadata; quet chunk da co tren dia (de tai tiep sau khi khoi dong lai)."""
        if not 0 < meta["chunk_size"] <= MAX_CHUNK:
            raise ValueError("chunk_size vuot gioi han")
        s.meta = meta
        s.dir = os.path.join(s.a.dir, meta["file_id"])
        os.makedirs(s.dir, exist_ok=True)
        with open(os.path.join(s.dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=1)
        for i, h in enumerate(meta["chunk_hashes"]):
            if os.path.exists(s.path(i)) and sha(read(s.path(i))) == h:
                s.have.add(i)

    def split(s, src):
        with open(src, "rb") as f:
            for i in range(s.meta["num_chunks"]):
                with open(s.path(i), "wb") as o:
                    o.write(f.read(s.meta["chunk_size"]))
                s.have.add(i)

    # ---------- phia server: upload ----------
    def serve(s):
        peer = s

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if not hmac.compare_digest(self.headers.get("X-API-Key", "").encode(), API_KEY.encode()):
                    log.warning("AUTH tu choi %s: sai hoac thieu X-API-Key", self.client_address[0])
                    return self.send_error(401)
                p = self.path.strip("/").split("/")
                if len(p) != 3 or p[0] != "chunk" or p[1] != peer.meta["file_id"] or not p[2].isdigit():
                    return self.send_error(404)
                i = int(p[2])
                with peer.lock:
                    ok, n = i in peer.have, len(peer.have)
                if not ok:
                    return self.send_error(404)
                data = read(peer.path(i))
                if i in peer.corrupt:  # gia lap peer gui du lieu hong
                    data = bytes([data[0] ^ 0xFF]) + data[1:]
                with peer.slots:
                    time.sleep(peer.a.slow)
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                log.info("UPLOAD chunk %d -> %s (minh dang co %d/%d)%s", i, self.headers.get("X-Peer-Id", "?"),
                         n, peer.meta["num_chunks"], " [GUI CHUNK HONG]" if i in peer.corrupt else "")

        srv = ThreadingHTTPServer(("0.0.0.0", s.a.port), H)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info("Peer %s phuc vu tai %s", s.id, s.addr)

    # ---------- giao tiep tracker ----------
    def announce(s):
        with s.lock:
            chunks = sorted(s.have)
        try:
            r = http_json(f"{s.tracker}/announce",
                          {"file_id": s.meta["file_id"], "peer_id": s.id, "addr": s.addr, "chunks": chunks})
            s.peers = [p for p in r["peers"] if p["peer_id"] != s.id]
        except urllib.error.HTTPError as e:
            if e.code == 404:  # tracker khoi dong lai, mat trang thai -> dang ky lai metadata
                log.warning("Tracker khong biet file (co the vua khoi dong lai) -> DANG KY LAI metadata")
                try:
                    http_json(f"{s.tracker}/register", s.meta)
                except Exception:
                    pass
            elif e.code == 401:
                log.error("Tracker tu choi xac thuc: kiem tra TRACKER_API_KEY")
        except Exception as e:
            log.warning("Khong lien lac duoc tracker: %s", e)

    def heartbeat(s):
        while True:
            time.sleep(3)
            s.announce()

    def leave(s):
        try:
            http_json(f"{s.tracker}/leave", {"file_id": s.meta["file_id"], "peer_id": s.id}, timeout=2)
        except Exception:
            pass

    # ---------- phia client: download ----------
    def alive(s, pid):
        return time.time() - s.dead.get(pid, 0) > DEAD_TTL

    def get_chunk(s, i, cands):
        """Thu lan luot cac peer co chunk i; loi/sai hash -> chuyen sang peer khac."""
        for p in cands:
            pid = p["peer_id"]
            if not s.alive(pid) or (i, pid) in s.bad:
                continue
            try:
                req = urllib.request.Request(f"{p['addr']}/chunk/{s.meta['file_id']}/{i}",
                                             headers={"X-Peer-Id": s.id, "X-API-Key": API_KEY})
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = r.read(s.meta["chunk_size"] + 1)  # doc toi da chunk_size + 1 byte
            except Exception as e:
                s.dead[pid] = time.time()
                log.warning("LOI tai chunk %d tu %s (%s) -> danh dau peer loi, DOI NGUON", i, pid, type(e).__name__)
                continue
            if len(data) > s.meta["chunk_size"] or sha(data) != s.meta["chunk_hashes"][i]:
                s.bad.add((i, pid))
                log.error("CHUNK KHONG HOP LE %d tu %s: sai SHA-256 -> loai bo, tai lai tu peer khac", i, pid)
                continue
            with open(s.path(i), "wb") as f:
                f.write(data)
            with s.lock:
                s.have.add(i)
                s.stats[pid] = s.stats.get(pid, 0) + 1
                n = len(s.have)
            log.info("OK chunk %d tu %s (%d/%d)", i, pid, n, s.meta["num_chunks"])
            return True
        return False

    def download(s):
        n, t0 = s.meta["num_chunks"], time.time()
        with ThreadPoolExecutor(s.a.workers) as pool:  # gioi han so luong tai dong thoi
            while True:
                with s.lock:
                    missing = [i for i in range(n) if i not in s.have]
                if not missing:
                    break
                s.announce()
                owned = [(p, set(p["chunks"])) for p in s.peers if s.alive(p["peer_id"])]
                holders = {i: [p for p, c in owned if i in c and (i, p["peer_id"]) not in s.bad] for i in missing}
                avail = [i for i in missing if holders[i]]
                if not avail:
                    log.warning("Chua co peer nao giu %d chunk con thieu, cho...", len(missing))
                    time.sleep(2)
                    continue
                random.shuffle(avail)
                avail.sort(key=lambda i: len(holders[i]))  # rarest-first: chunk it nguoi co thi tai truoc
                batch = avail[: s.a.workers * 2]
                list(pool.map(lambda i: s.get_chunk(i, random.sample(holders[i], len(holders[i]))), batch))
        log.info("Tai xong %d chunk trong %.2fs. Nguon: %s", n, time.time() - t0, s.stats)

    def merge(s):
        out = os.path.join(s.a.dir, s.meta["name"])
        h = hashlib.sha256()
        with open(out, "wb") as f:
            for i in range(s.meta["num_chunks"]):  # ghep dung thu tu chi so chunk
                d = read(s.path(i))
                f.write(d)
                h.update(d)
        if h.hexdigest() == s.meta["file_hash"]:
            log.info("GHEP FILE %s -> HASH TOAN FILE KHOP (%s...)", out, s.meta["file_hash"][:16])
        else:
            log.error("GHEP FILE %s -> HASH TOAN FILE KHONG KHOP!", out)


def main():
    global log
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["seed", "get"])
    ap.add_argument("target", help="seed: duong dan file; get: file_id")
    ap.add_argument("--id", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--host", default=os.getenv("PEER_HOST", "127.0.0.1"), help="dia chi peer khac dung de ket noi toi")
    ap.add_argument("--tracker", default=os.getenv("TRACKER_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--dir", help="thu muc luu chunk (mac dinh data/<id>)")
    ap.add_argument("--workers", type=int, default=4, help="so ket noi tai dong thoi toi da")
    ap.add_argument("--chunk-kb", type=int, default=DEFAULT_CHUNK // 1024)
    ap.add_argument("--slow", type=float, default=0.0, help="tre moi lan upload (giay), de demo de quan sat")
    ap.add_argument("--upload-slots", type=int, default=4, help="so luot upload dong thoi toi da")
    ap.add_argument("--corrupt", default="", help="gia lap gui hong cac chunk, vd 0-3,7")
    ap.add_argument("--exit-when-done", action="store_true")
    a = ap.parse_args()
    a.dir = a.dir or os.path.join("data", a.id)
    log = log_setup(a.id)
    if not API_KEY:
        log.error("Chua dat TRACKER_API_KEY (tao file .env tu .env.example) -> dung")
        return
    p = Peer(a)
    if a.mode == "seed":
        p.setup(make_meta(a.target, a.tracker, a.chunk_kb * 1024))
        p.split(a.target)
        http_json(f"{p.tracker}/register", p.meta)
        log.info("SEED file %s -> file_id=%s (%d chunk)", p.meta["name"], p.meta["file_id"], p.meta["num_chunks"])
    else:
        p.setup(http_json(f"{p.tracker}/meta/{a.target}"))
        if p.have:
            log.info("TIEP TUC TAI: da co san %d/%d chunk tren dia", len(p.have), p.meta["num_chunks"])
    p.serve()
    p.announce()
    threading.Thread(target=p.heartbeat, daemon=True).start()
    try:
        if a.mode == "get":
            p.download()
            p.merge()
            if a.exit_when_done:
                return
        log.info("Dang seed, Ctrl+C de thoat")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        p.leave()


if __name__ == "__main__":
    main()
