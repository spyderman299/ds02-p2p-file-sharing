"""4 test bao mat va du lieu sai (muc 9 cua de)."""
import json, os, sys, unittest, http.client
sys.path.insert(0, os.path.dirname(__file__))
from helpers import Cluster, http_json, raw, API_KEY  # noqa: E402


class TestSecurity(unittest.TestCase):
    def setUp(self):
        self.c = Cluster()
        self.c.tracker()

    def tearDown(self):
        self.c.stop()

    def test_s1_sai_hoac_thieu_api_key_bi_tu_choi(self):
        path, m = self.c.make_file(100)
        self.assertEqual(raw(f"{self.c.tr}/files", key=""), 401)
        self.assertEqual(raw(f"{self.c.tr}/files", key="khoa-sai"), 401)
        self.c.seed("A", path, m["file_id"])
        url = f"http://127.0.0.1:{self.c.ports['A']}/chunk/{m['file_id']}/0"
        self.assertEqual(raw(url, key="khoa-sai"), 401)   # peer cung xac thuc
        self.assertEqual(raw(url), 200)
        self.assertIn("AUTH tu choi", self.c.log("TRACKER"))

    def test_s2_du_lieu_sai_dinh_dang_va_qua_lon(self):
        _, m = self.c.make_file(100)
        post = lambda p, b: raw(f"{self.c.tr}{p}", "POST", b, headers={"Content-Type": "application/json"})
        self.assertEqual(post("/register", b"{khong phai json"), 400)
        self.assertEqual(post("/register", json.dumps({**m, "chunk_hashes": ["xyz"]}).encode()), 400)
        http_json(f"{self.c.tr}/register", m)
        bad = {"file_id": m["file_id"], "peer_id": "../../etc", "addr": "http://h:1", "chunks": []}
        self.assertEqual(post("/announce", json.dumps(bad).encode()), 400)
        conn = http.client.HTTPConnection("127.0.0.1", self.c.tport, timeout=5)  # khai bao body 2 MB > gioi han 1 MB
        conn.request("POST", "/announce", body=b"{}", headers={"X-API-Key": API_KEY, "Content-Length": str(2 * 1024 * 1024)})
        self.assertEqual(conn.getresponse().status, 413)

    def test_s3_chunk_hong_bi_loai_file_van_dung(self):
        path, m = self.c.make_file(1024)
        self.c.seed("A", path, m["file_id"], "--slow", "0.05")
        self.c.seed("B", path, m["file_id"], "--corrupt", "0-15")  # B gui hong moi chunk
        self.c.peer("C", "get", m["file_id"], "--exit-when-done").wait(60)
        self.assertIn("CHUNK KHONG HOP LE", self.c.log("C"))
        self.assertTrue(self.c.output_ok("C", m))

    def test_s4_duong_dan_va_chi_so_chunk_khong_hop_le(self):
        path, m = self.c.make_file(100)
        self.c.seed("A", path, m["file_id"])
        base = f"http://127.0.0.1:{self.c.ports['A']}"
        self.assertEqual(raw(f"{base}/chunk/{m['file_id']}/999"), 404)
        self.assertEqual(raw(f"{base}/chunk/{m['file_id']}/-1"), 404)
        self.assertEqual(raw(f"{base}/chunk/..%2F..%2Fetc/0"), 404)
        self.assertEqual(raw(f"{base}/chunk/khac/0"), 404)


if __name__ == "__main__":
    unittest.main()
