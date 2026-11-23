# sheets-video-store

Proof of concept: store a small video or image **inside Google Sheets cells** as Base64 text, then restore the identical file. No Google Drive link; the file's bytes live in the cells.

## How it works

- The file is Base64-encoded and cut into chunks of 40,000 characters, one chunk per cell.
- Tab `chunks` holds the chunk number and text. Tab `meta` holds filename, MIME type, byte size, chunk count and SHA-256.
- Download puts the chunks back in order, decodes them, and checks size and SHA-256 before writing anything.

Details: [docs/DESIGN.md](docs/DESIGN.md).

## Setup (once)

1. Python 3.10 or newer, then:

```powershell
pip install -r requirements.txt
```

2. Create your Google sign-in file by following [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md). It ends up at `C:\Users\<you>\.sheetvid\credentials.json`, outside this folder.

## Use

Upload. Creates a new spreadsheet and prints its link and ID:

```powershell
python sheetvid.py upload sample.mp4
```

Download. Restores the file and prints both checksums:

```powershell
python sheetvid.py download --sheet SPREADSHEET_ID -o restored.mp4
```

Options:

| Option | Command | Meaning |
|---|---|---|
| `--sheet ID` | upload | Reuse a spreadsheet from an earlier upload. Its previous file is replaced. |
| `--max-mb N` | upload | Raise the size cap. Default 1, at most 100. |
| `-o PATH` | download | Where to save. Default is the original filename. |

One file per spreadsheet. Images work the same way as videos.

## Web page

A page for restoring by link, with nothing to type in a terminal after it starts:

```powershell
python web.py
```

Open <http://127.0.0.1:8765>, paste a Google Sheets link (or just the spreadsheet ID) and press **Restore**. The video or image appears on the page with a Download button. The page re-computes the SHA-256 in your browser and only shows the file if it matches.

- It signs in as you, with the same credentials as the commands above, so it opens the same spreadsheets: the ones this tool created.
- It listens on this computer only. It is not a way to share with other people.
- Large files show a running timer but no progress bar; 100 MB takes over two minutes.
- The moving dot graphics need a wide window. On a phone-width screen the page works but the graphics are hidden.

## Size

Measured on 23 Nov 2026, one run each. Every restored file matched by SHA-256.

| File size | Chunks | Upload | Download | Note |
|---|---|---|---|---|
| 0.9 MB | 31 | 6 s | 5 s | default cap is 1 MB |
| 4.8 MB | 160 | 16 s | 10 s | needs `--max-mb 5` |
| 24 MB | 802 | 48 s | 33 s | needs `--max-mb 25`; the spreadsheet still opens normally |
| 50 MB | 1,671 | 71 s | 56 s | needs `--max-mb 50` |
| 90 MB | 3,006 | 132 s | 131 s | needs `--max-mb 90` |
| 99 MB | 3,312 | 153 s | 136 s | needs `--max-mb 100` |

The cap is 100 MB. Google refuses a spreadsheet at about 110 MB of file ("This document is too large to continue editing"), and a spreadsheet that reaches that point accepts no further edits.

Sharing the spreadsheet does not let the other person download the file: the tool only opens spreadsheets it created under your own sign-in.

## Tests

Offline, no Google account needed:

```powershell
python -m unittest
```

## Errors and fixes

| Message | Fix |
|---|---|
| `credentials.json not found` | Do [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md). |
| Browser shows `Error 403: access_denied` | Add your Gmail address under Google Auth Platform → Audience → Test users. |
| `HTTP 404` or `HTTP 403` with `--sheet` | That spreadsheet was not created by this tool. It can only open its own. |
| `missing chunks`, `duplicate chunk`, `SHA-256 mismatch` | The spreadsheet was edited or the upload was cut short. Upload again. |
| `no complete upload found` | The upload did not finish. Upload again with the same `--sheet`. |
| `already exists` | Pick another name with `-o`. The tool never overwrites a file. |
| Asked to sign in again after a week | Normal while the Google app is in Testing status. |
