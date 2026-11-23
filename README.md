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
| `--max-mb N` | upload | Raise the size cap. Default 1, at most 25. |
| `-o PATH` | download | Where to save. Default is the original filename. |

One file per spreadsheet. Images work the same way as videos.

## Size

| File size | Cells | Calls each way | Status |
|---|---|---|---|
| 1 MB | about 35 | 2 | default cap |
| 5 MB | about 170 | 7 | expected to be comfortable; not yet measured |
| 25 MB | about 835 | 34 | expected to be slow, and the spreadsheet heavy in the browser; not yet measured |

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
