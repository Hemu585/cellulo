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
| filename | report.pdf |
| mime_type | application/pdf |
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

## Web page

`web.py` is a small local server (Python standard library) around the same `download` function; `web/index.html` is the page and `web/app.js` its script.

- `POST /api/restore` with `{"sheet": "<link or ID>"}` returns the file bytes, with name, MIME type, SHA-256 and chunk count in `X-Cellulo-*` headers.
- The stored MIME type is not trusted: the bytes are always served as `application/octet-stream`. The page previews only PNG, JPEG, GIF, WebP, AVIF, MP4, WebM, Ogg and QuickTime. SVG is never previewed, because an SVG opened in its own tab runs script on the site's origin. The Download link always gets a separate `application/octet-stream` copy.
- The server binds to 127.0.0.1 and rejects requests whose `Host` is not this computer, because it acts with the owner's Google sign-in. `POST /api/restore` also refuses another site's `Origin`, a negative or oversized body, and anything but the fixed list of page files.
- The page re-computes the SHA-256 with the browser's Web Crypto before showing anything.
- An unfinished upload is refused before any chunk is read, and so is a `chunk_count` too large for `byte_size` (every chunk holds up to 30,000 bytes), so a tampered sheet cannot hang the reader.

### Security headers (24 Nov 2026)

`web/vercel.json` sets them for the hosted site, and `web.py` reads the same file, so both send the same set:

- `Content-Security-Policy`: script only from this site and Google's sign-in library (no inline script, which is why the script lives in `app.js`); connections only to this site, `sheets.googleapis.com`, `www.googleapis.com` and Google sign-in; fonts from Google Fonts; images and media from this site or `blob:`; `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`.
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` (the API key's referrer lock still gets the site's origin), and a `Permissions-Policy` that turns off camera, microphone and location.

### Background clip (25 Nov 2026)

A landscape of floating cliffs over clouds plays behind the page, full screen and fixed while the page scrolls. The text, logo and box are ordinary HTML on top. Palette: warm ivory text (`#f4eee2`), ice-blue accents (`#c3dbee`), and translucent deep-navy panels with a light blur behind them only. The clip itself is never blurred. The logo is drawn in ivory and ice blue so it shows on the dark background; the favicon keeps its own colours.

- **Source:** the owner's 1280x720 clip (H.264, 24 fps, 10 s, with an audio track, 3.7 MB). The 2560x1440 "upscaled" copy was not used.
- **`web/hero.mp4`:** H.264 High, 1280x720, no audio, 9 s, 1.3 MB, with `faststart`.
  - The last and first frames of the source don't match: the camera drifts, so a plain loop visibly jumps.
  - The web copy plays from 1 s to the end and crossfades its last second into the first second. It now ends on the frame it starts with.
- **`web/hero-poster.webp`:** the clip's first frame (73 KB).
  - It is preloaded and also set as the backdrop's CSS background, so it shows at once.
  - It stays when autoplay is blocked or the clip fails to load.
- **Playback:**
  - Muted, looping, `playsinline`, no controls, hidden from screen readers.
  - `object-fit: cover`, with `object-position: 55% 50%` so the open sky between the cliffs sits behind the content. On tall phone screens only the sky shows.
  - `app.js` starts it with `play()` rather than the `autoplay` attribute, so visitors who prefer reduced motion get the still poster, and the clip is never downloaded for them.
  - The bottom-left button pauses and resumes it, and remembers the choice. A paused visitor doesn't download the clip either.
  - Coming back to the tab resumes playback.
- **Contrast:** a navy veil over the whole clip, deeper behind the headline and box, and deeper still on portrait screens. The tagline sits on a small navy chip.
  - The worst case was measured over seven frames, at 779x668, 1440x900, 390x844 and 844x390, against the brightest 5% of pixels behind each text.
  - Results: headline at least 3.9:1, italic "One link" at least 3.7:1, tagline at least 6.4:1, brand at least 4.8:1 (5.4:1 on a landscape phone), placeholder at least 5.1:1, error line at least 4.6:1.
