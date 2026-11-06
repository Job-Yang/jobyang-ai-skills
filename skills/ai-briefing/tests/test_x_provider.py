import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import x_provider as xp  # noqa: E402

PROFILE_DIR = os.path.join(ROOT, "tests", "fixtures")


# A fake vendor shaped like the astra-x / RapidAPI-style response so the test
# proves normalization against a *different* schema without any network/key.
FAKE_ITEMS = {
    "code": 0,
    "msg": "success",
    "data": {
        "has_more": False,
        "items": [
            {
                "id": "2055312187124744476",
                "item_url": "https://x.com/OpenAI/status/2055312187124744476",
                "title": "Launching a new agent benchmark today.",
                "description": "Launching a new agent benchmark today.",
                "publish_time": "2026-10-19T20:06:12+00:00",
                "statistics": {"like_count": 21623, "share_count": 2598,
                               "comment_count": 1575, "view_count": 4358312},
                "author": {"screen_name": "OpenAI", "nickname": "OpenAI"},
            },
            {
                "id": "2055312187124744477",
                "title": "Second post without url field",
                "publish_time": "2026-10-19T21:00:00+00:00",
                "author": {"screen_name": "sama", "nickname": "Sam Altman"},
            },
        ],
    },
}

PROFILE = {
    "name": "fake-vendor",
    "mode": "http",
    "headers": {"x-test-key": "$TEST_X_KEY"},
    "actions": {
        "search_posts": {"url": "http://127.0.0.1:{port}/x/search_posts",
                         "method": "POST", "body": {"search_type": "Top"}},
        "user_posts": {"url": "http://127.0.0.1:{port}/x/get_user_info",
                       "method": "POST", "body": {"post_count": 20}},
        "post_detail": {"url": "http://127.0.0.1:{port}/x/get_posts_info",
                        "method": "POST", "body": {}},
    },
    "maps": {
        "items_path": "data.items",
        "id": "id", "url": "item_url",
        "text": "title|description|text", "created_at": "publish_time|created_at",
        "author_path": "author",
        "author_handle_path": "screen_name", "author_name_path": "nickname|name",
        "stats": "statistics",
    },
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.path.endswith("/search_posts"):
            assert body.get("query") == "agent"
        if self.path.endswith("/get_user_info"):
            assert body.get("id") == "sama"
        if self.path.endswith("/get_posts_info"):
            assert body.get("tweet_ids") == "111,222"
        self.wfile.write(json.dumps(FAKE_ITEMS).encode())


def start_server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


class TestXProvider(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.port = start_server()
        prof = json.loads(json.dumps(PROFILE).replace("{port}", str(cls.port)))
        cls.profile_path = os.path.join(PROFILE_DIR, "_tmp_profile.json")
        with open(cls.profile_path, "w") as f:
            json.dump(prof, f)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        os.remove(cls.profile_path)

    def setUp(self):
        os.environ["TEST_X_KEY"] = "secret123"

    def _prof(self):
        with open(self.profile_path) as f:
            return json.load(f)

    def test_search_normalizes_vendor_schema(self):
        items = xp.call_action(self._prof(), "search_posts", query="agent", count=10)
        self.assertEqual(len(items), 2)
        a = items[0]
        self.assertEqual(a["id"], "2055312187124744476")
        self.assertEqual(a["url"], "https://x.com/OpenAI/status/2055312187124744476")
        self.assertEqual(a["author"]["handle"], "OpenAI")
        self.assertEqual(a["author"]["name"], "OpenAI")
        self.assertEqual(a["metrics"]["likes"], 21623)
        self.assertEqual(a["metrics"]["views"], 4358312)
        self.assertIn("agent benchmark", a["text"])

    def test_missing_url_is_reconstructed_from_handle_and_id(self):
        items = xp.call_action(self._prof(), "user_posts", handle="sama")
        b = items[1]
        self.assertEqual(b["url"], "https://x.com/sama/status/2055312187124744477")

    def test_post_detail_accepts_urls_and_ids(self):
        ids = xp.split_posts("111,https://x.com/OpenAI/status/222")
        self.assertEqual(ids, "111,222")
        items = xp.call_action(self._prof(), "post_detail", posts=ids)
        self.assertEqual(items[0]["id"], "2055312187124744476")

    def test_env_var_injected_into_headers(self):
        h = xp._env({"x-test-key": "$TEST_X_KEY"})
        self.assertEqual(h["x-test-key"], "secret123")

    def test_stdin_mode_accepts_host_read_items(self):
        p = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "x_provider.py"),
             "search_posts", "--stdin"],
            input=json.dumps({"items": [
                {"id": "9", "title": "hi from host page reader",
                 "url": "https://x.com/k/status/9", "author": {"screen_name": "k"}}]}),
            capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(out["items"][0]["text"], "hi from host page reader")
        self.assertEqual(out["provider"], "stdin")

    def test_missing_profile_fails_structured(self):
        p = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "x_provider.py"),
             "search_posts", "--query", "x"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 2)
        self.assertIn("error", p.stderr)


if __name__ == "__main__":
    unittest.main()
