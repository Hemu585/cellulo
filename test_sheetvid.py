"""Offline tests: no network, no Google account. Run with: python -m unittest"""
import base64
import hashlib
import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sheetvid import BATCH, CHUNK, assemble, download, split_chunks, upload

_range = range  # the fake's methods must take a parameter named `range`, like the real API


def stored(data, size=10):
    """Meta and rows as the sheet would hold them for `data`."""
    chunks = split_chunks(base64.b64encode(data).decode(), size)
    meta = {
        "filename": "a.mp4",
        "mime_type": "video/mp4",
        "byte_size": len(data),
        "chunk_count": len(chunks),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return meta, [[i, c] for i, c in enumerate(chunks, 1)]


class FakeSheets:
    """In-memory stand-in for the Sheets service: only the calls sheetvid makes."""

    def __init__(self, rows=1000):
        self.tabs = {"meta": {}, "chunks": {}}  # tab -> {(row, column): value}
        self.rows = rows  # grid height of the chunks tab

    def batchUpdate(self, spreadsheetId, body):
        for request in body["requests"]:
            assert request["appendDimension"]["sheetId"] == 7
            self.rows += request["appendDimension"]["length"]
        return self._call({})

    def spreadsheets(self):
        return self

    def values(self):
        return self

    @staticmethod
    def _call(result):
        return SimpleNamespace(execute=lambda num_retries=0: result)

    def create(self, body, fields):
        return self._call({"spreadsheetId": "new-sheet"})

    def batchClear(self, spreadsheetId, body):
        for tab in body["ranges"]:
            self.tabs[tab].clear()
        return self._call({})

    def update(self, spreadsheetId, range, valueInputOption, body):
        assert valueInputOption == "RAW"
        tab, first = re.fullmatch(r"(\w+)!A(\d+)", range).groups()
        for r, row in enumerate(body["values"], int(first)):
            assert tab != "chunks" or r <= self.rows, "write exceeds grid limits"
            for c, value in enumerate(row):
                assert not isinstance(value, str) or len(value) <= 50_000
                self.tabs[tab][r, c] = value
        return self._call({})

    def get(self, spreadsheetId, range=None, valueRenderOption=None, fields=None):
        if fields:  # spreadsheets().get: tab properties
            tabs = [("meta", 3, 1000), ("chunks", 7, self.rows)]
            return self._call({"sheets": [
                {"properties": {"title": t, "sheetId": i, "gridProperties": {"rowCount": n}}} for t, i, n in tabs
            ]})
        assert valueRenderOption == "UNFORMATTED_VALUE"
        tab, first, column, end = re.fullmatch(r"(\w+)!A(\d+):([AB])(\d*)", range).groups()
        cells = self.tabs[tab]
        last = int(end) if end else max((r for r, _ in cells), default=0)
        rows = []
        for r in _range(int(first), last + 1):
            row = [cells.get((r, c), "") for c in _range("AB".index(column) + 1)]
            while row and row[-1] == "":
                row.pop()  # like the real API: trailing empty cells are dropped
            rows.append(row)
        while rows and not rows[-1]:
            rows.pop()  # and trailing empty rows
        return self._call({"values": rows} if rows else {})


class SplitTest(unittest.TestCase):
    def test_split_rejoins_and_respects_size(self):
        text = "x" * (2 * CHUNK + 1)
        chunks = split_chunks(text)
        self.assertEqual([len(c) for c in chunks], [CHUNK, CHUNK, 1])
        self.assertEqual("".join(chunks), text)


class AssembleTest(unittest.TestCase):
    def setUp(self):
        self.data = os.urandom(500)
        self.meta, self.rows = stored(self.data)

    def test_restores_from_shuffled_rows(self):
        random.shuffle(self.rows)
        self.assertEqual(assemble(self.meta, self.rows), self.data)

    def test_ignores_blank_rows(self):
        self.assertEqual(assemble(self.meta, self.rows + [[], ["", ""]]), self.data)

    def test_rejects_missing_chunk(self):
        del self.rows[3]
        with self.assertRaisesRegex(ValueError, r"missing chunks.*\[4\]"):
            assemble(self.meta, self.rows)

    def test_rejects_duplicate_chunk(self):
        with self.assertRaisesRegex(ValueError, "duplicate chunk 2"):
            assemble(self.meta, self.rows + [self.rows[1]])

    def test_rejects_extra_chunk(self):
        with self.assertRaisesRegex(ValueError, "unexpected chunks"):
            assemble(self.meta, self.rows + [[len(self.rows) + 1, "AAAA"]])

    def test_rejects_chunk_without_data(self):
        self.rows[0] = [1]
        with self.assertRaisesRegex(ValueError, "chunk 1 has no data"):
            assemble(self.meta, self.rows)

    def test_rejects_bad_chunk_number(self):
        self.rows[0][0] = "one"
        with self.assertRaisesRegex(ValueError, "invalid chunk number"):
            assemble(self.meta, self.rows)

    def test_rejects_altered_data(self):
        first = self.rows[0][1]
        self.rows[0][1] = ("B" if first[0] == "A" else "A") + first[1:]
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            assemble(self.meta, self.rows)

    def test_rejects_invalid_base64(self):
        self.rows[0][1] = "!" + self.rows[0][1][1:]
        with self.assertRaisesRegex(ValueError, "not valid Base64"):
            assemble(self.meta, self.rows)

    def test_rejects_wrong_size(self):
        self.meta["byte_size"] += 1
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            assemble(self.meta, self.rows)

    def test_rejects_incomplete_meta(self):
        del self.meta["sha256"]
        with self.assertRaisesRegex(ValueError, "no complete upload"):
            assemble(self.meta, self.rows)


class RoundTripTest(unittest.TestCase):
    """upload then download through the fake service, with a file big enough to span two calls."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "clip.mp4"
        self.data = os.urandom(800_000)
        self.path.write_bytes(self.data)
        self.svc = FakeSheets()
        self.sheet_id, self.meta = upload(self.svc, self.path)

    def test_round_trip(self):
        self.assertGreater(self.meta["chunk_count"], BATCH)
        meta, data = download(self.svc, self.sheet_id)
        self.assertEqual(data, self.data)
        self.assertEqual(meta["filename"], "clip.mp4")
        self.assertEqual(meta["mime_type"], "video/mp4")
        self.assertEqual(meta["sha256"], hashlib.sha256(self.data).hexdigest())

    def test_deleted_row_is_rejected(self):
        cells = self.svc.tabs["chunks"]
        del cells[5, 0], cells[5, 1]
        with self.assertRaisesRegex(ValueError, "missing chunks"):
            download(self.svc, self.sheet_id)

    def test_duplicated_row_is_rejected(self):
        cells = self.svc.tabs["chunks"]
        last = max(r for r, _ in cells)
        cells[last + 1, 0], cells[last + 1, 1] = cells[3, 0], cells[3, 1]
        with self.assertRaisesRegex(ValueError, "duplicate chunk 2"):
            download(self.svc, self.sheet_id)

    def test_interrupted_upload_is_rejected(self):
        self.svc.tabs["meta"].clear()
        with self.assertRaisesRegex(ValueError, "no complete upload"):
            download(self.svc, self.sheet_id)

    def test_grows_tab_when_file_needs_more_rows(self):
        svc = FakeSheets(rows=5)
        sheet_id, meta = upload(svc, self.path)
        self.assertEqual(svc.rows, meta["chunk_count"] + 1)
        self.assertEqual(download(svc, sheet_id)[1], self.data)

    def test_smaller_file_replaces_larger(self):
        small = os.urandom(50_000)
        self.path.write_bytes(small)
        upload(self.svc, self.path, self.sheet_id)
        self.assertEqual(download(self.svc, self.sheet_id)[1], small)


if __name__ == "__main__":
    unittest.main()
