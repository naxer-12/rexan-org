import os
import sys
import unittest
import threading
import time
import requests
import uvicorn

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from server import app

TEST_PORT = 8991
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

class TestRexanServer(unittest.TestCase):
    server = None
    server_thread = None

    @classmethod
    def setUpClass(cls):
        config = uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        
        # Wait up to 5 seconds for server to be ready
        for _ in range(50):
            try:
                r = requests.get(f"{BASE_URL}/api/config", timeout=1)
                if r.status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True

    def test_01_config(self):
        resp = requests.get(f"{BASE_URL}/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("frames_source"), "youtube")

    def test_02_stats(self):
        resp = requests.get(f"{BASE_URL}/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data.get("videos", 0), 6000)
        self.assertGreaterEqual(data.get("comments", 0), 30000)
        self.assertEqual(data.get("areas"), 16)
        self.assertEqual(data.get("categories"), 150)

    def test_03_browse(self):
        resp = requests.get(f"{BASE_URL}/api/browse")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 16)
        self.assertTrue(any(a["id"] == "software" for a in data))

    def test_04_playlists(self):
        resp = requests.get(f"{BASE_URL}/api/playlists")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data), 20)
        slugs = [p["slug"] for p in data]
        self.assertIn("hn-canon", slugs)

    def test_05_playlist_detail(self):
        resp = requests.get(f"{BASE_URL}/api/playlist?slug=hn-canon")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("title"), "The HN canon")
        self.assertTrue(len(data.get("videos", [])) > 0)

    def test_06_video_detail(self):
        resp = requests.get(f"{BASE_URL}/api/video?vid=fNk_zzaMoSs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("video", data)
        self.assertIn("comments", data)
        self.assertEqual(data["video"]["vid"], "fNk_zzaMoSs")
        self.assertGreaterEqual(len(data["comments"]), 1)

    def test_07_docs(self):
        resp = requests.get(f"{BASE_URL}/api/docs?vids=fNk_zzaMoSs,jbkSRLYSojo")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["vid"], "fNk_zzaMoSs")
        self.assertEqual(data[1]["vid"], "jbkSRLYSojo")

    def test_08_related(self):
        resp = requests.get(f"{BASE_URL}/api/related?vid=fNk_zzaMoSs&n=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data), 0)

    def test_09_feed(self):
        resp = requests.get(f"{BASE_URL}/api/feed?seed=123&n=12")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 12)
        for item in data:
            self.assertIn("vid", item)
            self.assertIn("source", item)
            self.assertIn("reason", item)

    def test_10_feed_with_likes_and_dislikes(self):
        resp = requests.get(f"{BASE_URL}/api/feed?like=fNk_zzaMoSs&dislike=jbkSRLYSojo&seed=456&n=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        vids = [item["vid"] for item in data]
        self.assertNotIn("jbkSRLYSojo", vids)

    def test_11_list_all(self):
        resp = requests.get(f"{BASE_URL}/api/list?offset=0&n=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 10)

    def test_12_list_filtered(self):
        resp = requests.get(f"{BASE_URL}/api/list?cat=functional-programming&n=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data), 0)

    def test_13_list_dur_xlong(self):
        resp = requests.get(f"{BASE_URL}/api/list?dur=xlong&n=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for v in data:
            self.assertGreater(v.get("duration_s", 0), 3600)

    def test_14_search_fts(self):
        resp = requests.get(f"{BASE_URL}/api/search?q=lisp")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)

    def test_15_export(self):
        resp = requests.get(f"{BASE_URL}/api/export")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("name"), "rexan-data")
        self.assertIn("files", data)

    def test_16_download(self):
        resp = requests.get(f"{BASE_URL}/download/DATA.md")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Rexan", resp.text)

    def test_17_spa_frontend_pages(self):
        for route in ["/", "/watch/fNk_zzaMoSs", "/about", "/data", "/categories", "/playlists", "/browse", "/settings", "/add", "/extension"]:
            resp = requests.get(f"{BASE_URL}{route}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            self.assertIn("Rexan", resp.text)

    def test_18_fetch_meta(self):
        resp = requests.get(f"{BASE_URL}/api/video/fetch-meta?url=https://www.youtube.com/watch?v=fNk_zzaMoSs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("vid"), "fNk_zzaMoSs")
        self.assertIn("title", data)
        self.assertIn("tags", data)
        self.assertIn("categories", data)
        self.assertTrue(len(data.get("tags", [])) > 0)
        self.assertTrue(data.get("exists"))

    def test_19_dislikes_endpoint(self):
        resp = requests.get(f"{BASE_URL}/api/video/dislikes?vid=fNk_zzaMoSs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("likes", data)
        self.assertIn("dislikes", data)

    def test_20_add_video_and_search(self):
        test_payload = {
            "url": "https://www.youtube.com/watch?v=testVid123X",
            "title": "Quantum Computing Fundamentals by David Deutsch",
            "channel": "Quantum Institute",
            "summary": "An introduction to quantum computation and many worlds interpretation.",
            "tags": ["quantum", "computation", "physics"],
            "playlist_slug": "hn-canon",
            "custom_note": "A must-watch quantum physics lecture."
        }
        resp = requests.post(f"{BASE_URL}/api/video/add", json=test_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("vid"), "testVid123X")

        # Verify video can now be fetched via /api/video
        vid_resp = requests.get(f"{BASE_URL}/api/video?vid=testVid123X")
        self.assertEqual(vid_resp.status_code, 200)
        vid_data = vid_resp.json()
        self.assertEqual(vid_data["video"]["title"], test_payload["title"])
        self.assertGreaterEqual(len(vid_data["comments"]), 1)

        # Verify searchable via FTS5
        search_resp = requests.get(f"{BASE_URL}/api/search?q=quantum+deutsch")
        self.assertEqual(search_resp.status_code, 200)
        search_data = search_resp.json()
        vids = [v["vid"] for v in search_data.get("results", [])]
        self.assertIn("testVid123X", vids)

        # Clean up test video
        import sqlite3, json
        conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "rexan.db"))
        cur = conn.cursor()
        cur.execute("DELETE FROM videos WHERE vid = ?", ("testVid123X",))
        cur.execute("DELETE FROM videos_fts WHERE vid = ?", ("testVid123X",))
        cur.execute("DELETE FROM video_categories WHERE vid = ?", ("testVid123X",))
        cur.execute("DELETE FROM mentions WHERE vid = ?", ("testVid123X",))
        conn.commit()
        conn.close()

        pl_file = os.path.join(BASE_DIR, "data", "playlists.json")
        with open(pl_file, "r") as f:
            pls = json.load(f)
        for p in pls:
            p["videos"] = [v for v in p.get("videos", []) if v.get("vid") != "testVid123X"]
            p["count"] = len(p["videos"])
        with open(pl_file, "w") as f:
            json.dump(pls, f, indent=2)

if __name__ == "__main__":
    unittest.main()
