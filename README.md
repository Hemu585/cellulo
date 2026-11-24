# Cellulo

Store a small file of any type **inside Google Sheets cells** as Base64 text, then restore the identical file. No Google Drive link; the file's bytes live in the cells.

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

2. Create your Google sign-in file by following [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md). It ends up at `C:\Users\<you>\.cellulo\credentials.json`, outside this folder.

## Use

Upload. Creates a new spreadsheet and prints its link and ID:

```powershell
python cellulo.py upload sample.mp4
```

Download. Restores the file and prints both checksums:

```powershell
python cellulo.py download --sheet SPREADSHEET_ID -o restored.mp4
```

Options:

| Option | Command | Meaning |
|---|---|---|
| `--sheet ID` | upload | Reuse a spreadsheet from an earlier upload. Its previous file is replaced. |
| `--max-mb N` | upload | Raise the size cap. Default 1, at most 100. |
| `-o PATH` | download | Where to save. Default is the original filename. |

One file per spreadsheet. Any type of file works.

## Hosted page

<https://cellulo-app.vercel.app> uploads and restores in the browser; nothing to install.

**Upload:** click **Attach a file** in the box (or drop a file on it), press **Upload** and sign in with your own Google account. The file goes into a new spreadsheet in your own Google Drive. With **Anyone with the link can restore it** ticked (the default), the page then shows a link you can send to anyone.

- The site asks only for access to files it creates itself, not the rest of your Drive.
- Limit 100 MB.
- While the Google app is in Testing, only test users can sign in. Add people under Google Auth Platform, Audience, Test users in the Google Cloud project Cellulo (project ID `sheetvid-poc`, which Google never lets you rename).

**Restore:** paste the sheet link into the same box and press **Restore** (or Enter). The button changes from Upload to Restore as soon as you paste. This works for sheets shared as **Anyone with the link** (Viewer); sheets uploaded with `cellulo.py` must be shared by hand in Google Sheets first.

- The browser reads the cells straight from Google; no server is involved, so there is no size limit beyond the tool's 100 MB.
- Private sheets are refused with a message saying how to share them.
- Anyone who has a shared sheet's link can get its file. Set sharing back to **Restricted** to stop that.
- The page carries a public Google API key. It only works for the Google Sheets API and only from this site's address.

Deploy a change: `vercel deploy --prod --cwd web`.

## Local page

A page for restoring by link, including private sheets, with nothing to type in a terminal after it starts:

```powershell
python web.py
```

Open <http://127.0.0.1:8765>, paste a Google Sheets link (or just the spreadsheet ID) and press **Restore**. Images and playable media get a preview, and every file gets a Download button. The page re-computes the SHA-256 in your browser and only shows the file if it matches.

- It signs in as you, with the same credentials as the commands above, so it opens the same spreadsheets: the ones this tool created.
- It listens on this computer only. For sharing, use the hosted page above.
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

To let someone else download a file, share its spreadsheet publicly and send them the link with the hosted page (below).

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
