(() => {
  // ---------- background: the clip loops with no visible seam (its last two seconds dissolve into its first) ----------
  // play() is called here rather than by an autoplay attribute, so reduced-motion visitors get its first frame as a still
  const form = document.getElementById('form'), clip = document.getElementById('bg'), motion = document.getElementById('motion');
  const still = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = false;
  try { paused = localStorage.getItem('cellulo-motion') === 'paused'; } catch {}
  const show = () => clip.classList.add('on');   // one fade-in when the first frame is ready
  if (clip.readyState >= 2) show(); else clip.addEventListener('loadeddata', show, { once: true });
  function sync() {
    motion.hidden = still.matches;   // reduced motion: a still frame only, so there is nothing to pause
    motion.setAttribute('aria-pressed', String(paused));
    motion.setAttribute('aria-label', paused ? 'Play the background' : 'Pause the background');
    if (paused || still.matches) clip.pause();
    else clip.play().catch(() => {});   // autoplay blocked or the file failed: the black page stays
  }
  motion.addEventListener('click', () => {
    paused = !paused;
    try { localStorage.setItem('cellulo-motion', paused ? 'paused' : 'moving'); } catch {}
    sync();
  });
  still.addEventListener('change', sync);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });   // phones pause media in background tabs
  sync();

  // ---------- restore ----------
  const input = document.getElementById('link'), go = document.getElementById('go'), goLabel = document.getElementById('go-label');
  const status = document.getElementById('status'), result = document.getElementById('result'), media = document.getElementById('media');
  const save = document.getElementById('save');
  let objectUrls = [], ticker = 0, done = '', action = 'upload';   // what the button will do: 'upload' or 'restore'

  function say(text, isError) { status.textContent = text; status.classList.toggle('error', !!isError); }
  function busy(on) {
    const up = action === 'upload';
    go.disabled = on; goLabel.textContent = on ? (up ? 'Uploading…' : 'Restoring…') : (up ? 'Upload' : 'Restore');
    done = '';
    clearInterval(ticker);
    if (on) {
      const began = Date.now(), what = up ? 'Uploading to Google Sheets' : 'Restoring from Google Sheets';
      ticker = setInterval(() => say(`${what}${done} · ${Math.round((Date.now() - began) / 1000)} s`), 1000);
    }
  }
  const hex = buffer => [...new Uint8Array(buffer)].map(b => b.toString(16).padStart(2, '0')).join('');

  // Two ways to read a sheet. On this computer (python web.py) the local server reads it with the owner's sign-in.
  // Hosted, the browser reads a sheet shared as "anyone with the link" straight from Google with a public API key.
  const LOCAL = ['127.0.0.1', 'localhost'].includes(location.hostname);
  const API_KEY = 'AIzaSyC8xLVjqbHoC66LFp6Y046lEPdi1dgorUc';   // browser key, locked to the Sheets API and this site's address, so it is safe to ship in the page
  const META_KEYS = ['filename', 'mime_type', 'byte_size', 'chunk_count', 'sha256'];
  const ROWS_PER_CALL = 100;   // about 4 MB per response, well inside 60 reads a minute even at 100 MB
  const backoff = attempt => new Promise(wake => setTimeout(wake, Math.min(32000, 1000 * 2 ** attempt) + Math.random() * 1000));

  function sheetIdFrom(text) {
    const match = text.match(/\/spreadsheets\/d\/([\w-]+)/);
    if (match) return match[1];
    if (/^[\w-]{20,}$/.test(text)) return text;
    throw new Error('That does not look like a Google Sheets link.');
  }

  async function sheetGet(id, range) {
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(id)}/values/${encodeURIComponent(range)}`
              + `?valueRenderOption=UNFORMATTED_VALUE&key=${API_KEY}`;
    for (let attempt = 0; ; attempt++) {
      const response = await fetch(url);
      if (response.ok) return (await response.json()).values || [];
      if ((response.status === 429 || response.status >= 500) && attempt < 6) { await backoff(attempt); continue; }   // Google asks for backoff on quota errors
      const detail = String((await response.json().catch(() => ({}))).error?.message || '');
      if (response.status === 403 && /caller does not have permission/i.test(detail))   // a blocked site says "Permission denied on the service"
        throw new Error('This sheet is not shared. In Google Sheets choose Share, then General access: Anyone with the link, Viewer.');
      if (response.status === 404) throw new Error('No spreadsheet found at that link.');
      if (/Unable to parse range/i.test(detail)) throw new Error('That spreadsheet was not made by Cellulo.');
      throw new Error(`Google Sheets answered ${response.status}${detail ? ': ' + detail : ''}.`);
    }
  }

  // each 40,000-character chunk is whole Base64 groups, so chunks decode one at a time
  function decodeChunk(text, n) {
    if (text.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(text)) throw new Error(`Chunk ${n} is not valid Base64.`);
    const binary = atob(text), out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  }

  // the same checks as assemble() in cellulo.py
  async function readPublicSheet(link) {
    if (!API_KEY) throw new Error('This site has no Google API key configured yet.');
    const id = sheetIdFrom(link);
    const meta = Object.fromEntries((await sheetGet(id, 'meta!A1:B5')).filter(row => row.length === 2));
    const absent = META_KEYS.filter(key => meta[key] === undefined || meta[key] === '');
    if (absent.length) throw new Error(`No complete upload found (meta is missing: ${absent.join(', ')}).`);
    const count = Number(meta.chunk_count), size = Number(meta.byte_size);
    if (!Number.isInteger(count) || !Number.isInteger(size) || count < 1 || size < 0 || size > 150e6 || count > Math.ceil(size / BYTES_PER_CHUNK) + 1)
      throw new Error('The sheet is corrupt: chunk_count and byte_size must be sensible whole numbers.');

    const last = (await sheetGet(id, 'chunks!A2:A')).length + 1;   // sheet row of the last numbered chunk
    const pieces = new Map();
    for (let start = 2; start <= last; start += ROWS_PER_CALL) {
      for (const row of await sheetGet(id, `chunks!A${start}:B${Math.min(start + ROWS_PER_CALL - 1, last)}`)) {
        if (!row.some(cell => cell !== '')) continue;
        const n = row[0];
        if (typeof n !== 'number' || !Number.isInteger(n)) throw new Error(`Invalid chunk number: ${JSON.stringify(n)}.`);
        if (pieces.has(n)) throw new Error(`Duplicate chunk ${n}.`);
        if (typeof row[1] !== 'string' || !row[1]) throw new Error(`Chunk ${n} has no data.`);
        pieces.set(n, decodeChunk(row[1], n));
      }
      done = ` · ${Math.min(100, Math.round(100 * (start + ROWS_PER_CALL - 2) / Math.max(1, last - 1)))}%`;
    }
    const missing = [], extra = [...pieces.keys()].filter(n => n < 1 || n > count).sort((a, b) => a - b);
    for (let n = 1; n <= count; n++) if (!pieces.has(n)) missing.push(n);
    if (missing.length) throw new Error(`Missing chunks (${missing.length} of ${count}): ${missing.slice(0, 10).join(', ')}.`);
    if (extra.length) throw new Error(`Unexpected chunks beyond ${count}: ${extra.slice(0, 10).join(', ')}.`);

    let total = 0;
    for (let n = 1; n <= count; n++) total += pieces.get(n).length;
    if (total !== size) throw new Error(`Size mismatch: restored ${total} bytes, expected ${size}.`);
    const bytes = new Uint8Array(total);
    for (let n = 1, at = 0; n <= count; at += pieces.get(n).length, n++) bytes.set(pieces.get(n), at);
    return { bytes: bytes.buffer, name: String(meta.filename).split(/[\\/]/).pop(), mime: String(meta.mime_type),
             expected: String(meta.sha256), chunks: count };
  }

  async function readLocal(link) {
    const response = await fetch('/api/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sheet: link }) });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).error || `The server answered ${response.status}`);
    const header = key => decodeURIComponent(response.headers.get('X-Cellulo-' + key) || '');
    return { bytes: await response.arrayBuffer(), name: header('Name'), mime: header('Mime'), expected: header('Sha256'), chunks: header('Chunks') };
  }

  // ---------- upload: the visitor signs in with their own Google account, and the file goes into their own Drive ----------
  const CLIENT_ID = '823029525535-7kf4gjnmml0jlq6g3646dodolvp9sfdn.apps.googleusercontent.com';
  const SCOPE = 'https://www.googleapis.com/auth/drive.file';   // only files this site creates; nothing else in their Drive
  const MAX_BYTES = 100e6, BYTES_PER_CHUNK = 30000, ROWS_PER_WRITE = 25;   // as cellulo.py: 40,000 characters a cell, ~1 MB a call
  const fileInput = document.getElementById('file'), pick = document.getElementById('pick'), shareRow = document.getElementById('share-row');
  const sent = document.getElementById('sent'), sentLink = document.getElementById('sent-link');
  let chosen = null, gis = null, tokenClient = null, pending = null, token = null;

  // one box: an attached file means upload, otherwise a pasted link means restore
  function updateAction() {
    if (go.disabled) return;
    action = chosen || !input.value.trim() ? 'upload' : 'restore';
    goLabel.textContent = action === 'upload' ? 'Upload' : 'Restore';
  }
  function choose(file) {
    chosen = file || null;
    if (chosen) input.value = '';   // one job at a time: an attached file replaces a pasted link
    else fileInput.value = '';      // so the same file can be picked again
    document.getElementById('chip-name').textContent =
      chosen ? `${chosen.name} · ${(chosen.size / 1e6).toFixed(chosen.size < 1e6 ? 2 : 1)} MB` : '';
    document.getElementById('chip').hidden = !chosen;
    pick.hidden = !!chosen; shareRow.hidden = !chosen;
    result.hidden = true; sent.hidden = true;
    updateAction();
    if (chosen) {
      say('Press the arrow to upload, then sign in with your own Google account. The file stays in your Drive.');
      loadGis().catch(error => say(error.message, true));   // ready before the click, so the sign-in window may open
    } else say('');
  }
  fileInput.addEventListener('change', () => choose(fileInput.files[0]));
  document.getElementById('unpick').addEventListener('click', () => choose(null));
  input.addEventListener('input', updateAction);
  input.addEventListener('keydown', event => {   // Enter sends, as in a chat box; Shift+Enter still makes a new line
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener('dragover', event => { event.preventDefault(); form.dataset.drop = ''; });
  form.addEventListener('dragleave', () => delete form.dataset.drop);
  form.addEventListener('drop', event => {
    event.preventDefault(); delete form.dataset.drop;
    if (event.dataTransfer.files[0]) choose(event.dataTransfer.files[0]);
  });

  function loadGis() {
    gis = gis || new Promise((ok, fail) => {
      const script = Object.assign(document.createElement('script'), { src: 'https://accounts.google.com/gsi/client', async: true });
      script.onload = ok;
      script.onerror = () => { gis = null; fail(new Error('Could not load Google sign-in. Check the connection and try again.')); };
      document.head.append(script);
    });
    return gis;
  }

  // must start inside the click itself, or the browser blocks Google's sign-in window
  function signIn() {
    if (token && token.expires > Date.now() + 60000) return Promise.resolve(token.value);
    const oauth = window.google?.accounts?.oauth2;
    if (!oauth) return Promise.reject(new Error('Google sign-in is still loading. Try again in a moment.'));
    tokenClient = tokenClient || oauth.initTokenClient({
      client_id: CLIENT_ID, scope: SCOPE,
      callback: reply => {
        if (reply.error || !oauth.hasGrantedAllScopes(reply, SCOPE)) return pending.fail(new Error('Google did not give this site access, so nothing was uploaded.'));
        token = { value: reply.access_token, expires: Date.now() + Number(reply.expires_in) * 1000 };
        pending.ok(token.value);
      },
      error_callback: problem => pending.fail(new Error(
        problem.type === 'popup_closed' ? 'The Google sign-in window was closed, so nothing was uploaded.'
        : problem.type === 'popup_failed_to_open' ? 'The browser blocked the Google sign-in window. Allow pop-ups for this site and try again.'
        : 'Google sign-in failed, so nothing was uploaded.')),
    });
    return new Promise((ok, fail) => { pending = { ok, fail }; tokenClient.requestAccessToken(); });
  }

  async function googleCall(method, url, body, accessToken) {
    for (let attempt = 0; ; attempt++) {
      const response = await fetch(url, { method, headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (response.ok) return response.json();
      if ((response.status === 429 || response.status >= 500) && attempt < 6) { await backoff(attempt); continue; }
      if (response.status === 401) { token = null; throw new Error('Your Google sign-in expired. Press Upload again to sign in.'); }
      const detail = String((await response.json().catch(() => ({}))).error?.message || '');
      throw new Error(`Google answered ${response.status}${detail ? ': ' + detail : ''}.`);
    }
  }

  function encodeChunk(part) {
    let binary = '';
    for (let i = 0; i < part.length; i += 0x8000) binary += String.fromCharCode.apply(null, part.subarray(i, i + 0x8000));
    return btoa(binary);
  }

  // same order as upload() in cellulo.py: chunks first and meta last, so a cut-off upload is never taken for a whole one
  async function uploadFile(file, share, accessToken) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const sha256 = hex(await crypto.subtle.digest('SHA-256', bytes));
    const rows = [['chunk', 'data']];
    for (let at = 0; at < bytes.length; at += BYTES_PER_CHUNK) rows.push([rows.length, encodeChunk(bytes.subarray(at, at + BYTES_PER_CHUNK))]);
    const sheets = 'https://sheets.googleapis.com/v4/spreadsheets';
    const { spreadsheetId: id } = await googleCall('POST', sheets, {
      properties: { title: `Cellulo - ${file.name}` },
      sheets: [{ properties: { title: 'meta' } }, { properties: { title: 'chunks', gridProperties: { rowCount: Math.max(1000, rows.length) } } }],
    }, accessToken);
    // RAW: Sheets must never read a chunk starting with + or = as a formula
    const write = (cell, values) => googleCall('PUT', `${sheets}/${id}/values/${encodeURIComponent(cell)}?valueInputOption=RAW`, { values }, accessToken);
    for (let start = 0; start < rows.length; start += ROWS_PER_WRITE) {
      await write(`chunks!A${start + 1}`, rows.slice(start, start + ROWS_PER_WRITE));
      done = ` · ${Math.round(100 * Math.min(rows.length, start + ROWS_PER_WRITE) / rows.length)}%`;
    }
    await write('meta!A1', [['filename', file.name], ['mime_type', file.type || 'application/octet-stream'],
                            ['byte_size', bytes.length], ['chunk_count', rows.length - 1], ['sha256', sha256]]);
    let shareError = '';
    if (share) {
      try { await googleCall('POST', `https://www.googleapis.com/drive/v3/files/${id}/permissions`, { type: 'anyone', role: 'reader' }, accessToken); }
      catch (error) { shareError = error.message; }
    }
    return { id, size: bytes.length, count: rows.length - 1, shared: share && !shareError, shareError };
  }

  function startUpload() {
    if (!chosen.size) return say('That file is empty.', true);
    if (chosen.size > MAX_BYTES)
      return say(`That file is ${(chosen.size / 1e6).toFixed(1)} MB. The limit is 100 MB, because a Google spreadsheet fills up at about 110 MB.`, true);
    const file = chosen, share = document.getElementById('share').checked;
    const access = signIn();   // before any await, so the sign-in window counts as part of this click
    busy(true); say('Waiting for Google sign-in…');
    (async () => {
      try {
        const upload = await uploadFile(file, share, await access);
        const link = `https://docs.google.com/spreadsheets/d/${upload.id}`;
        document.getElementById('sent-name').textContent = file.name;
        document.getElementById('sent-facts').textContent =
          `${upload.size.toLocaleString()} bytes · ${upload.count} chunks · ${upload.shared ? 'anyone with the link' : 'private to you'}`;
        sentLink.href = link; sentLink.textContent = link;
        sent.hidden = false;
        say(upload.shareError ? `Uploaded, but sharing failed: ${upload.shareError}`
            : upload.shared ? 'Uploaded. Send the link to anyone.' : 'Uploaded. The sheet is private to you.', !!upload.shareError);
        sent.scrollIntoView({ behavior: still.matches ? 'auto' : 'smooth', block: 'nearest' });
      } catch (error) {
        say(error.message || 'Something went wrong.', true);
      } finally {
        busy(false);
      }
    })();
  }

  document.getElementById('copy').addEventListener('click', async event => {
    const button = event.currentTarget;
    try { await navigator.clipboard.writeText(sentLink.href); button.textContent = 'Copied'; }
    catch { button.textContent = 'Copy failed'; }
    setTimeout(() => { button.textContent = 'Copy link'; }, 1600);
  });
  document.getElementById('try').addEventListener('click', () => {
    const link = sentLink.href;
    choose(null); input.value = link; updateAction(); form.requestSubmit();
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (go.disabled) return;
    updateAction();
    if (chosen) return startUpload();
    const link = input.value.trim();
    if (!link) return say('Paste a link, or attach a file to upload.', true);
    sent.hidden = true;
    busy(true); say('Restoring from Google Sheets…');
    try {
      const file = await (LOCAL ? readLocal(link) : readPublicSheet(link));
      const { bytes, mime, expected } = file, name = file.name || 'restored';
      if (hex(await crypto.subtle.digest('SHA-256', bytes)) !== expected) throw new Error('The file arrived damaged: its SHA-256 does not match the one stored in the sheet.');

      const kind = /^video\/(mp4|webm|ogg|quicktime)$/.test(mime) ? 'video' : /^image\/(png|jpeg|gif|webp|avif)$/.test(mime) ? 'img' : null;
      objectUrls.forEach(url => URL.revokeObjectURL(url));
      const blobUrl = type => URL.createObjectURL(new Blob([bytes], { type }));
      objectUrls = [blobUrl('application/octet-stream')];
      media.replaceChildren();
      if (kind) {
        const view = document.createElement(kind);
        view.src = objectUrls[objectUrls.push(blobUrl(mime)) - 1];
        if (kind === 'video') { view.controls = true; view.playsInline = true; } else view.alt = name;
        media.append(view);
      }
      document.getElementById('name').textContent = name;
      const facts = document.getElementById('facts');
      facts.textContent = `${bytes.byteLength.toLocaleString()} bytes · ${file.chunks} chunks · `;
      const ok = document.createElement('span'); ok.className = 'ok'; ok.textContent = 'SHA-256 verified'; ok.title = expected;
      facts.append(ok);
      save.href = objectUrls[0]; save.download = name;
      result.hidden = false;
      say('Restored. Checked byte for byte.');
      result.scrollIntoView({ behavior: still.matches ? 'auto' : 'smooth', block: 'nearest' });
    } catch (error) {
      say(error.message || 'Something went wrong.', true);
    } finally {
      busy(false);
    }
  });
})();