- **Liquid glass:** every button (Upload/Restore, Attach a file, Copy link, Restore it, Download and the pause button) is transparent white glass.
  - It is ported from a React "liquid glass button" component into plain CSS. The page has no React, Tailwind or build step, so only the look was carried over.
  - The look has two parts: the component's bright inset rim shadows, kept in the `--rim` CSS variable, and its SVG lens filter (`#glass`: fractal noise, then displacement of what's behind), applied with `backdrop-filter: url(#glass)`.
  - The tagline chip and both panels get the same rim and lens, but keep their navy tint, so the contrast figures above still hold.
  - Chromium draws the lens. Safari uses the `-webkit-` blur instead and shows only the rim.
- **The old dotted flow** is kept in `web/flow.js`, which the page doesn't load; its header says how to bring it back.

### Page design (24 Nov 2026)

Follows the owner's reference image: "Cellulo" with the C logo centred at the top (a home link; the logo is drawn inline in the original navy and blue, about 1.2x the text size), an orange-dot tagline "A simpler way to share files", the headline "Your file is one link away.", one composer box, and under it a status line that stays empty until there is progress or an error (it keeps its height so the box never jumps), all centred in the screen. Nothing on the right-hand side. The product stores any file, so the page never names a file type.

- One box does both jobs. A pasted link makes the button **Restore**; an attached file (button "Attach a file", or drag and drop) makes it **Upload** and shows a chip with the file name, a remove button and the share checkbox. Attaching a file clears a pasted link. Enter sends; Shift+Enter makes a new line.
- The flow lines meet in a point just outside each side of the box. The earlier dot shapes and their morph were removed at the owner's request.
- Fonts: **Newsreader** for the headline (optical sizes, italic for "one link"), **Schibsted Grotesk** for the interface, **Fragment Mono** for small labels. The headline is 36 px on small phones and 67 px at 1678 px wide, capped at 72 px (larger only on 1800+ px monitors, where the whole page scales up).
- Web Interface Guidelines applied: "…" on loading states, non-breaking spaces in sizes, tabular numbers in the progress line, `color-scheme: light`, `touch-action: manipulation` on controls, no transitions on colour or shadow, `translate="no"` on the brand.
- A small pause button at the bottom left stops the flow animation (moving content that runs longer than 5 seconds needs one). The choice is remembered in the browser; reduced-motion visitors get a still frame and no button.

### Browser tab icon (24 Nov 2026)

The owner's C logo (navy top, blue bottom) is the tab icon.

- `web/favicon.svg`: the logo redrawn as two vector paths, so it stays sharp at 16 px. In a dark browser it switches to lighter shades (`prefers-color-scheme: dark`), because the navy half disappears on dark tab bars.
- `web/icon-32.png` and `web/icon-192.png`: cut from the owner's original file, for browsers that don't use SVG icons.
- `web/apple-touch-icon.png`: 180 px, logo on the page colour, for phone home screens.
- The local server (`web.py`) serves only these four file names; Vercel serves them from `web/`.

### Responsive layout (checked 24 Nov 2026)

Measured with the box empty and with a file attached, at 320×568, 390×844, 844×390 (landscape phone), 768×1024, 1024×768, 1440×900, 1920×1080 and 2560×1440: no sideways scrolling and nothing past the screen edge.

- The hero grid column is `minmax(0, 1fr)`, so a long file name cannot widen the page.
- Touch screens (`pointer: coarse`): every control, including the remove-file button, is at least 44 px tall.
- Hover effects only apply where the device can hover, so they don't stick after a tap.
- Short screens (`max-height: 700px`, and `480px` for landscape phones): tighter spacing, the headline sizes by height too, and the tagline pill is dropped below 480 px, so the input box stays on the first screen. At 568×320 nothing scrolls.
- The tagline never wraps; on the narrowest phones (280 px) its text shrinks instead.
- Resizing the window, rotating a phone, or moving the window to a screen with different scaling redraws the flow animation to fit.
- Big monitors (1800+ and 2400+ px wide): the page scales up.
- `viewport-fit=cover` with safe-area padding keeps content clear of notches and the home indicator.

