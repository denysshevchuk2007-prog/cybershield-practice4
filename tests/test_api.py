"""End-to-end tests for the local HTTP API using only Python's stdlib."""

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, urlopen

os.environ["CYBERSHIELD_ADMIN_USER"] = "ci-admin"
os.environ["CYBERSHIELD_ADMIN_PASSWORD"] = "ci-only-test-password"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend  # noqa: E402


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.anchors = []
        self.resources = []
        self.forms = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "a":
            self.anchors.append(attributes.get("href", ""))
        if tag in ("script", "link"):
            resource = attributes.get("src") or attributes.get("href", "")
            if resource and not resource.startswith(("http:", "https:", "mailto:", "#")):
                self.resources.append(resource)
        if tag == "form":
            self.forms.append(attributes)


class CyberShieldApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        backend.DB_PATH = Path(self.temp_dir.name) / "messages.sqlite3"
        backend.initialize_db()
        self.start_server()

    def start_server(self):
        self.server = backend.LoggingHTTPServer(("127.0.0.1", 0), backend.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def tearDown(self):
        self.stop_server()
        self.temp_dir.cleanup()

    def request_json(self, method, path, body=None, cookie=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if cookie:
            headers["Cookie"] = cookie
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read()), response.headers
        except HTTPError as error:
            status, headers = error.code, error.headers
            body = json.loads(error.read())
            error.close()
            return status, body, headers

    def login(self):
        status, _, headers = self.request_json(
            "POST", "/api/login", {"username": "ci-admin", "password": "ci-only-test-password"}
        )
        self.assertEqual(status, 200)
        return headers.get("Set-Cookie").split(";", 1)[0]

    def test_valid_form_is_saved_and_survives_server_restart(self):
        payload = {"name": "Test User", "email": "test@example.com", "message": "A test message."}
        status, result, _ = self.request_json("POST", "/api/messages", payload)
        self.assertEqual(status, 201)
        self.assertTrue(result["ok"])

        self.stop_server()
        backend.initialize_db()
        self.start_server()
        status, data, _ = self.request_json("GET", "/api/messages", cookie=self.login())
        self.assertEqual(status, 200)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["email"], payload["email"])

    def test_invalid_form_is_rejected_by_server(self):
        status, result, _ = self.request_json(
            "POST", "/api/messages", {"name": "x", "email": "not-an-email", "message": "no"}
        )
        self.assertEqual(status, 400)
        self.assertIn("name", result["fields"])
        self.assertIn("email", result["fields"])
        self.assertIn("message", result["fields"])

    def test_message_list_and_delete_require_admin_login(self):
        status, _, _ = self.request_json(
            "POST", "/api/messages", {"name": "Test User", "email": "test@example.com", "message": "A test message."}
        )
        self.assertEqual(status, 201)
        status, _, _ = self.request_json("GET", "/api/messages")
        self.assertEqual(status, 401)

        cookie = self.login()
        status, data, _ = self.request_json("GET", "/api/messages", cookie=cookie)
        self.assertEqual(status, 200)
        message_id = data["messages"][0]["id"]
        status, result, _ = self.request_json("DELETE", f"/api/messages/{message_id}", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])

    def test_home_and_admin_pages_are_served(self):
        for route, expected in (("/", "CyberShield"), ("/messages", "Повідомлення")):
            with urlopen(self.base_url + route, timeout=3) as response:
                self.assertEqual(response.status, 200)
                html = response.read().decode("utf-8")
                self.assertIn(expected, html)
                page = PageLinks()
                page.feed(html)
                for href in page.anchors:
                    if href.startswith("#"):
                        self.assertIn(href[1:], page.ids, f"Broken in-page link: {href} on {route}")
                for resource in page.resources:
                    with urlopen(self.base_url + "/" + resource.lstrip("/"), timeout=3) as asset:
                        self.assertEqual(asset.status, 200, f"Missing page asset: {resource}")
                if route == "/":
                    contact = next(form for form in page.forms if form.get("id") == "contact-form")
                    self.assertEqual(contact.get("method", "get").lower(), "post")
                    self.assertEqual(contact.get("action"), "/api/messages")


if __name__ == "__main__":
    unittest.main()
