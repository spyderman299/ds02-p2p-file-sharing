"""Tracker: chi luu metadata va danh sach peer, KHONG luu noi dung file."""
import argparse, hmac, json, re, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from common import API_KEY, MAX_BODY, log_setup

PEER_TIMEOUT = 10  # giay khong heartbeat -> coi nhu peer da roi mang
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")  # dinh dang hop le cua peer_id, file_id
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


def valid_meta(d):
    try:
        n = d["num_chunks"]
        return (ID_RE.match(d["file_id"]) and isinstance(n, int) and 0 < n <= 100000
                and isinstance(d["chunk_hashes"], list) and len(d["chunk_hashes"]) == n
                and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in d["chunk_hashes"])
                and re.fullmatch(r"[0-9a-f]{64}", d["file_hash"]) and isinstance(d["name"], str))
    except (KeyError, TypeError):
        return False


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

    def authed(self):
        """Xac thuc: header X-API-Key phai khop khoa cua tracker (so sanh thoi gian hang so)."""
        if hmac.compare_digest(self.headers.get("X-API-Key", "").encode(), API_KEY.encode()):
            return True
        log.warning("AUTH tu choi %s %s: sai hoac thieu X-API-Key", self.client_address[0], self.path)
        self.reply(401, {"error": "sai hoac thieu X-API-Key"})
        return False

    def do_GET(self):
        if not self.authed():
            return
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
        if not self.authed():
            return
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > MAX_BODY:  # gioi han kich thuoc thong diep
            log.warning("TU CHOI request %d byte tu %s: vuot gioi han", n, self.client_address[0])
            return self.reply(413, {"error": "request qua lon"})
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
            assert isinstance(d, dict)
        except (ValueError, AssertionError):
            return self.reply(400, {"error": "bad json"})
        with lock:
            prune()
            if self.path == "/register":
                if not valid_meta(d):
                    return self.reply(400, {"error": "metadata khong hop le"})
                files[d["file_id"]] = d
                log.info("REGISTER file %s (%s, %d chunk)", d["file_id"], d["name"], d["num_chunks"])
                return self.reply(200, {"ok": True})
            if self.path == "/announce":
                fid, pid, addr, ch = d.get("file_id"), d.get("peer_id"), d.get("addr"), d.get("chunks")
                if fid not in files:
                    return self.reply(404, {"error": "file chua dang ky"})
                if not (isinstance(pid, str) and ID_RE.match(pid) and isinstance(addr, str) and addr.startswith("http://")
                        and isinstance(ch, list) and all(isinstance(i, int) and 0 <= i < files[fid]["num_chunks"] for i in ch)):
                    return self.reply(400, {"error": "announce khong hop le"})
                ps = peers.setdefault(fid, {})
                if pid not in ps:
                    log.info("JOIN peer %s @ %s (co %d/%d chunk)", pid, addr, len(ch), files[fid]["num_chunks"])
                ps[pid] = {"peer_id": pid, "addr": addr, "chunks": ch, "seen": time.time()}
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
    if not API_KEY:
        log.error("Chua dat TRACKER_API_KEY (tao file .env tu .env.example) -> dung")
        sys.exit(1)
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    log.info("Tracker chay tai cong %d (bat xac thuc API key)", a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
