# Build plan and status

Last updated: 23 Nov 2026.

## Build

- [x] Check current Sheets limits (recorded in [DESIGN.md](DESIGN.md))
- [x] Project folder, `.gitignore`, `requirements.txt`
- [x] `README.md`, `docs/AUTH_SETUP.md`, `docs/DESIGN.md`, this file
- [x] `sheetvid.py`: `upload` and `download` commands
- [x] `test_sheetvid.py`: 17 offline tests, all passing
- [x] Sample clip `sample.mp4`, 903,473 bytes (not committed)
- [x] Guards checked by hand: missing credentials, missing file, over the cap, cap above 25

## Google sign-in

- [x] Cloud project `sheetvid-poc`, Sheets API enabled, consent screen (External, Testing), test user, Desktop client
- [x] `credentials.json` and `token.json` in `~/.sheetvid`, outside this folder

## Live tests against real Google Sheets (23 Nov 2026)

- [x] 1. `python sheetvid.py upload sample.mp4` printed a spreadsheet link (903,473 bytes, 31 chunks)
- [x] 2. The spreadsheet shows Base64 text in `chunks` and five values in `meta`; a 40,000-character cell is accepted; chunks starting with `+` are stored as text
- [x] 3. `python sheetvid.py download --sheet <ID> -o restored.mp4` printed matching checksums
- [x] 4. `Get-FileHash` shows identical hashes; ffprobe reads `restored.mp4` as a valid 12-second video
- [x] 5. One chunk row deleted: download stopped with `missing chunks (1 of 31): [5]`, wrote no file
- [x] 6. One chunk row duplicated: download stopped with `duplicate chunk 2`, wrote no file
- [x] 6b. Checksum removed, then altered: download stopped both times, wrote no file
- [x] 7. Image: 96,218-byte PNG round trip, hashes identical
- [x] 8. 5 MB video with `--max-mb 5`: round trip, hashes identical
- [x] 9. 24 MB video with `--max-mb 25`: round trip, hashes identical, spreadsheet still opens normally

- [x] 10. Limit search (23 to 24 Nov 2026): 50, 70, 80, 90 and 99 MB round trips, hashes identical. 120 MB (reused spreadsheet) and 130 MB (fresh spreadsheet) both refused by Google at about 110 MB of file. Cap set to 100 MB.

- [x] 11. Web page (`python web.py`, 24 Nov 2026): a real sheet link restored `sample.mp4` in the browser, it played (640x360, 12 s), and the browser's own SHA-256 matched. Wrong links, an unknown spreadsheet and an unfinished upload each gave a clear message. Checked at desktop and phone width. Reduced-motion mode and files over 1 MB were not tried through the page.

- [x] 12. Hosted page (24 Nov 2026) at https://sheets-video-store.vercel.app: a publicly shared test sheet (`sheetvid - public-demo.mp4`, the colour-bar clip) restored and played, SHA-256 verified in the browser. A private sheet was refused with the sharing instructions. The API key works from the site and is refused from another site and with no referrer. Files over 1 MB were not tried through the hosted page.

- [ ] 13. Upload from the website (24 Nov 2026). Checked: mode switch, file picker, share box, and the message when the sign-in window is blocked. Not yet done: a real upload, because the browser pane blocks Google's sign-in window unless the owner clicks it.

Tests 5, 6 and 6b edited the spreadsheet through the API rather than by hand; the effect on the cells is the same. Timings are in [DESIGN.md](DESIGN.md).

Not done: nobody has watched `restored.mp4` play or opened `restored.png` by eye. The byte-for-byte hash match makes a difference impossible, but it is a check by tool, not by eye.

## What the offline tests do and do not prove

They prove the chunking, the reassembly, every rejection rule, and the upload and download logic against an in-memory stand-in for Sheets. The live tests above confirm the real Sheets API behaves like the stand-in.

## Rule for changes

Run `python -m unittest` before every commit. Push to GitHub only when it passes.
