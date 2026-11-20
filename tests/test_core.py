"""Test don vi: python -m unittest discover tests"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from common import make_meta, sha  # noqa: E402
from peer import parse_range  # noqa: E402


class T(unittest.TestCase):
    def test_meta(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(os.urandom(150 * 1024)); name = f.name
        m = make_meta(name, "http://x", 64 * 1024)
        self.assertEqual((m["num_chunks"], m["size"]), (3, 150 * 1024))
        with open(name, "rb") as f:
            self.assertEqual(m["chunk_hashes"][0], sha(f.read(64 * 1024)))
        os.remove(name)

    def test_corrupt_detected(self):
        d = os.urandom(1000)
        self.assertNotEqual(sha(d), sha(bytes([d[0] ^ 0xFF]) + d[1:]))

    def test_parse_range(self):
        self.assertEqual(parse_range("0-2,7"), {0, 1, 2, 7})


if __name__ == "__main__":
    unittest.main()
