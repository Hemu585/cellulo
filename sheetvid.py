"""Store one small file (video or image) in Google Sheets cells as Base64 text, and restore it."""
import argparse
import base64
import hashlib
import mimetypes
import os
import sys
from pathlib import Path

CHUNK = 40_000  # characters per cell; Sheets rejects cells over 50,000
BATCH = 25  # rows per API call: about 1 MB, under Google's recommended 2 MB payload
MAX_MB = 100  # Google refuses a spreadsheet at about 110 MB of file and then blocks all edits to it (measured Nov 2026)
RETRIES = 6  # the client library retries 429 and 5xx with randomised exponential backoff
HOME = Path.home() / ".sheetvid"  # credentials live outside the project folder
SCOPES = ["https://www.googleapis.com/auth/drive.file"]  # only spreadsheets this tool created
META_KEYS = ["filename", "mime_type", "byte_size", "chunk_count", "sha256"]


def split_chunks(text, size=CHUNK):
    return [text[i:i + size] for i in range(0, len(text), size)]


def read_meta(meta):
    """Return (chunk_count, byte_size), or raise ValueError if the upload never finished."""
    absent = [k for k in META_KEYS if meta.get(k) in (None, "")]
    if absent:
        raise ValueError(f"no complete upload found (meta is missing: {', '.join(absent)})")
    try:
        return int(meta["chunk_count"]), int(meta["byte_size"])
    except (TypeError, ValueError):
        raise ValueError("meta is corrupt: chunk_count and byte_size must be whole numbers")


def assemble(meta, rows):
    """Rebuild the original bytes from sheet rows, or raise ValueError saying what is wrong."""
    count, size = read_meta(meta)

    chunks = {}
    for row in rows:
        if not any(cell != "" for cell in row):
            continue  # blank row
        number = row[0]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or number != int(number):
            raise ValueError(f"invalid chunk number: {number!r}")
        number = int(number)
        if number in chunks:
            raise ValueError(f"duplicate chunk {number}")
        if len(row) < 2 or not isinstance(row[1], str) or not row[1]:
            raise ValueError(f"chunk {number} has no data")
        chunks[number] = row[1]

    expected = set(range(1, count + 1))
    missing = sorted(expected - chunks.keys())
    if missing:
        raise ValueError(f"missing chunks ({len(missing)} of {count}): {missing[:10]}")
    extra = sorted(chunks.keys() - expected)
    if extra:
        raise ValueError(f"unexpected chunks beyond {count}: {extra[:10]}")

    try:
        data = base64.b64decode("".join(chunks[i] for i in range(1, count + 1)), validate=True)
    except ValueError as err:
        raise ValueError(f"chunk data is not valid Base64: {err}")
    if len(data) != size:
        raise ValueError(f"size mismatch: restored {len(data)} bytes, expected {size}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != meta["sha256"]:
        raise ValueError(f"SHA-256 mismatch: restored {digest}, expected {meta['sha256']}")
    return data


def get_service():
    # imported here so the offline tests run without touching Google libraries
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    cred_file, token_file = HOME / "credentials.json", HOME / "token.json"
    creds = Credentials.from_authorized_user_file(token_file, SCOPES) if token_file.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None  # Testing-status sign-ins expire after 7 days: sign in again
    if not creds or not creds.valid:
        if not cred_file.exists():
            sys.exit(f"ERROR: {cred_file} not found. Follow docs/AUTH_SETUP.md first.")
        creds = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES).run_local_server(port=0)
    token_file.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def upload(svc, path, sheet_id=None):
    data = Path(path).read_bytes()
    name = Path(path).name
    chunks = split_chunks(base64.b64encode(data).decode("ascii"))
    meta = [
        ["filename", name],
        ["mime_type", mimetypes.guess_type(name)[0] or "application/octet-stream"],
        ["byte_size", len(data)],
        ["chunk_count", len(chunks)],
        ["sha256", hashlib.sha256(data).hexdigest()],
    ]
    sheets = svc.spreadsheets()
    if not sheet_id:
        body = {
            "properties": {"title": f"Cellulo - {name}"},
            "sheets": [{"properties": {"title": "meta"}}, {"properties": {"title": "chunks"}}],
        }
        sheet_id = sheets.create(body=body, fields="spreadsheetId").execute(num_retries=RETRIES)["spreadsheetId"]

    def write(cell, rows):
        # RAW: Sheets must never read a chunk starting with + or = as a formula
        sheets.values().update(
            spreadsheetId=sheet_id, range=cell, valueInputOption="RAW", body={"values": rows}
        ).execute(num_retries=RETRIES)

    # clear first so rows from an older, longer file cannot linger
    sheets.values().batchClear(spreadsheetId=sheet_id, body={"ranges": ["meta", "chunks"]}).execute(num_retries=RETRIES)
    rows = [["chunk", "data"]] + [[i, c] for i, c in enumerate(chunks, 1)]

    # a new tab has 1,000 rows; writing past the grid is an error, so grow it first
    tabs = sheets.get(spreadsheetId=sheet_id, fields="sheets.properties").execute(num_retries=RETRIES)["sheets"]
    tab = next((t["properties"] for t in tabs if t["properties"]["title"] == "chunks"), None)
    if tab is None:
        raise ValueError("the spreadsheet has no 'chunks' tab; upload without --sheet to create a fresh one")
    short = len(rows) - tab["gridProperties"]["rowCount"]
    if short > 0:
        grow = {"appendDimension": {"sheetId": tab["sheetId"], "dimension": "ROWS", "length": short}}
        sheets.batchUpdate(spreadsheetId=sheet_id, body={"requests": [grow]}).execute(num_retries=RETRIES)

    for start in range(0, len(rows), BATCH):
        write(f"chunks!A{start + 1}", rows[start:start + BATCH])
        print(f"  wrote rows {start + 1}-{min(start + BATCH, len(rows))} of {len(rows)}")
    write("meta!A1", meta)  # last: an interrupted upload leaves no meta, so download refuses it
    return sheet_id, dict(meta)


