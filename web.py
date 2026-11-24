"""Local web page that restores a file from a Google Sheets link.

Run:  python web.py   then open http://127.0.0.1:8765
It signs in as you (same credentials as cellulo.py), so it only listens on this computer.
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from cellulo import download, get_service, read_meta

PORT = 8765
PAGE = Path(__file__).with_name("web") / "index.html"
# the same security headers the hosted site sends, kept in one place
HEADERS = [(h["key"], h["value"]) for h in json.loads(PAGE.with_name("vercel.json").read_text())["headers"][0]["headers"]]
FILES = {"app.js": "text/javascript; charset=utf-8", "favicon.svg": "image/svg+xml", "icon-32.png": "image/png", "icon-192.png": "image/png", "apple-touch-icon.png": "image/png"}


def sheet_id_from(text):
    """Accept a full Google Sheets link or a bare spreadsheet ID."""
    text = str(text).strip()
    match = re.search(r"/spreadsheets/d/([\w-]+)", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"[\w-]{20,}", text):
        return text
    raise ValueError("That does not look like a Google Sheets link")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in HEADERS + list(headers):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def fail(self, status, message):
        self.reply(status, json.dumps({"error": message}).encode(), "application/json")

    def local(self):
        # refuse other host names: a hostile site that points its own name at 127.0.0.1 could otherwise read restored files
        port = self.server.server_address[1]
        if self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            return True
        self.fail(403, "This page only answers on this computer")
        return False

    def do_GET(self):
        if not self.local():
            return
        name = self.path.split("?")[0].lstrip("/")
        if self.path == "/":
            self.reply(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif name in FILES:   # fixed list, so no path from the request ever reaches the file system
            self.reply(200, PAGE.with_name(name).read_bytes(), FILES[name])
        else:
            self.fail(404, "Not found")

    def do_POST(self):
        if not self.local():
            return
        if self.path != "/api/restore":
            return self.fail(404, "Not found")
        # browsers always send Origin on a cross-site POST; refuse other sites so they cannot start restores here
        if self.headers.get("Origin", f"http://{self.headers['Host']}") != f"http://{self.headers['Host']}":
            return self.fail(403, "Requests from other sites are refused")
        from googleapiclient.errors import HttpError

        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= 4096:
                return self.fail(413, "Request too large")
            sheet = sheet_id_from(json.loads(self.rfile.read(length))["sheet"])
            meta, data = download(get_service(), sheet)
        except (ValueError, KeyError, TypeError) as err:
            message = str(err)
            return self.fail(422, message[:1].upper() + message[1:] + ("" if message.endswith(".") else "."))
        except HttpError as err:
            if err.status_code in (400, 403, 404):
                return self.fail(404, "Google could not open that spreadsheet. Check the link; this page only opens sheets made by this tool.")
            return self.fail(502, f"Google Sheets returned HTTP {err.status_code}: {err.reason}")
        except SystemExit as err:  # get_service() exits when credentials are missing
            return self.fail(500, str(err))
        name = os.path.basename(str(meta["filename"])) or "restored"
        # always octet-stream: the stored MIME type is untrusted, the page decides how to show it
        self.reply(200, data, "application/octet-stream", [
            ("X-Cellulo-Name", quote(name)),
            ("X-Cellulo-Mime", quote(str(meta["mime_type"]))),
            ("X-Cellulo-Sha256", str(meta["sha256"])),
            ("X-Cellulo-Chunks", str(read_meta(meta)[0])),
        ])


if __name__ == "__main__":
    print(f"Cellulo: http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