### Hosted on Vercel

The same `web/index.html` is deployed as a static site to <https://cellulo-app.vercel.app> (Vercel project `cellulo`, linked in `web/`). The earlier address was removed when the project was renamed. `cellulo.vercel.app` belongs to another Vercel project, so it could not be used.

- When the page is not on `127.0.0.1` or `localhost`, it reads the sheet itself, in the browser, through the Sheets API with an API key, and applies the same checks as `assemble()`.
- This only works for sheets shared as "anyone with the link". That was the owner's choice on 24 Nov 2026, over putting their Google sign-in on a public server.
- Why not a Vercel function: function responses are capped at 4.5 MB, and the owner's sign-in would let any visitor restore any sheet the tool made.
- API key `cellulo-web` in Google Cloud project Cellulo (ID `sheetvid-poc`): restricted to the Google Sheets API and to `https://cellulo-app.vercel.app/*`. Checked: allowed from the site, 403 from another site or with no referrer.
- Reads 100 rows (about 4 MB) per request and backs off on HTTP 429, so 100 MB takes about 34 reads.

### Upload in the browser

- The visitor signs in with their own Google account through Google Identity Services (token popup, OAuth client `cellulo-web` in the Cellulo project, allowed origins: `https://cellulo-app.vercel.app`, `http://localhost:8765`, `http://127.0.0.1:8765`). The consent screen shows the app name Cellulo). Scope `drive.file`. The owner chose this on 24 Nov 2026: each user uploads into their own Drive.
- Same layout and order as `cellulo.py`: create the spreadsheet (the `chunks` tab is created with enough rows), write chunks 25 rows per call with RAW, write `meta` last.
- If the share box is ticked, a Drive API call then gives "anyone with the link" reader access. The Google Drive API is enabled in the Cellulo project for this.
- The sign-in window has to open from the click itself, so the page asks for the token before any other await.
- Measured: `cellulo.py` (desktop OAuth client) can open a sheet the website (web OAuth client) created, and the reverse is true for public reading, so both clients share `drive.file` access inside the same Cloud project.
- The app is in Testing: only listed test users can sign in. Letting anyone sign in means publishing the app in Google Auth Platform, which may need a privacy policy and brand verification.

## Rate limits

Every call runs with `execute(num_retries=6)`. The Google client library retries HTTP 429 and 5xx with randomised exponential backoff (up to about a minute on the last try), which is what Google's limits page asks for.

## File safety on download

- Only the base name of the stored filename is used, so a doctored name cannot write outside the current folder.
- An existing file is never overwritten (the file is opened in exclusive-create mode, so there is no gap between the check and the write); choose another name with `-o`.
- `token.json` is written owner-only (mode 600) on macOS and Linux.

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
| 50 MB file | 50.1 MB | 1,671 | 71 s | 56 s | not checked |
| 70 MB file | 70.1 MB | 2,337 | 120 s | 64 s | not checked |
| 80 MB file | 80.1 MB | 2,671 | 117 s | 107 s | not checked |
| 90 MB file | 90.2 MB | 3,006 | 132 s | 131 s | not checked |
| 99 MB file, fresh spreadsheet | 99.3 MB | 3,312 | 153 s | 136 s | not checked |
| 120 MB file, reused spreadsheet | 120.1 MB | 4,005 | refused after 159 s | n/a | n/a |
| 130 MB file, fresh spreadsheet | 130.1 MB | 4,338 | refused after 185 s | n/a | n/a |

The 24 MB to 90 MB and 120 MB runs all reused one spreadsheet; the others each used a fresh one.

Every restored file matched its original by SHA-256. Times include Python start-up and depend on the internet connection. No HTTP 429 was seen in the output at any size; the client library retries those silently, so some may have happened.

The earlier guess that a 25 MB spreadsheet would be heavy in the browser was wrong: both tabs opened and scrolled normally.

## Not built

- Files over 100 MB (would need the file split across several spreadsheets).
- Several files in one spreadsheet.
- Resuming an interrupted upload.
- Compression, a web interface, service-account sign-in.