def download(svc, sheet_id):
    def get(cells):
        return svc.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=cells, valueRenderOption="UNFORMATTED_VALUE"
        ).execute(num_retries=RETRIES).get("values", [])

    meta = {row[0]: row[1] for row in get("meta!A1:B5") if len(row) == 2}
    read_meta(meta)  # refuse an unfinished upload before fetching what may be a hundred megabytes
    last = len(get("chunks!A2:A")) + 1  # sheet row of the last numbered chunk
    rows = []
    for start in range(2, last + 1, BATCH):
        rows += get(f"chunks!A{start}:B{min(start + BATCH - 1, last)}")
    return meta, assemble(meta, rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("upload", help="store a file in a spreadsheet")
    up.add_argument("file")
    up.add_argument("--sheet", help="spreadsheet ID from an earlier upload (replaces its file); omit to create a new one")
    up.add_argument("--max-mb", type=float, default=1, help=f"size cap in MB (default 1, at most {MAX_MB})")
    down = sub.add_parser("download", help="restore the file from a spreadsheet")
    down.add_argument("--sheet", required=True, help="spreadsheet ID printed by upload")
    down.add_argument("-o", "--output", help="where to save (default: the original filename)")
    args = parser.parse_args(argv)

    from googleapiclient.errors import HttpError

    try:
        if args.command == "upload":
            path = Path(args.file)
            if not path.is_file():
                sys.exit(f"ERROR: {path} is not a file")
            if not 0 < args.max_mb <= MAX_MB:
                sys.exit(f"ERROR: --max-mb must be above 0 and at most {MAX_MB}")
            size = path.stat().st_size
            if size == 0:
                sys.exit("ERROR: the file is empty")
            if size > args.max_mb * 1_000_000:
                sys.exit(f"ERROR: {size:,} bytes is over the {args.max_mb:g} MB cap. Raise it with --max-mb (at most {MAX_MB}).")
            sheet_id, meta = upload(get_service(), path, args.sheet)
            print(f"Stored {meta['filename']} ({meta['byte_size']:,} bytes, {meta['chunk_count']} chunks)")
            print(f"SHA-256:  {meta['sha256']}")
            print(f"Sheet:    https://docs.google.com/spreadsheets/d/{sheet_id}")
            print(f"Restore:  python sheetvid.py download --sheet {sheet_id}")
        else:
            meta, data = download(get_service(), args.sheet)
            name = args.output or os.path.basename(str(meta["filename"]))
            if not name or Path(name).exists():
                sys.exit(f"ERROR: {name!r} already exists or is not a usable name. Choose another with -o.")
            Path(name).write_bytes(data)
            print(f"Restored {name} ({len(data):,} bytes, {meta['mime_type']})")
            print(f"SHA-256 stored:   {meta['sha256']}")
            print(f"SHA-256 restored: {hashlib.sha256(data).hexdigest()}")
            print("Checksums match.")
    except ValueError as err:
        sys.exit(f"ERROR: {err}. Nothing was written.")
    except HttpError as err:
        hint = " The spreadsheet does not exist, or was not created by this tool." if err.status_code in (403, 404) else ""
        sys.exit(f"ERROR: Google Sheets returned HTTP {err.status_code}: {str(err.reason).rstrip('.')}.{hint}")


if __name__ == "__main__":
    main()
