"""Ham dung chung: bam SHA-256, tao metadata, goi HTTP/JSON, ghi log."""
import hashlib, json, logging, os, sys, urllib.request

DEFAULT_CHUNK = 64 * 1024  # 64 KB / chunk


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
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def log_setup(name):
    logging.basicConfig(
        format=f"%(asctime)s.%(msecs)03d [{name}] %(levelname)s %(message)s",
        datefmt="%H:%M:%S", level=logging.INFO, stream=sys.stdout)
    return logging.getLogger(name)
