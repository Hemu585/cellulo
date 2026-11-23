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

## Your part

- [ ] Google sign-in setup: [AUTH_SETUP.md](AUTH_SETUP.md), about 10 minutes

## Live tests (need the sign-in)

- [ ] 1. `python sheetvid.py upload sample.mp4` prints a spreadsheet link
- [ ] 2. The spreadsheet shows Base64 text in `chunks` (31 chunks) and five values in `meta`
- [ ] 3. `python sheetvid.py download --sheet <ID> -o restored.mp4` prints matching checksums
- [ ] 4. `Get-FileHash sample.mp4, restored.mp4` shows identical hashes, and `restored.mp4` plays
- [ ] 5. Delete one chunk row in the spreadsheet: download stops with `missing chunks`, writes no file
- [ ] 6. Duplicate one chunk row: download stops with `duplicate chunk`, writes no file
- [ ] 7. Image: upload a JPEG or PNG under 1 MB, download it, hashes match, picture opens
- [ ] 8. 5 MB file with `--max-mb 5`: round trip works; record timings in DESIGN.md
- [ ] 9. 25 MB file with `--max-mb 25`: round trip works; record timings in DESIGN.md

## What the offline tests do and do not prove

They prove the chunking, the reassembly, every rejection rule, and the upload and download logic against an in-memory stand-in for Sheets.

They do not prove that the real Sheets API behaves like the stand-in. Live tests 1 to 4 settle that, including whether a 40,000-character cell is accepted.

## Rule for changes

Run `python -m unittest` before every commit. Push to GitHub only when it passes.
