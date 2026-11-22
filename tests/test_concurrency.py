"""2 test dong thoi (muc 9 cua de)."""
import os, sys, unittest
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from helpers import Cluster, http_json  # noqa: E402


class TestConcurrency(unittest.TestCase):
    def setUp(self):
        self.c = Cluster()
        self.c.tracker()

    def tearDown(self):
        self.c.stop()

    def test_c1_30_peer_announce_cung_luc(self):
        """Tracker xu ly 30 announce dong thoi, khong mat peer nao, khong loi."""
        _, m = self.c.make_file(100)
        http_json(f"{self.c.tr}/register", m)
        body = lambda i: {"file_id": m["file_id"], "peer_id": f"P{i}", "addr": f"http://h:{i}", "chunks": [0, 1]}
        with ThreadPoolExecutor(30) as ex:
            list(ex.map(lambda i: http_json(f"{self.c.tr}/announce", body(i)), range(30)))
        self.assertEqual(len(http_json(f"{self.c.tr}/peers/{m['file_id']}")["peers"]), 30)

    def test_c2_hai_peer_tai_dong_thoi_cung_file(self):
        """Hai peer tai dong thoi va trao doi chunk cho nhau; trang thai cuoi: ca hai co file dung."""
        path, m = self.c.make_file(2048)
        self.c.seed("A", path, m["file_id"], "--slow", "0.05", "--upload-slots", "2")
        c = self.c.peer("C", "get", m["file_id"], "--exit-when-done", "--slow", "0.02")
        d = self.c.peer("D", "get", m["file_id"], "--exit-when-done", "--slow", "0.02")
        c.wait(60); d.wait(60)
        self.assertTrue(self.c.output_ok("C", m))
        self.assertTrue(self.c.output_ok("D", m))
        self.assertTrue("tu D" in self.c.log("C") or "tu C" in self.c.log("D"), "hai peer khong trao doi chunk")


if __name__ == "__main__":
    unittest.main()
