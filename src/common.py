"""Ham dung chung: doc cau hinh .env, bam SHA-256, tao metadata, goi HTTP/JSON, ghi log."""
import hashlib, json, logging, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=os.path.join(ROOT, ".env")):
    """Nap bien tu file .env (neu co) vao moi truong; bien da dat san duoc giu nguyen."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep and not k.startswith("#"):
                    os.environ.setdefault(k.strip(), v.strip())


load_env()
API_KEY = os.getenv("TRACKER_API_KEY", "")  # khoa bi mat dung chung trong swarm, KHONG commit len GitHub
DEFAULT_CHUNK = 64 * 1024        # 64 KB / chunk
MAX_BODY = 1024 * 1024           # gioi han kich thuoc request JSON: 1 MB
MAX_CHUNK = 4 * 1024 * 1024      # gioi han kich thuoc chunk: 4 MB


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def make_meta(path, tracker, chunk_size=DEFAULT_CHUNK):
    """Doc file theo tung chunk, tinh hash tung chunk va hash ca file."""
    hashes, full, size = [], hashlib.sha256(), 0
    with open(path, "rb") as f:
        while b := f.read(chunk_size):
            hashes.append(sha(b))
            full.update(b)
            size += len(b)
    fh = full.hexdigest()
    return {
        "file_id": fh[:16],
        "name": os.path.basename(path),
        "size": size,
        "chunk_size": chunk_size,
        "num_chunks": len(hashes),
        "chunk_hashes": hashes,
        "file_hash": fh,
        "tracker": tracker,
    }


def http_json(url, data=None, timeout=5):
    """Gui GET (data=None) hoac POST JSON, kem header X-API-Key de xac thuc."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "X-API-Key": API_KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def log_setup(name):
    logging.basicConfig(
        format=f"%(asctime)s.%(msecs)03d [{name}] %(levelname)s %(message)s",
        datefmt="%H:%M:%S", level=logging.INFO, stream=sys.stdout)
    return logging.getLogger(name)
