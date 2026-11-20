"""Tracker: chi luu metadata va danh sach peer, KHONG luu noi dung file."""
import argparse, json, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from common import log_setup

PEER_TIMEOUT = 10  # giay khong heartbeat -> coi nhu peer da roi mang
files, peers, lock = {}, {}, threading.Lock()  # files[fid]=meta ; peers[fid][pid]=info
log = None


def prune():
    now = time.time()
    for fid, ps in peers.items():
        for pid in [p for p, i in ps.items() if now - i["seen"] > PEER_TIMEOUT]:
            del ps[pid]
            log.warning("TIMEOUT peer %s (file %s) -> xoa khoi danh sach", pid, fid)


def plist(fid):
    return [{k: v for k, v in i.items() if k != "seen"} for i in peers.get(fid, {}).values()]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.strip("/").split("/")
        with lock:
            prune()
            if len(p) == 2 and p[0] == "meta" and p[1] in files:
                return self.reply(200, files[p[1]])
            if len(p) == 2 and p[0] == "peers":
                return self.reply(200, {"peers": plist(p[1])})
            if p == ["files"]:
                return self.reply(200, {f: {"name": m["name"], "peers": len(peers.get(f, {}))} for f, m in files.items()})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self.reply(400, {"error": "bad json"})
        with lock:
            prune()
            if self.path == "/register":
                if not all(k in d for k in ("file_id", "chunk_hashes", "file_hash")):
                    return self.reply(400, {"error": "metadata thieu truong"})
                files[d["file_id"]] = d
                log.info("REGISTER file %s (%s, %d chunk)", d["file_id"], d["name"], d["num_chunks"])
                return self.reply(200, {"ok": True})
            if self.path == "/announce":
                fid, pid = d.get("file_id"), d.get("peer_id")
                if fid not in files or not pid:
                    return self.reply(404, {"error": "file chua dang ky"})
                ps = peers.setdefault(fid, {})
                if pid not in ps:
                    log.info("JOIN peer %s @ %s (co %d/%d chunk)", pid, d["addr"], len(d["chunks"]), files[fid]["num_chunks"])
                ps[pid] = {"peer_id": pid, "addr": d["addr"], "chunks": d["chunks"], "seen": time.time()}
                return self.reply(200, {"peers": plist(fid)})
            if self.path == "/leave":
                if peers.get(d.get("file_id"), {}).pop(d.get("peer_id"), None):
                    log.info("LEAVE peer %s", d["peer_id"])
                return self.reply(200, {"ok": True})
        self.reply(404, {"error": "not found"})


def main():
    global log
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    log = log_setup("TRACKER")
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    log.info("Tracker chay tai cong %d", a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
