"""2 test loi va phuc hoi (muc 9 cua de)."""
import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(__file__))
from helpers import Cluster, http_json, wait  # noqa: E402


class TestFault(unittest.TestCase):
    def setUp(self):
        self.c = Cluster()
        self.c.tracker()

    def tearDown(self):
        self.c.stop()

    def test_r1_nguon_bi_tat_giua_chung_doi_nguon(self):
        path, m = self.c.make_file(2048)
        self.c.seed("A", path, m["file_id"], "--slow", "0.1")
        b = self.c.seed("B", path, m["file_id"], "--slow", "0.1")
        c = self.c.peer("C", "get", m["file_id"], "--exit-when-done")
        self.assertTrue(wait(lambda: "tu B" in self.c.log("C"), 20))
        b.kill()  # nguon B roi mang dot ngot
        c.wait(60)
        self.assertIn("DOI NGUON", self.c.log("C"))
        self.assertTrue(self.c.output_ok("C", m))

    def test_r2_tracker_khoi_dong_lai_peer_dang_ky_lai(self):
        path, m = self.c.make_file(512)
        self.c.seed("A", path, m["file_id"])
        self.c.procs["TRACKER"].kill(); self.c.procs["TRACKER"].wait()
        self.c.tracker()  # tracker moi, mat het trang thai
        self.assertTrue(wait(lambda: "DANG KY LAI" in self.c.log("A"), 15))
        self.assertTrue(wait(lambda: http_json(f"{self.c.tr}/meta/{m['file_id']}") is not None, 10))
        self.c.peer("C", "get", m["file_id"], "--exit-when-done").wait(60)
        self.assertTrue(self.c.output_ok("C", m))


if __name__ == "__main__":
    unittest.main()
