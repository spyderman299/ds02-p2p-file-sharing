"""8 test chuc nang (muc 9 cua de)."""
import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(__file__))
from helpers import Cluster, http_json, wait  # noqa: E402


class TestFunctional(unittest.TestCase):
    def setUp(self):
        self.c = Cluster()
        self.c.tracker()

    def tearDown(self):
        self.c.stop()

    def test_f1_metadata_day_du_truong(self):
        _, m = self.c.make_file(150)
        for k in ("file_id", "name", "size", "chunk_size", "num_chunks", "chunk_hashes", "file_hash", "tracker"):
            self.assertIn(k, m)
        self.assertEqual(m["num_chunks"], 3)  # 150 KB / 64 KB -> 3 chunk
        self.assertEqual(len(m["chunk_hashes"]), 3)

    def test_f2_dang_ky_va_lay_metadata(self):
        _, m = self.c.make_file(100)
        http_json(f"{self.c.tr}/register", m)
        self.assertEqual(http_json(f"{self.c.tr}/meta/{m['file_id']}"), m)

    def test_f3_announce_tra_ve_danh_sach_peer(self):
        _, m = self.c.make_file(100)
        http_json(f"{self.c.tr}/register", m)
        http_json(f"{self.c.tr}/announce", {"file_id": m["file_id"], "peer_id": "X", "addr": "http://h:1", "chunks": [0]})
        r = http_json(f"{self.c.tr}/announce", {"file_id": m["file_id"], "peer_id": "Y", "addr": "http://h:2", "chunks": []})
        self.assertEqual({p["peer_id"] for p in r["peers"]}, {"X", "Y"})

    def test_f4_leave_xoa_peer(self):
        _, m = self.c.make_file(100)
        http_json(f"{self.c.tr}/register", m)
        http_json(f"{self.c.tr}/announce", {"file_id": m["file_id"], "peer_id": "X", "addr": "http://h:1", "chunks": []})
        http_json(f"{self.c.tr}/leave", {"file_id": m["file_id"], "peer_id": "X"})
        self.assertEqual(http_json(f"{self.c.tr}/peers/{m['file_id']}")["peers"], [])

    def test_f5_tai_tu_mot_nguon_hash_khop(self):
        path, m = self.c.make_file(512)
        self.c.seed("A", path, m["file_id"])
        self.c.peer("C", "get", m["file_id"], "--exit-when-done").wait(60)
        self.assertTrue(self.c.output_ok("C", m))

    def test_f6_tai_song_song_tu_hai_nguon(self):
        path, m = self.c.make_file(1024)
        self.c.seed("A", path, m["file_id"], "--slow", "0.05")
        self.c.seed("B", path, m["file_id"], "--slow", "0.05")
        self.c.peer("C", "get", m["file_id"], "--exit-when-done").wait(60)
        log = self.c.log("C")
        self.assertIn("tu A", log)
        self.assertIn("tu B", log)
        self.assertTrue(self.c.output_ok("C", m))

    def test_f7_upload_khi_chua_tai_xong(self):
        path, m = self.c.make_file(2048)  # 32 chunk
        self.c.seed("A", path, m["file_id"], "--slow", "0.1", "--upload-slots", "2")
        c = self.c.peer("C", "get", m["file_id"], "--exit-when-done", "--slow", "0.02")
        d = self.c.peer("D", "get", m["file_id"], "--exit-when-done", "--slow", "0.02")
        c.wait(60); d.wait(60)
        ups = [l for l in (self.c.log("C") + self.c.log("D")).splitlines()
               if "UPLOAD" in l and "/32)" in l and "co 32/32" not in l]
        self.assertGreater(len(ups), 0, "khong co lan upload nao truoc khi tai xong")
        self.assertTrue(self.c.output_ok("C", m) and self.c.output_ok("D", m))

    def test_f8_tiep_tuc_tai_sau_khoi_dong_lai(self):
        path, m = self.c.make_file(2048)
        self.c.seed("A", path, m["file_id"], "--slow", "0.1", "--upload-slots", "1")
        c = self.c.peer("C", "get", m["file_id"], "--exit-when-done", "--workers", "1")
        self.assertTrue(wait(lambda: self.c.log("C").count("OK chunk") >= 5, 20))
        c.kill(); c.wait()
        self.c.peer("C", "get", m["file_id"], "--exit-when-done").wait(60)
        self.assertIn("TIEP TUC TAI", self.c.log("C"))
        self.assertTrue(self.c.output_ok("C", m))


if __name__ == "__main__":
    unittest.main()
