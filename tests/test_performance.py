"""1 thi nghiem hieu nang (muc 9 cua de). Bang so lieu day du: python scripts/benchmark.py"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from helpers import Cluster  # noqa: E402


class TestPerformance(unittest.TestCase):
    def run_case(self, seeders):
        c = Cluster()
        try:
            c.tracker()
            path, m = c.make_file(2048)  # 32 chunk
            for k in range(seeders):  # moi seeder chi 1 luot upload cung luc, 30 ms/chunk
                c.seed(f"S{k}", path, m["file_id"], "--slow", "0.03", "--upload-slots", "1")
            c.peer("C", "get", m["file_id"], "--exit-when-done", "--workers", "4").wait(60)
            self.assertTrue(c.output_ok("C", m))
            return c.dl_time("C")
        finally:
            c.stop()

    def test_p1_nhieu_nguon_tai_nhanh_hon(self):
        t1, t3 = self.run_case(1), self.run_case(3)
        print(f"\n  1 nguon: {t1:.2f}s | 3 nguon: {t3:.2f}s | nhanh hon {t1 / t3:.1f} lan")
        self.assertLess(t3, t1)


if __name__ == "__main__":
    unittest.main()
