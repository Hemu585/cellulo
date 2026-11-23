# Design

## Goal

Hold the actual bytes of one small file in Google Sheets cells as Base64 text, and get back a byte-identical file, proven by SHA-256.

## Sheets limits (checked 23 Nov 2026)

| Limit | Value | Effect here |
|---|---|---|
| Write requests | 300/min per project, 60/min per user | A 1 MB file needs 4 write calls |
| Read requests | 300/min per project, 60/min per user | A 1 MB file needs 4 read calls |
| Batch request | Counts as 1 request | Many chunks per call |
| Payload | No hard limit; Google recommends 2 MB max | 25 rows per call, about 1 MB |
| Request timeout | 180 seconds | Not a concern at these sizes |
| Over quota | HTTP 429; retry with truncated exponential backoff | Client library retries for us |
| Spreadsheet size | 20 million cells or 100 MB | A 1 MB file uses about 70 cells |
| Characters per cell | 50,000 | 40,000-character chunks leave margin |

Notes:

- Google documents the 50,000-character rule only for Excel imports. The API also rejects longer cells in practice. The live upload confirmed a 40,000-character cell is accepted and read back intact.
- Google's limits page says exceeding the request quota "is planned to incur charges to your Google Cloud billing account later in 2026". Normal use is free, and this tool makes a handful of calls per run.

Sources: [Sheets API usage limits](https://developers.google.com/workspace/sheets/api/limits), [Files you can store in Google Drive](https://support.google.com/drive/answer/37603?hl=en).

## Sheet layout

Tab `meta`, key in column A and value in column B:

| A | B |
|---|---|
| filename | sample.mp4 |
| mime_type | video/mp4 |
| byte_size | 912345 |
| chunk_count | 31 |
| sha256 | 64 hex characters |

Tab `chunks`:

| A (chunk) | B (data) |
|---|---|
| 1 | up to 40,000 Base64 characters |
| 2 | … |

Row 1 is a header, so chunk *n* sits in row *n* + 1.

## Why RAW input

Base64 text can start with `+`, `/` or contain `=`. With the default input mode, Sheets could read a chunk as a formula or number and change it. `valueInputOption=RAW` stores exactly what is sent. Reads use `UNFORMATTED_VALUE` for the same reason.

## Upload order

1. Check the file exists, is not empty, and is under the cap (before any sign-in).
2. SHA-256, Base64-encode, split into 40,000-character chunks.
3. No `--sheet`: create a spreadsheet with tabs `meta` and `chunks`.
4. Clear both tabs in one call. Otherwise rows from an older, longer file would linger and look like extra chunks.
5. If the file needs more rows than the `chunks` tab has, add them (one call).
6. Write the header and chunks, 25 rows per call.
7. Write `meta` last. If the upload is cut short there is no metadata, and download refuses to proceed.

## Download order

1. Read `meta`.
2. Read column A of `chunks` to learn how many numbered rows there are.
3. Read those rows 25 at a time.
4. Validate and rebuild (below).
5. Write the file only after every check passes.

## Validation (`assemble`)

Download stops, and writes nothing, if any of these is true:

- A `meta` value is missing.
- A chunk number is not a whole number.
- A chunk number appears twice.
- A numbered row has no text.
- Any number from 1 to `chunk_count` is absent.
- A number above `chunk_count` is present.
- The joined text is not valid Base64.
- The decoded size differs from `byte_size`.
- The SHA-256 differs from the stored one.

Chunks are placed by their number, not by row position, so sorting or moving rows in the sheet does no harm.

## Rate limits

Every call runs with `execute(num_retries=6)`. The Google client library retries HTTP 429 and 5xx with randomised exponential backoff (up to about a minute on the last try), which is what Google's limits page asks for.

## File safety on download

- Only the base name of the stored filename is used, so a doctored name cannot write outside the current folder.
- An existing file is never overwritten; choose another name with `-o`.

## Size cap

- Default 1 MB. `--max-mb` raises it, up to 100.
- One chunk is 30,000 bytes of file. A new tab has 1,000 rows; for bigger files the tool adds rows to the `chunks` tab before writing.
- **Measured wall: about 110 MB of file per spreadsheet** (23 to 24 Nov 2026, two runs):
  - Fresh spreadsheet, 130 MB upload: refused after 3,749 chunks were accepted (112.5 MB of file, 150 million Base64 characters). The error text of this run was not captured.
  - Spreadsheet already reused for five large uploads, 120 MB upload: refused after 3,649 chunks (109.5 MB of file) with HTTP 400 "This document is too large to continue editing".
- Google's documented "100 MB per spreadsheet" is not the exact wall for this layout: 99.3 MB of file (132 MB of text) was stored and restored on a fresh spreadsheet.
- The tool stops at 100 MB, the largest size proven, which leaves margin below the wall.
- **A spreadsheet that hits the wall is stuck.** Google then refuses every edit to it, including clearing it, so the tool cannot reuse it. Delete it and upload to a new one. The 100 MB cap exists so the tool never gets there.
- A refused upload leaves no `meta`, so download rejects it.

### Measured timings (23 Nov 2026, one run each)

| File | Size | Chunks | Upload | Download | Spreadsheet opens in browser? |
|---|---|---|---|---|---|
| sample.png | 96 KB | 4 | 4.8 s | 3.1 s | yes |
| sample.mp4 | 0.9 MB | 31 | 6.0 s | 5.2 s | yes |
| sample5.mp4 | 4.8 MB | 160 | 15.5 s | 10.3 s | yes, about 3 s |
| sample25.mp4 | 24.0 MB | 802 | 47.9 s | 33.1 s | yes, within seconds |
| 50 MB video | 50.1 MB | 1,671 | 71 s | 56 s | not checked |
| 70 MB video | 70.1 MB | 2,337 | 120 s | 64 s | not checked |
| 80 MB video | 80.1 MB | 2,671 | 117 s | 107 s | not checked |
| 90 MB video | 90.2 MB | 3,006 | 132 s | 131 s | not checked |
| 99 MB video, fresh spreadsheet | 99.3 MB | 3,312 | 153 s | 136 s | not checked |
| 120 MB video, reused spreadsheet | 120.1 MB | 4,005 | refused after 159 s | n/a | n/a |
| 130 MB video, fresh spreadsheet | 130.1 MB | 4,338 | refused after 185 s | n/a | n/a |

The 24 MB to 90 MB and 120 MB runs all reused one spreadsheet; the others each used a fresh one.

Every restored file matched its original by SHA-256. Times include Python start-up and depend on the internet connection. No HTTP 429 was seen in the output at any size; the client library retries those silently, so some may have happened.

The earlier guess that a 25 MB spreadsheet would be heavy in the browser was wrong: both tabs opened and scrolled normally.

## Not built

- Files over 100 MB (would need the file split across several spreadsheets).
- A way for someone you share the spreadsheet with to download the file. The tool only opens spreadsheets it created under your own sign-in.
- Several files in one spreadsheet.
- Resuming an interrupted upload.
- Compression, a web interface, service-account sign-in.
