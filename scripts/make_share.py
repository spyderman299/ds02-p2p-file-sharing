"""Tao file mau share/video.bin (4 MB) va in FILE_ID de dung voi Docker."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from common import make_meta  # noqa: E402

os.makedirs(os.path.join(ROOT, "share"), exist_ok=True)
p = os.path.join(ROOT, "share", "video.bin")
if not os.path.exists(p):
    with open(p, "wb") as f:
        f.write(os.urandom(4 * 1024 * 1024))
print(make_meta(p, "")["file_id"])
