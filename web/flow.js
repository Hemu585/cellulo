// The dotted "Gateway Flow" background used before the landscape clip (Nov 2026). Not loaded by the page.
// To bring it back: add <canvas id="flow" aria-hidden="true"></canvas> and the .motion button inside <main class="hero">,
// load this file before app.js, restore the #flow CSS rule (position: absolute; inset: 0; pointer-events: none),
// and drop the background clip. The restore/upload code no longer speeds the flow up while busy (targetPace).
(() => {
  // ---------- flow: dotted curves pour from both edges into the link box ----------
  const canvas = document.getElementById('flow'), ctx = canvas.getContext('2d');
  const hero = document.querySelector('.hero'), form = document.getElementById('form');
  const still = matchMedia('(prefers-reduced-motion: reduce)');
  const LINE = 'rgba(52, 72, 94, 0.3)', MOTE = 'rgba(15, 42, 68, 0.85)';
  let W = 0, H = 0, sides = [], paths = [], booms = [], pace = 1, targetPace = 1, last = 0;

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  // Gateway Flow, light mode: 80 dotted cubic curves, alternating sides, one mote riding each.
  // Changed from the original: the curves meet in a point just outside each side of the box, not at the screen centre.
  const PATHS = 80;
  function makePaths(old, centre) {
    return Array.from({ length: PATHS }, (_, i) => {
      const base = centre + (i / PATHS - 0.5) * H * 1.4, prev = old[i];   // spread evenly around where the curves meet
      return { left: i % 2 === 0, base, startY: base, t: prev ? prev.t : Math.random(),
               speed: prev ? prev.speed : (0.0015 + Math.random() * 0.002) * 60 };   // original speeds were per frame at 60 fps
    });
  }
  // edge -> halfway, still at the start height -> 80%, at the box height -> the tip beside the box
  function curve(p) {
    const s = p.left ? sides[0] : sides[1], at = f => s.edge + s.dir * s.span * f;
    return [at(0), p.startY, at(0.5), p.startY, at(0.8), s.y, at(1), s.y];
  }
  function bezier(t, c) {
    const u = 1 - t, a = u * u * u, b = 3 * u * u * t, d = 3 * u * t * t, e = t * t * t;
    return [a * c[0] + b * c[2] + d * c[4] + e * c[6], a * c[1] + b * c[3] + d * c[5] + e * c[7]];
  }

  function layout() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2), box = hero.getBoundingClientRect(), f = form.getBoundingClientRect();
    W = box.width; H = box.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const left = f.left - box.left, right = box.right - f.right, y = f.top - box.top + f.height / 2;
    const gap = 12, room = Math.min(left, right);
    sides = room < 90 ? [] : [{ edge: 0, dir: 1, span: left - gap }, { edge: W, dir: -1, span: right - gap }];
    for (const s of sides) s.y = y;
    paths = makePaths(paths, y);
  }

  function draw(ms, dt) {
    ctx.clearRect(0, 0, W, H);
    if (!sides.length) return;
    for (const b of booms) { b.r += 900 * dt; b.life -= 0.9 * dt; }
    booms = booms.filter(b => b.life > 0);

    ctx.setLineDash([1, 4]); ctx.lineWidth = 1.2; ctx.strokeStyle = LINE;
    for (const p of paths) {
      const c = p.c = curve(p);
      ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.bezierCurveTo(c[2], c[3], c[4], c[5], c[6], c[7]); ctx.stroke();
    }
    ctx.setLineDash([]);

    ctx.fillStyle = MOTE;
    for (const p of paths) {
      p.t += p.speed * pace * dt;
      if (p.t > 1) { p.t = 0; p.startY = clamp(p.startY + (Math.random() - 0.5) * 10, p.base - 40, p.base + 40); }
      let [x, y] = bezier(p.t, p.c);
      for (const b of booms) {                              // a click sends out a ring that shoves motes aside
        const dx = x - b.x, dy = y - b.y, dist = Math.hypot(dx, dy) || 1, off = Math.abs(dist - b.r);
        if (off < 120) { const push = (1 - off / 120) * b.life * 80; x += dx / dist * push; y += dy / dist * push; }
      }
      ctx.fillRect(x - 2, y - 2, 4, 4);
    }
  }

  // the loop runs unless the visitor asked for less motion or pressed pause; then one still frame is drawn
  const motion = document.getElementById('motion');
  let running = false, paused = false;
  try { paused = localStorage.getItem('cellulo-motion') === 'paused'; } catch {}
  const moving = () => !still.matches && !paused;
  function frame(now) {
    if (!moving()) { running = false; return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    pace += (targetPace - pace) * Math.min(1, dt * 3);
    draw(now, dt);
    requestAnimationFrame(frame);
  }
  const start = () => {
    motion.setAttribute('aria-pressed', String(paused));
    motion.setAttribute('aria-label', paused ? 'Play the background animation' : 'Pause the background animation');
    if (!moving()) { draw(0, 0); return; }
    if (running) return;
    running = true; last = performance.now(); requestAnimationFrame(frame);
  };
  motion.addEventListener('click', () => {
    paused = !paused;
    try { localStorage.setItem('cellulo-motion', paused ? 'paused' : 'moving'); } catch {}
    start();
  });
  const relayout = () => { layout(); motion.hidden = !sides.length || still.matches; if (!moving()) draw(0, 0); };
  new ResizeObserver(relayout).observe(hero);
  (function watchPixelRatio() {
    matchMedia(`(resolution: ${devicePixelRatio}dppx)`).addEventListener('change', () => { relayout(); watchPixelRatio(); }, { once: true });
  })();
  layout();
  motion.hidden = !sides.length || still.matches;
  still.addEventListener('change', () => { motion.hidden = !sides.length || still.matches; start(); });
  start();
  hero.addEventListener('pointerdown', event => {
    if (!moving() || event.target.closest('form, .result')) return;
    const r = canvas.getBoundingClientRect();
    booms.push({ x: event.clientX - r.left, y: event.clientY - r.top, r: 0, life: 1 });
  });

})();
