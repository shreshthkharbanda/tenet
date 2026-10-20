/* Reader for a spec-from-code book. Data comes from site_data.py (pre-escaped HTML); this script only
   arranges it. Views are chosen by a bare hash token: '' home, 'paths', 'chapters', 'defects',
   'glossary', a spec file slug, a flow id, or a claim ID (opens its chapter at the claim). */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const root = document.documentElement;
  const view = $("#view");
  const ID_RE = /^[A-Z][A-Z0-9]{1,11}-\d{3,4}$/;
  const NS = "http://www.w3.org/2000/svg";
  const cache = { files: {}, snips: {} };
  let B = null;            // book.json
  let current = null;      // slug or view token being shown
  const cleanup = [];      // per-view teardown (observers, timers)

  const store = {
    get(k) { try { return localStorage.getItem("sfc." + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("sfc." + k, v); } catch (e) { /* storage unavailable */ } },
  };
  const motionOn = () => root.dataset.motion !== "off" && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtPct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  const flowColor = (i) => `var(--l${(i % 6) + 1})`;

  async function getJSON(p) {
    const r = await fetch(p);
    if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
    return r.json();
  }
  async function loadFile(slug) {
    return cache.files[slug] || (cache.files[slug] = await getJSON(`data/f-${slug}.json`));
  }
  async function loadSnips(slug) {
    return cache.snips[slug] || (cache.snips[slug] = await getJSON(`data/s-${slug}.json`));
  }
  const fileMeta = (slug) => B.files.find((f) => f.slug === slug);
  const shortTitle = (f) => (f ? f.title.replace(/\s*\([A-Z0-9]+\)\s*$/, "") : "");
  const modules = () => B.files.filter((f) => f.kind === "module");
  // a module's display name is its id in plain words ("failure-handling" -> "Failure handling")
  const pretty = (id) => String(id).replace(/^\d+-/, "").replace(/[-_]+/g, " ").replace(/^./, (c) => c.toUpperCase());
  const nameOf = (slug) => { const f = fileMeta(slug); return f ? pretty(f.module || f.rel.replace(/\.md$/, "").replace(/^modules\//, "")) : slug; };
  const readingMinutes = (f) => Math.max(1, Math.round(((f.words || 0) / 238)));

  /* ---------- chrome: toggles and search entry ---------- */
  function initChrome() {
    const theme = store.get("theme");
    if (theme) root.dataset.theme = theme;
    const font = store.get("font");
    if (font) root.dataset.font = font;
    const motion = store.get("motion");
    if (motion) root.dataset.motion = motion;
    // reading depth: Everyone (no code), Engineer (adds the mechanism), Expert (adds every claim)
    root.dataset.lens = store.get("lens") || "engineer";
    const lensBtns = $$("[data-lens-set]");
    const syncLens = () => lensBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lensSet === root.dataset.lens)));
    lensBtns.forEach((b) => b.addEventListener("click", () => { root.dataset.lens = b.dataset.lensSet; store.set("lens", b.dataset.lensSet); syncLens(); }));
    syncLens();
    const sync = () => {
      $("#t-font").setAttribute("aria-pressed", root.dataset.font === "sans" ? "true" : "false");
      $("#t-font").textContent = root.dataset.font === "sans" ? "Aa sans" : "Aa serif";
      $("#t-motion").setAttribute("aria-pressed", root.dataset.motion === "off" ? "false" : "true");
      $("#t-motion").textContent = root.dataset.motion === "off" ? "Motion off" : "Motion on";
      const t = root.dataset.theme || "system";
      $("#t-theme").textContent = { system: "Auto", light: "Light", dark: "Dark" }[t];
    };
    $("#t-font").onclick = () => { root.dataset.font = root.dataset.font === "sans" ? "serif" : "sans"; store.set("font", root.dataset.font); sync(); };
    $("#t-motion").onclick = () => { root.dataset.motion = root.dataset.motion === "off" ? "on" : "off"; store.set("motion", root.dataset.motion); sync(); };
    $("#t-theme").onclick = () => {
      const next = { system: "light", light: "dark", dark: "system" }[root.dataset.theme || "system"];
      if (next === "system") delete root.dataset.theme; else root.dataset.theme = next;
      store.set("theme", next === "system" ? "" : next); sync();
    };
    $("#t-search").onclick = openSearch;
    document.addEventListener("click", (e) => {
      const b = e.target.closest("[data-lens-go]");
      if (b) { root.dataset.lens = b.dataset.lensGo; store.set("lens", b.dataset.lensGo); $$("[data-lens-set]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.lensSet === root.dataset.lens))); }
    });
    $("#t-menu").onclick = () => { const d = $("#drawer"); d.hidden = !d.hidden; $("#t-menu").setAttribute("aria-expanded", String(!d.hidden)); };
    $("#drawer").addEventListener("click", (e) => {
      const px = e.target.closest("[data-proxy]");
      if (px) { $("#" + px.dataset.proxy).click(); return; }
      if (e.target.closest("a")) $("#drawer").hidden = true;
    });
    document.addEventListener("keydown", (e) => {
      if ((e.key === "/" && !/input|textarea/i.test(document.activeElement.tagName)) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) {
        e.preventDefault(); openSearch();
      }
    });
    sync();
  }

  /* ---------- routing ---------- */
  async function route() {
    const tok = decodeURIComponent(location.hash.slice(1));
    hidePop();
    if (ID_RE.test(tok) && B.owner[tok]) {
      const slug = B.owner[tok];
      if (current !== slug) await show(() => renderChapter(slug), slug);
      focusClaim(tok);
      return;
    }
    const f = fileMeta(tok);
    const fl = B.flows.find((x) => x.id === tok);
    if (f) return show(() => renderChapter(f.slug), f.slug, true);
    if (fl) return show(() => renderFlow(fl), fl.id, true);
    const views = { paths: renderPaths, chapters: renderChapters, defects: renderDefects, glossary: renderGlossary };
    if (views[tok]) return show(views[tok], tok, true);
    return show(renderHome, "", true);
  }
  async function show(fn, key, top) {
    while (cleanup.length) { try { cleanup.pop()(); } catch (e) { /* ignore */ } }
    current = key;
    $$(".nav a").forEach((a) => a.setAttribute("aria-current", a.getAttribute("href") === "#" + key || (key === "" && a.getAttribute("href") === "#") ? "page" : "false"));
    const run = async () => {
      view.innerHTML = '<p class="loading">Loading…</p>';
      try { await fn(); } catch (e) { view.innerHTML = `<p class="empty">This page could not load: ${esc(e.message)}</p>`; }
      view.classList.remove("view"); void view.offsetWidth; view.classList.add("view");
      if (top) window.scrollTo(0, 0);
    };
    if (document.startViewTransition && motionOn()) await document.startViewTransition(run).updateCallbackDone;
    else await run();
  }
  function focusClaim(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: motionOn() ? "smooth" : "auto" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  }

  /* ---------- shared pieces ---------- */
  function meter(f) {
    if (f.holdout == null) return "";
    const w = 92, lo = (f.holdout_low ?? f.holdout) * w, pt = f.holdout * w;
    const tip = `Accuracy check: ${Math.round(f.holdout * f.holdout_n)} of ${f.holdout_n} test questions, written from the code and never shown to the spec's writers, were answered correctly from this chapter alone. With so few questions the true rate could be as low as ${fmtPct(f.holdout_low)} (95% confidence).`;
    return `<span class="meter" title="${esc(tip)}"><span>Accuracy check ${Math.round(f.holdout * f.holdout_n)}/${f.holdout_n}</span><svg viewBox="0 0 ${w} 12" aria-hidden="true">
      <rect class="track" x="0" y="4" width="${w}" height="4" rx="2"/><rect class="ci" x="${lo}" y="2" width="${Math.max(2, pt - lo)}" height="8" rx="2"/>
      <circle class="pt" cx="${pt}" cy="6" r="4.5"/></svg></span>`;
  }
  const pill = (s) => s ? `<span class="pill ${esc(s.toLowerCase())}">${esc(s)}</span>` : "";
  function glyphCounts(c) {
    return `<span class="glyphs"><span title="Confirmed: read directly in the code"><i class="g confirmed"></i>${c.confirmed} confirmed</span><span title="Inferred: follows from the code but depends on something outside it"><i class="g inferred"></i>${c.inferred} inferred</span><span title="Open question: the code does not settle it"><i class="g gap"></i>${c.gap} open</span></span>`;
  }
  function stripSVG(fl, i) {
    const steps = fl.steps, n = steps.length, W = 360, pad = 14, y = 16;
    const x = (k) => pad + (n === 1 ? (W - 2 * pad) / 2 : (k * (W - 2 * pad)) / (n - 1));
    let s = `<svg class="strip" viewBox="0 0 ${W} 44" role="img" aria-label="${n} steps through ${new Set(steps.flatMap((st) => st.who)).size} chapters">`;
    s += `<line x1="${x(0)}" y1="${y}" x2="${x(n - 1)}" y2="${y}" stroke="${flowColor(i)}" stroke-width="5" stroke-linecap="round"/>`;
    // a stop per step; a label only where the path enters another chapter, alternating rows so
    // neighbouring labels never collide
    let last = null, row = 0;
    steps.forEach((st, k) => {
      const prim = st.who.find((w) => (fileMeta(w) || {}).kind === "module");
      const pf = prim ? fileMeta(prim).prefix : "";
      s += `<circle cx="${x(k)}" cy="${y}" r="5.5" fill="var(--sheet)" stroke="${flowColor(i)}" stroke-width="2.5"><title>Step ${k + 1}: ${esc(nameOf(prim || ""))}</title></circle>`;
      if (pf && pf !== last) { s += `<text x="${x(k)}" y="${row % 2 ? 42 : 33}" text-anchor="middle">${esc(pf)}</text>`; row++; }
      last = pf || last;
    });
    return s + "</svg>";
  }
  function pathCard(fl, i) {
    const mods = new Set(fl.steps.flatMap((s) => s.who.filter((w) => (fileMeta(w) || {}).kind === "module")));
    return `<a class="path" href="#${fl.id}" style="--c:${flowColor(i)}">
      <span class="t"><b>${i + 1}</b>${esc(fl.title)}</span>${stripSVG(fl, i)}
      <span class="meta">${fl.steps.length} steps · ${mods.size} chapters</span></a>`;
  }
  function chapterRow(f, n) {
    return `<a class="chap" href="#${f.slug}"><span class="n">${n}</span>
      <div><h3>${esc(shortTitle(f))}</h3><p>${f.story && f.story.headline ? f.story.headline : f.lede || ""}</p></div>
      <div class="stats">${f.kind === "module" ? `<div style="display:flex;gap:8px;align-items:center">${meter(f)} ${pill(f.status)}</div>` : ""}
        <div class="kv">${f.story ? `<span class="brief-badge" title="This chapter opens with a short illustrated story">In brief · <b>${Math.max(1, Math.round(f.story.words / 238))}</b> min</span>` : ""}<span><b>${f.claims.confirmed + f.claims.inferred + f.claims.gap}</b> claims</span>${f.defects ? `<span><b>${f.defects}</b> suspected defects</span>` : ""}<span><b>${readingMinutes(f)}</b> min</span></div></div></a>`;
  }
  function defectCard(d) {
    const f = fileMeta(d.file);
    return `<div class="defect"><span class="id"><a href="#${d.id}">${d.id}</a></span><div class="txt">${d.h}</div>
      <span class="where">${esc(shortTitle(f))}${d.conf !== "confirmed" ? " · " + esc(d.conf) : ""}</span></div>`;
  }
  const ordered = () => (B.order || B.files.map((f) => f.slug)).map(fileMeta).filter(Boolean);

  /* ---------- system map ---------- */
  function mapLayout() {
    const mods = modules();
    const ids = mods.map((m) => m.slug);
    const score = {}, cnt = {};
    B.flows.forEach((fl) => fl.steps.forEach((st, k) => st.who.forEach((w) => {
      if (!ids.includes(w)) return;
      const p = fl.steps.length > 1 ? k / (fl.steps.length - 1) : 0.5;
      score[w] = (score[w] || 0) + p; cnt[w] = (cnt[w] || 0) + 1;
    })));
    const links = B.links.filter((l) => ids.includes(l.from) && ids.includes(l.to));
    ids.forEach((id) => { if (cnt[id]) score[id] /= cnt[id]; });
    ids.forEach((id) => {
      if (cnt[id]) return;
      const nb = links.filter((l) => l.from === id || l.to === id).map((l) => (l.from === id ? l.to : l.from)).filter((x) => cnt[x]);
      score[id] = nb.length ? nb.reduce((a, x) => a + score[x], 0) / nb.length + 0.08 : 0.9;
    });
    const ncol = ids.length <= 6 ? 3 : ids.length <= 16 ? 4 : 5;
    const sorted = [...ids].sort((a, b) => score[a] - score[b] || a.localeCompare(b));
    const cols = Array.from({ length: ncol }, () => []);
    sorted.forEach((id, k) => cols[Math.min(ncol - 1, Math.floor((k * ncol) / ids.length))].push(id));
    const pos = {};
    const place = () => cols.forEach((c, ci) => c.forEach((id, ri) => (pos[id] = { c: ci, r: ri, n: c.length })));
    place();
    for (let it = 0; it < 6; it++) {   // barycenter ordering against neighbouring columns
      cols.forEach((c) => {
        const bc = {};
        c.forEach((id) => {
          const nb = links.filter((l) => l.from === id || l.to === id).map((l) => (l.from === id ? l.to : l.from)).filter((x) => pos[x] && pos[x].c !== pos[id].c);
          const w = nb.map((x) => (pos[x].r + 0.5) / pos[x].n);
          bc[id] = w.length ? w.reduce((a, b) => a + b, 0) / w.length : (pos[id].r + 0.5) / pos[id].n;
        });
        c.sort((a, b) => bc[a] - bc[b]);
      });
      place();
    }
    const NW = 158, NH = 54, GX = 70, GY = 26, maxRows = Math.max(...cols.map((c) => c.length));
    const H = maxRows * (NH + GY) + 20, W = ncol * NW + (ncol - 1) * GX + 24;
    const xy = {};
    cols.forEach((c, ci) => c.forEach((id, ri) => {
      const off = ((maxRows - c.length) * (NH + GY)) / 2;
      xy[id] = { x: 12 + ci * (NW + GX), y: 10 + off + ri * (NH + GY), w: NW, h: NH };
    }));
    return { xy, links, W, H };
  }
  function routeOf(fl, xy) {
    const seq = [];
    fl.steps.forEach((st) => { const p = st.who.find((w) => xy[w]); if (p && seq[seq.length - 1] !== p) seq.push(p); });
    return seq;
  }
  function smoothPath(pts) {
    if (pts.length < 2) return pts.length ? `M${pts[0][0]},${pts[0][1]}` : "";
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let k = 1; k < pts.length; k++) {
      const [x0, y0] = pts[k - 1], [x1, y1] = pts[k], mx = (x0 + x1) / 2;
      d += ` C${mx},${y0} ${mx},${y1} ${x1},${y1}`;
    }
    return d;
  }
  // ELK (layered, orthogonal routing) lays out the map so each path runs as one metro line that
  // enters a box only where that chapter takes a step. Loaded on demand; the simple column layout
  // above is the fallback when the script cannot load.
  let elkReady = null;
  function loadELK() {
    if (window.ELK) return Promise.resolve(window.ELK);
    return elkReady || (elkReady = new Promise((res, rej) => {
      const sc = document.createElement("script");
      sc.src = "https://cdn.jsdelivr.net/npm/elkjs@0.12.0/lib/elk.bundled.js";
      sc.onload = () => (window.ELK ? res(window.ELK) : rej(new Error("ELK missing")));
      sc.onerror = () => rej(new Error("ELK did not load"));
      document.head.appendChild(sc);
    }));
  }
  let mapCache = null;
  async function mapGeometry() {
    if (mapCache) return mapCache;
    const NW = 164, NH = 54;
    const mods = modules(), ids = new Set(mods.map((m) => m.slug));
    const edges = [];
    B.flows.forEach((fl, i) => {
      const seq = [];
      fl.steps.forEach((st) => { const p = st.who.find((w) => ids.has(w)); if (p && seq[seq.length - 1] !== p) seq.push(p); });
      for (let k = 1; k < seq.length; k++) edges.push({ id: `f${i}e${k}`, flow: i, k, sources: [seq[k - 1]], targets: [seq[k]] });
    });
    // a step's other chapters are consulted by its main one: dashed spurs, deduplicated
    const spurs = [], seen = new Set();
    B.flows.forEach((fl) => fl.steps.forEach((st) => {
      const mods_ = st.who.filter((w) => ids.has(w));
      mods_.slice(1).forEach((w) => {
        const key = mods_[0] + ">" + w;
        if (mods_[0] !== w && !seen.has(key) && !edges.some((e) => e.sources[0] === mods_[0] && e.targets[0] === w)) {
          seen.add(key); spurs.push({ id: `s${spurs.length}`, sources: [mods_[0]], targets: [w] });
        }
      });
    }));
    // a chapter no path visits is tied to its strongest citation partner, for placement only
    const onPath = new Set(edges.concat(spurs).flatMap((e) => [e.sources[0], e.targets[0]]));
    const ghost = [];
    mods.forEach((m) => {
      if (onPath.has(m.slug)) return;
      const l = B.links.find((x) => (x.from === m.slug && ids.has(x.to)) || (x.to === m.slug && ids.has(x.from)));
      if (l) ghost.push({ id: `g-${m.slug}`, sources: [l.to === m.slug ? l.from : m.slug], targets: [l.to === m.slug ? m.slug : l.to] });
    });
    try {
      const ELK = await loadELK();
      const g = await new ELK().layout({
        id: "root",
        layoutOptions: {
          "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
          "elk.layered.spacing.nodeNodeBetweenLayers": "84", "elk.spacing.nodeNode": "34", "elk.spacing.edgeEdge": "7",
          "elk.layered.spacing.edgeEdgeBetweenLayers": "7", "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
          "elk.layered.crossingMinimization.thoroughness": "40", "elk.padding": "[top=14,left=14,bottom=14,right=14]",
        },
        children: mods.map((m) => ({ id: m.slug, width: NW, height: NH })),
        edges: edges.concat(spurs, ghost).map(({ id, sources, targets }) => ({ id, sources, targets })),
      });
      const xy = {};
      g.children.forEach((c) => (xy[c.id] = { x: c.x, y: c.y, w: c.width, h: c.height }));
      const route = {};
      g.edges.forEach((e) => {
        const sec = (e.sections || [])[0];
        if (sec) route[e.id] = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map((p) => [p.x, p.y]);
      });
      const lines = B.flows.map((fl, i) => {
        const pts = [];
        edges.filter((e) => e.flow === i).forEach((e) => { (route[e.id] || []).forEach((p) => pts.push(p)); });
        return pts;
      });
      // one spur per chapter that no colored line visits: its shortest
      const onLine = new Set(edges.flatMap((e) => [e.sources[0], e.targets[0]]));
      const best = {};
      spurs.forEach((e) => {
        const t = e.targets[0], pts = route[e.id];
        if (!pts || onLine.has(t)) return;
        if (!best[t] || pts.length < best[t].length) best[t] = pts;
      });
      const spurLines = Object.values(best);
      return (mapCache = { xy, lines, spurLines, W: g.width, H: g.height, elk: true });
    } catch (e) {
      const { xy, W, H } = mapLayout();
      const lines = B.flows.map((fl, i) => {
        const o = (i - (B.flows.length - 1) / 2) * 4.5;
        return routeOf(fl, xy).map((id) => [xy[id].x + xy[id].w / 2 + o, xy[id].y + xy[id].h / 2 + o]);
      });
      return (mapCache = { xy, lines, spurLines: [], W, H, elk: false });
    }
  }
  function roundedPath(pts, r = 9) {
    if (pts.length < 2) return "";
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let k = 1; k < pts.length - 1; k++) {
      const [x0, y0] = pts[k - 1], [x1, y1] = pts[k], [x2, y2] = pts[k + 1];
      const d1 = Math.hypot(x1 - x0, y1 - y0), d2 = Math.hypot(x2 - x1, y2 - y1);
      const q = Math.min(r, d1 / 2, d2 / 2);
      if (q < 0.5) { d += ` L${x1},${y1}`; continue; }
      const ax = x1 - ((x1 - x0) / d1) * q, ay = y1 - ((y1 - y0) / d1) * q;
      const bx = x1 + ((x2 - x1) / d2) * q, by = y1 + ((y2 - y1) / d2) * q;
      d += ` L${ax},${ay} Q${x1},${y1} ${bx},${by}`;
    }
    const z = pts[pts.length - 1];
    return d + ` L${z[0]},${z[1]}`;
  }
  async function renderMap(el) {
    const { xy, lines, spurLines, W, H, elk } = await mapGeometry();
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Map of the chapters. Each colored line is one main path a request takes; it enters a box where that chapter does the next step. Dashed lines lead to chapters a step consults.");
        let r = spurLines.map((pts) => `<path class="spur" d="${roundedPath(pts)}"/>`).join("");
    lines.forEach((pts, i) => {
      if (pts.length < 2) {
        // a path that never leaves one chapter is drawn as a ring around that box
        const st = B.flows[i].steps.map((x) => x.who.find((w) => xy[w])).find(Boolean), p = st && xy[st];
        if (p) r += `<rect class="route" data-flow="${i}" x="${p.x - 5 - i}" y="${p.y - 5 - i}" width="${p.w + 10 + 2 * i}" height="${p.h + 10 + 2 * i}" rx="${14 + i}" stroke="${flowColor(i)}" stroke-width="3.5" opacity="0.85"/>`;
        return;
      }
      r += `<path class="route" data-flow="${i}" d="${elk ? roundedPath(pts) : smoothPath(pts)}" stroke="${flowColor(i)}" stroke-width="3.5" opacity="0.85"/>`;
    });
    let nodes = "";
    modules().forEach((m) => {
      const p = xy[m.slug];
      if (!p) return;
      const ring = m.status === "validated" ? "var(--ok)" : m.status === "provisional" ? "var(--warn)" : m.status === "weak" ? "var(--bad)" : "var(--rule)";
      nodes += `<g class="map-node" data-slug="${m.slug}" tabindex="0" role="link" aria-label="${esc(shortTitle(m))}">
        <rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="10"/>
        <rect class="ring" x="${p.x + 10}" y="${p.y + p.h - 6}" width="${p.w - 20}" height="3" rx="1.5" style="fill:${ring}"/>
        <text x="${p.x + 12}" y="${p.y + 22}">${esc(pretty(m.module))}</text>
        <text class="sub" x="${p.x + 12}" y="${p.y + 38}">${esc(m.prefix)} · ${m.claims.confirmed + m.claims.inferred + m.claims.gap} claims</text>
        <title>${esc(shortTitle(m))}: ${esc(m.status || "")}</title></g>`;
    });
    svg.innerHTML = `<g class="routes">${r}</g><g>${nodes}</g><circle class="route-dot" r="6.5" fill="var(--ink)" stroke="var(--sheet)" stroke-width="2.5" opacity="0"/>`;
    el.innerHTML = "";
    el.appendChild(svg);
    $$(".map-node", svg).forEach((n) => {
      const go = () => (location.hash = n.dataset.slug);
      n.addEventListener("click", go);
      n.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
    return { svg, xy };
  }
  let ride = 0;
  function playRoute(svg, i) {
    const routes = $$(".route", svg), dot = $(".route-dot", svg);
    ride++;
    const me = ride;
    routes.forEach((p) => { const on = i == null || +p.dataset.flow === i; p.setAttribute("opacity", i == null ? "0.85" : on ? "1" : "0.1"); p.setAttribute("stroke-width", i != null && on ? "6" : "3.5"); });
    const nodesOn = new Set();
    if (i != null) B.flows[i].steps.forEach((st) => st.who.forEach((w) => nodesOn.add(w)));
    $$(".map-node", svg).forEach((n) => { n.classList.toggle("on", nodesOn.has(n.dataset.slug)); n.classList.toggle("dim", i != null && !nodesOn.has(n.dataset.slug)); });
    dot.setAttribute("opacity", "0");
    if (i == null) return;
    const path = routes.find((p) => +p.dataset.flow === i);
    if (!path) return;
    const L = path.getTotalLength();
    if (!motionOn() || !L) return;
    path.style.strokeDasharray = `${L}`;
    path.animate([{ strokeDashoffset: L }, { strokeDashoffset: 0 }], { duration: 900, easing: "cubic-bezier(.3,.6,.2,1)" }).onfinish = () => { path.style.strokeDasharray = ""; };
    dot.setAttribute("fill", getComputedStyle(path).stroke);
    const t0 = performance.now(), dur = 900 + L * 3.2;
    const tick = (t) => {
      if (me !== ride) return;
      const k = Math.min(1, (t - t0) / dur), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const pt = path.getPointAtLength(e * L);
      dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y); dot.setAttribute("opacity", k < 1 ? "1" : "0");
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  /* ---------- views ---------- */
  async function renderHome() {
    const ov = B.files.find((f) => f.kind === "overview");
    const mods = modules();
    const validated = mods.filter((m) => m.status === "validated").length;
    const sysName = (B.title || "").replace(/:\s*overview$/i, "");
    view.innerHTML = `
      <div class="cover">
        <div><h1><small>Behavioral specification</small>${esc(sysName)}</h1>
          <p class="lede">${B.system && B.system.plain.length ? B.system.plain[0] : ov ? ov.lede : ""}</p></div>
        <aside class="cover-side">
          <div class="facts">
            <div><b>${B.stats.claims.toLocaleString()}</b><span>claims, each citing code</span></div>
            <div><b>${mods.length}</b><span>chapters</span></div>
            <div><b>${validated}/${mods.length}</b><span>chapters passed the accuracy check</span></div>
            <div><b>${B.stats.defects}</b><span>suspected defects</span></div>
          </div>
          <p class="label">Start here</p>
          <ol class="start">${ordered().filter((f) => f.kind === "module").slice(0, 3).map((f) => `<li><a href="#${f.slug}">${esc(shortTitle(f))}</a></li>`).join("")}<li><a href="#${B.flows[0] ? B.flows[0].id : "paths"}">Walk one request end to end</a></li></ol>
          <p class="label">Compiled from <a href="${esc(B.repo)}/tree/${esc(B.commit)}" target="_blank" rel="noopener">${esc(B.repo.replace(/^https?:\/\//, ""))}</a> at <span class="mono">${esc(B.commit.slice(0, 10))}</span></p>
        </aside>
      </div>
      <figure class="mapcard"><div class="head"><span class="label">System map</span><span class="label" style="text-transform:none;letter-spacing:0">Pick a path to trace it; pick a box to open its chapter</span></div>
        <div class="mapwrap" id="map"></div>
        <div class="legend" id="legend"></div>
        <figcaption class="label" style="text-transform:none;letter-spacing:0;padding:6px 4px 2px;font-weight:600">Boxes are chapters. Each colored line is one path a request takes, entering a box where that chapter does the next step; dashed lines lead to chapters a step consults. The bar in each box is its validation status: green validated, amber provisional.</figcaption>
      </figure>
      ${B.system ? `<div class="system-story">${storyHTML(B.system, null, true)}</div>` : ""}
      <section class="block" id="paths"><header><h2>What happens when…</h2><p>Each path follows one request through the chapters, step by step.</p></header>
        <div class="paths">${B.flows.map(pathCard).join("")}</div></section>
      <section class="block"><header><h2>Chapters</h2><p>In reading order. Accuracy check: unseen test questions answered correctly from the chapter alone.</p></header>
        <div class="chapters">${ordered().filter((f) => f.kind === "module").map((f, k) => chapterRow(f, k + 1)).join("")}</div></section>
      <section class="block L2"><header><h2>Needs a decision</h2><p>${B.stats.defects} suspected defects: behavior the code has that looks unintended.</p></header>
        <div class="defect-list">${(B.headline_defects || []).concat(B.defects.map((d) => d.id)).filter((v, k, a) => a.indexOf(v) === k).slice(0, 6).map((id) => B.defects.find((d) => d.id === id)).filter(Boolean).map(defectCard).join("")}</div>
        <p style="margin-top:14px"><a href="#defects">All ${B.stats.defects} suspected defects →</a></p></section>
      <section class="block"><header><h2>Reference</h2><p>Facts that span chapters.</p></header>
        <div class="shelf">${B.files.filter((f) => f.kind !== "module").map((f) => `<a href="#${f.slug}"><b>${esc(shortTitle(f))}</b><span>${f.claims.confirmed + f.claims.inferred + f.claims.gap} claims · ${readingMinutes(f)} min</span></a>`).join("")}<a href="#glossary"><b>Glossary</b><span>${B.glossary.length} terms</span></a></div></section>`;
    if (B.system) {  // the system story's terms and figures, as a chapter's
      const sys = $(".system-story", view);
      defineTerms(sys, B.system.words);
      for (const fg of B.system.sections.flatMap((x) => x.blocks.filter((b) => b.t === "fig"))) {
        const el = $(`.sfig[data-fig="${fg.id}"]`, sys);
        if (el) drawFigure(el, fg);
      }
    }
    $("#map").innerHTML = '<p class="loading" style="padding:30px 8px">Laying out the map…</p>';
    const { svg } = await renderMap($("#map"));
    const legend = $("#legend");
    legend.innerHTML = B.flows.map((fl, i) => `<button class="chip-flow" style="--c:${flowColor(i)}" data-i="${i}" aria-pressed="false"><i></i><b>${i + 1}</b>${esc(fl.title)}</button>`).join("");
    let active = null;
    $$(".chip-flow", legend).forEach((b) => {
      const pick = (on) => { active = on; $$(".chip-flow", legend).forEach((x) => x.setAttribute("aria-pressed", String(+x.dataset.i === on))); playRoute(svg, on); };
      b.addEventListener("click", () => pick(active === +b.dataset.i ? null : +b.dataset.i));
      b.addEventListener("mouseenter", () => { if (active == null) playRoute(svg, +b.dataset.i); });
      b.addEventListener("mouseleave", () => { if (active == null) playRoute(svg, null); });
    });
    $$(".path").forEach((a, i) => {
      a.addEventListener("mouseenter", () => { if (active == null) playRoute(svg, i); });
      a.addEventListener("mouseleave", () => { if (active == null) playRoute(svg, null); });
    });
  }
  async function renderPaths() {
    view.innerHTML = `<section class="block" style="margin-top:0"><header><h2>What happens when…</h2><p>${B.flows.length} paths through the system, each step citing the claims that specify it.</p></header>
      <div class="paths">${B.flows.map(pathCard).join("")}</div></section>`;
  }
  async function renderChapters() {
    const list = ordered();
    view.innerHTML = `<section class="block" style="margin-top:0"><header><h2>Chapters</h2><p>In reading order.</p></header>
      <div class="chapters">${list.filter((f) => f.kind === "module").map((f, k) => chapterRow(f, k + 1)).join("")}</div></section>
      <section class="block"><header><h2>Reference</h2></header><div class="chapters">${list.filter((f) => f.kind !== "module").map((f, k) => chapterRow(f, "R" + (k + 1))).join("")}</div></section>`;
  }
  async function renderDefects() {
    const groups = {};
    B.defects.forEach((d) => (groups[d.file] = groups[d.file] || []).push(d));
    view.innerHTML = `<section class="block" style="margin-top:0"><header><h2>Suspected defects</h2><p>${B.defects.length} behaviors that look unintended, each stating why and who is affected.</p></header>
      ${ordered().filter((f) => groups[f.slug]).map((f) => `<h3 style="margin:26px 0 10px;font-size:1.1rem"><a href="#${f.slug}" style="color:inherit;text-decoration:none">${esc(shortTitle(f))}</a> <span class="label">${groups[f.slug].length}</span></h3><div class="defect-list">${groups[f.slug].map(defectCard).join("")}</div>`).join("")}</section>`;
  }
  async function renderGlossary() {
    view.innerHTML = `<section class="block" style="margin-top:0"><header><h2>Glossary</h2><p>One meaning per term, used the same way in every chapter.</p></header>
      <dl class="glossary">${B.glossary.map((g) => `<div><dt>${g.term}</dt><dd>${g.h}</dd></div>`).join("")}</dl></section>`;
  }

  function blockHTML(b, F) {
    if (b.t === "p") return `<div class="prose"><p>${b.h}</p></div>`;
    if (b.t === "ul" || b.t === "ol") return `<div class="prose"><${b.t}>${b.items.map((it) => `<li>${it.h}</li>`).join("")}</${b.t}></div>`;
    if (b.t === "table") return `<div class="tbl"><table><thead><tr>${b.head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${b.rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    if (b.t === "code") return `<pre class="fence"><code>${esc(b.text)}</code></pre>`;
    if (b.t === "claims") return `<ul class="ledger">${b.ids.map((id) => claimHTML(F.claims[id])).join("")}</ul>`;
    return "";
  }
  function refLabel(r) {
    const m = r.match(/^(.*?)(?::L?(\d+)(?:-L?(\d+))?)?$/);
    const sym = r.includes("::") ? r.split("::")[1] : null;
    const base = (r.split("::")[0].match(/[^/]+$/) || [r])[0].replace(/:.*$/, "");
    if (sym) return `${base} · ${sym}`;
    return m && m[2] ? `${base}:${m[2]}${m[3] && m[3] !== m[2] ? "–" + m[3] : ""}` : base;
  }
  function claimHTML(c) {
    if (!c) return "";
    const ev = c.ev === "passed" ? `<span class="badge ev" title="An executed check script confirms this claim">✓ executed</span>`
      : c.ev === "hollow" ? `<span class="badge hollow" title="Its check runs none of the cited code">check hollow</span>`
      : c.ev === "flaky" ? `<span class="badge flaky" title="Its check passed only on a re-run">✓ flaky check</span>`
      : c.ev === "failed" || c.ev === "stale" ? `<span class="badge failed">check ${esc(c.ev)}</span>` : "";
    return `<li class="claim${c.defect ? " defect" : ""}" id="${c.id}">
      <div class="cid"><i class="g ${c.conf}" title="${c.conf}"></i><a href="#${c.id}">${c.id}</a></div>
      <div class="body"><div class="tx">${c.h}</div>${c.detail && c.detail.length ? `<ul class="cdetail">${c.detail.map((d) => `<li>${d}</li>`).join("")}</ul>` : ""}
        <div class="refs">${ev}${c.refs.map((r, k) => `<button class="ref" data-ref="${esc(r)}" data-k="${k}" aria-expanded="false" title="${esc(r)}">${esc(refLabel(r))}</button>`).join("")}</div></div></li>`;
  }
  function srcHTML(r, sn) {
    if (!sn) return `<div class="src"><div class="more">No source excerpt for <span class="mono">${esc(r)}</span>.</div></div>`;
    const url = B.repo ? `${B.repo}/blob/${B.commit}/${sn.p}${sn.a ? `#L${sn.a}-L${sn.b}` : ""}` : "";
    const head = `<header><span>${esc(sn.p)}${sn.a ? `:${sn.a}–${sn.b}` : ""}</span>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">Open at ${esc(B.commit.slice(0, 7))} ↗</a>` : ""}</header>`;
    if (!sn.l) return `<div class="src">${head}<div class="more">Whole-file reference.</div></div>`;
    const code = sn.l.join("\n");
    let hl = esc(code);
    if (window.hljs && /\.py$/.test(sn.p)) { try { hl = window.hljs.highlight(code, { language: "python", ignoreIllegals: true }).value; } catch (e) { /* plain */ } }
    const lines = hl.split("\n");
    const rows = lines.map((ln, k) => `<tr><td class="ln">${sn.a + k}</td><td class="cd">${ln || " "}</td></tr>`).join("");
    const cut = sn.b - sn.a + 1 - sn.l.length;
    return `<div class="src">${head}<div class="code"><table>${rows}</table></div>${cut > 0 ? `<div class="more">${cut} more lines in the cited range; open the file to read them.</div>` : ""}</div>`;
  }

  /* ---------- chapter story: the readable layer over the ledger ---------- */
  const chips = (ids) => ids.length ? `<span class="cites">${ids.map((x) => `<a class="xr" href="#${x}" data-id="${x}">${x}</a>`).join(" ")}</span>` : "";
  // skipPlain: the home cover already shows the system story's plain words, so its card leaves them out
  function storyHTML(st, f, skipPlain) {
    const n = f ? f.claims.confirmed + f.claims.inferred + f.claims.gap : 0;
    // each block carries its layer from the story gate (check_story.block_layer), the same definition the
    // persona readers are tested on; the lens hides Engineer blocks from Everyone
    const lay = (b) => (b.layer === "everyone" ? "" : "L2");
    const sec = st.sections.map((x, k) => `<section class="st-sec" id="story-${k}"><h3>${x.title}</h3>${x.blocks.map((b) =>
      b.t === "p" ? `<p class="${b.lead ? "lead " : ""}${lay(b)}">${b.h}</p>` : b.t === "ul" ? `<ul class="${lay(b)}">${b.items.map((i) => `<li>${i.h}</li>`).join("")}</ul>`
        : b.t === "path" ? pathBlock(b) : figureShell(b)).join("")}</section>`).join("");
    const mins = Math.max(1, Math.round((st.words_n || st.words || 0) / 238));
    return `<section class="story" aria-label="Chapter in brief">
      <p class="label">${f ? "The chapter in brief" : "Start here"} · ${mins} min</p>
      <h2 class="headline">${st.headline}</h2>
      ${st.plain.length && !skipPlain ? `<div class="plain L1"><span class="label">In plain words</span>${st.plain.map((p) => `<p>${p}</p>`).join("")}</div>` : ""}
      ${st.minute.length ? `<div class="minute L2"><span class="label">In one minute</span>${st.minute.map((p) => `<p>${p}</p>`).join("")}</div>` : ""}
      ${st.words.length ? `<details class="words${st.words.length > 16 ? " many" : ""}"${st.words.length > 16 ? "" : " open"}><summary class="label">Words you'll see (${st.words.length})</summary><dl>${st.words.map((w) =>
        `<div><dt>${w.term}</dt><dd>${w.means}<span class="code-names"><span class="L2">${w.code}</span> ${chips(w.ids)}</span></dd></div>`).join("")}</dl></details>` : ""}
      ${st.glance.length ? `<div class="glance L2"><span class="label">At a glance</span><div class="tbl"><table><thead><tr><th>When</th><th>Then</th><th>Claims</th></tr></thead><tbody>${st.glance.map((r) => `<tr><td>${r.when}</td><td>${r.then}</td><td class="ids">${chips(r.ids)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
      ${sec}
      ${st.watch.length ? `<div class="watch"><span class="label">Watch out</span><ul>${st.watch.map((w) => `<li>${w}</li>`).join("")}</ul></div>` : ""}
      ${f ? `<p class="to-ledger L2">Every claim in this chapter follows, in the order of the module (${n} claims). <button class="btn lens-jump" data-lens-go="expert">Show all ${n} claims</button></p>` : ""}
    </section>`;
  }
  // each defined term, at its first use in each section, carries its plain meaning on hover or focus
  // (signalling and pre-training: the reader never has to scroll back to Words you'll see)
  function defineTerms(root, words) {
    if (!root || !words || !words.length) return;
    const strip = (h) => { const d = document.createElement("div"); d.innerHTML = h; d.querySelectorAll(".cites").forEach((c) => c.remove()); return d.textContent.trim(); };
    const terms = words.map((w) => ({ term: strip(w.term), means: strip(w.means) })).filter((w) => w.term.length > 2)
      .sort((a, b) => b.term.length - a.term.length);
    const rx = (s) => new RegExp(`(^|[^\\w-])(${s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}s?)(?![\\w-])`, "i");
    const parts = $$(".plain, .st-sec, .watch, .minute, .glance", root);
    parts.forEach((part) => {
      const seen = new Set();
      const walk = document.createTreeWalker(part, NodeFilter.SHOW_TEXT, { acceptNode: (n) =>
        n.parentElement.closest("a, code, h3, dfn, .label, .sfig-art, button, .tl-events") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
      const nodes = [];
      while (walk.nextNode()) nodes.push(walk.currentNode);
      for (const node of nodes) {
        let n = node;
        for (const w of terms) {
          if (seen.has(w.term) || !n || !n.parentNode) continue;
          const m = rx(w.term).exec(n.nodeValue);
          if (!m) continue;
          seen.add(w.term);
          const at = m.index + m[1].length;
          const rest = n.splitText(at);
          const after = rest.splitText(m[2].length);
          const d = document.createElement("dfn");
          d.className = "term"; d.tabIndex = 0; d.dataset.means = w.means; d.textContent = rest.nodeValue;
          d.setAttribute("aria-description", w.means);
          rest.replaceWith(d);
          n = after;
        }
      }
    });
  }
  function pathBlock(b) {
    const i = B.flows.findIndex((x) => x.id === b.flow);
    const fl = B.flows[i];
    return `<ol class="pathsteps" style="--c:${flowColor(Math.max(0, i))}">${b.steps.map((x) => `<li><span class="n">${x.n}</span><span>${x.h}</span></li>`).join("")}</ol>
      ${fl ? `<p><a class="btn" href="#${fl.id}">Walk through it step by step →</a></p>` : ""}`;
  }
  // an example played out over time: one lane per actor, state bands, event markers, a playhead the
  // reader can play or scrub; the event list beside it lights up as the playhead passes
  function drawTimeline(fig, fg) {
    const art = $(".sfig-art", fig);
    const lanes = fg.lanes, evs = fg.events;
    const times = [...new Set(evs.map((e) => e.t))].sort((a, b) => a - b);
    const tmax = times.length;  // the playhead runs over event slots: distinct times evenly spaced, in order
    // lane names wrap to two lines and size the label column, so a long name never runs into its bars
    const wrap = (s) => { const out = [""]; s.split(" ").forEach((w) => { const c = out.length - 1; if (out[c] && (out[c] + " " + w).length > 18 && out.length < 2) out.push(w); else out[c] = (out[c] + " " + w).trim(); }); return out; };
    const names = lanes.map((ln) => wrap(ln.label));
    const LW = Math.round(Math.min(210, Math.max(110, 22 + 7.8 * Math.max(...names.flat().map((s) => s.length))))), W = Math.max(680, LW + 110 * times.length), LH = 52, TOP = 26, H = TOP + lanes.length * LH + 34;
    const slot = (t) => times.indexOf(t);
    const x = (u) => LW + 10 + (u / tmax) * (W - LW - 26);
    evs.forEach((e) => (e.u = slot(e.t)));
    const states = [...new Set(evs.map((e) => e.state))];
    const hue = (st) => `var(--l${(states.indexOf(st) % 6) + 1})`;
    let out = `<line class="tl-axis" x1="${LW}" y1="${H - 26}" x2="${W - 10}" y2="${H - 26}"/>`;
    times.forEach((t, u) => {
      const lab = evs.find((e) => e.t === t).time;
      out += `<line class="tl-tick" x1="${x(u)}" y1="${TOP - 6}" x2="${x(u)}" y2="${H - 26}"/><text class="tl-time" x="${x(u)}" y="${H - 10}" text-anchor="middle">${lbl(lab)}</text>`;
    });
    lanes.forEach((ln, k) => {
      const y = TOP + k * LH;
      out += `<text class="tl-lane" x="8" y="${y + LH / 2 + 4 - (names[k].length - 1) * 8}">${names[k].map((s, i) => `<tspan x="8" dy="${i ? 16 : 0}">${lbl(s)}</tspan>`).join("")}<title>${lbl(ln.label)}</title></text>`;
      const le = evs.filter((e) => e.lane === ln.id);
      le.forEach((e, j) => {
        const x0 = x(e.u), x1 = j + 1 < le.length ? x(le[j + 1].u) : W - 12;
        out += `<rect class="tl-band" data-k="${evs.indexOf(e)}" x="${x0}" y="${y + 10}" width="${Math.max(2, x1 - x0)}" height="${LH - 20}" rx="6" style="fill:${hue(e.state)}"/>`;
        if (x1 - x0 > 46) out += `<text class="tl-state" x="${x0 + 8}" y="${y + LH / 2 + 4}">${lbl(e.state.length > Math.floor((x1 - x0 - 14) / 6.2) ? e.state.slice(0, Math.max(3, Math.floor((x1 - x0 - 14) / 6.2) - 1)) + "…" : e.state)}<title>${lbl(e.state)}</title></text>`;
      });
      le.forEach((e) => { out += `<circle class="tl-ev" data-k="${evs.indexOf(e)}" cx="${x(e.u)}" cy="${y + 10}" r="6"><title>${lbl(e.time)}: ${lbl(e.label)}</title></circle>`; });
    });
    out += `<line class="tl-head" x1="${LW}" y1="${TOP - 10}" x2="${LW}" y2="${H - 26}"/>`;
    art.innerHTML = `<svg class="sfig-svg tl" viewBox="0 0 ${W} ${H}" role="img" aria-label="${lbl(fg.title.replace(/<[^>]+>/g, ""))}" style="min-width:${Math.min(W, 520)}px">${out}</svg>
      <div class="tl-controls"><button class="btn" data-act="tl-play" aria-pressed="false">Play</button><input type="range" min="0" max="1000" value="1000" aria-label="Time in the example"><span class="label tl-now">end</span></div>`;
    const steps = $(".sfig-steps", fig);
    if (steps) steps.remove();
    fig.insertAdjacentHTML("beforeend", `<ol class="tl-events">${evs.map((e, k) => `<li data-k="${k}"><b>${lbl(e.time)}</b><span><strong>${lbl(lanes.find((l) => l.id === e.lane)?.label || e.lane)}:</strong> ${lbl(e.label)} → <em>${lbl(e.state)}</em> ${chips(e.ids)}</span></li>`).join("")}</ol>`);
    const svg = $("svg", art), head = $(".tl-head", svg), range = $("input", art), now = $(".tl-now", art), items = $$(".tl-events li", fig);
    const show = (u) => {
      head.setAttribute("x1", x(u)); head.setAttribute("x2", x(u));
      $$(".tl-band", svg).forEach((b) => b.classList.toggle("future", evs[+b.dataset.k].u > u + 1e-9));
      $$(".tl-ev", svg).forEach((c) => c.classList.toggle("future", evs[+c.dataset.k].u > u + 1e-9));
      let last = -1;
      evs.forEach((e, k) => { if (e.u <= u + 1e-9) last = k; });
      items.forEach((li, k) => { li.classList.toggle("on", k === last); li.classList.toggle("future", evs[k].u > u + 1e-9); });
      now.textContent = u >= tmax - 1 + 1e-9 ? "end" : last >= 0 ? evs[last].time : "start";
    };
    range.addEventListener("input", () => show((range.value / 1000) * tmax));
    items.forEach((li) => li.addEventListener("click", (e) => { if (e.target.closest("a")) return; const u = evs[+li.dataset.k].u; range.value = (u / tmax) * 1000; show(u); }));
    let raf = 0;
    const btn = $('[data-act="tl-play"]', art);
    const stop = () => { cancelAnimationFrame(raf); btn.textContent = "Play"; btn.setAttribute("aria-pressed", "false"); };
    btn.addEventListener("click", () => {
      if (btn.getAttribute("aria-pressed") === "true") return stop();
      btn.textContent = "Pause"; btn.setAttribute("aria-pressed", "true");
      if (!motionOn()) { range.value = 1000; show(tmax); return stop(); }
      const t0 = performance.now(), from = +range.value >= 1000 ? 0 : (range.value / 1000) * tmax, dur = 1200 + evs.length * 900;
      const tick = (nw) => {
        const q = Math.min(1, (nw - t0) / dur), t = from + (tmax - from) * q;
        range.value = (t / tmax) * 1000; show(t);
        if (q < 1) raf = requestAnimationFrame(tick); else stop();
      };
      raf = requestAnimationFrame(tick);
    });
    cleanup.push(stop);
    show(tmax);  // complete at rest: the whole example is visible before anyone presses play
  }
  function figureShell(fg) {
    return `<figure class="sfig" data-fig="${fg.id}"><div class="sfig-art"><p class="loading" style="padding:16px">Drawing…</p></div>
      ${fg.steps.length ? `<div class="sfig-steps"><div class="controls"><span class="label">Step through</span><span style="display:flex;gap:6px"><button class="btn" data-act="prev" aria-label="Previous step">←</button><button class="btn" data-act="play">Play</button><button class="btn" data-act="next" aria-label="Next step">→</button></span></div>
        <ol>${fg.steps.map((x, k) => `<li data-k="${k}"><b>${x.title}</b><span>${x.h}</span></li>`).join("")}</ol></div>` : ""}
      <figcaption>${fg.title}</figcaption></figure>`;
  }
  const textW = (t, px = 12.5) => Math.ceil(String(t).length * px * 0.56) + 4;
  const lbl = (t) => esc(String(t).replace(/`/g, ""));
  async function drawFigure(fig, fg) {
    const art = $(".sfig-art", fig);
    let svg, geo;
    if (fg.kind === "timeline") return drawTimeline(fig, fg);
    if (fg.kind === "sequence") ({ svg, geo } = seqFigure(fg));
    else ({ svg, geo } = await graphFigure(fg));
    art.innerHTML = "";
    art.appendChild(svg);
    // claims behind any mark: click opens the first, hover shows all
    $$("[data-ids]", svg).forEach((el) => {
      el.addEventListener("click", () => { const ids = el.dataset.ids.split(","); if (ids[0]) location.hash = ids[0]; });
    });
    const items = $$(".sfig-steps li", fig);
    if (!items.length) return;
    let cur = -1, timer = null;
    const token = $(".token", svg);
    const set = (k) => {
      if (k < 0 || k >= items.length) return;
      cur = k;
      items.forEach((li, j) => li.classList.toggle("on", j === k));
      const t = fg.steps[k].target;
      $$("[data-el]", svg).forEach((el) => el.classList.toggle("on", el.dataset.el === t));
      $$("[data-el]", svg).forEach((el) => el.classList.toggle("dim", el.dataset.el !== t && !(t.includes(">") && t.split(">").includes(el.dataset.el))));
      const path = $(`path[data-el="${t}"]`, svg);
      if (path && token && motionOn()) {
        const L = path.getTotalLength(), t0 = performance.now(), dur = 500 + L * 1.6, me = k;
        const tick = (now) => {
          if (cur !== me) return;
          const q = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - q, 3), pt = path.getPointAtLength(e * L);
          token.setAttribute("cx", pt.x); token.setAttribute("cy", pt.y); token.setAttribute("opacity", q < 1 ? "1" : "0");
          if (q < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }
    };
    const stop = () => { clearInterval(timer); timer = null; const b = $('[data-act="play"]', fig); b.textContent = "Play"; b.setAttribute("aria-pressed", "false"); };
    fig.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      const li = e.target.closest(".sfig-steps li");
      if (li && !e.target.closest("a")) { stop(); set(+li.dataset.k); }
      if (!b) return;
      if (b.dataset.act === "prev") { stop(); set(Math.max(0, cur - 1)); }
      if (b.dataset.act === "next") { stop(); set(cur + 1); }
      if (b.dataset.act === "play") {
        if (timer) return stop();
        b.textContent = "Pause"; b.setAttribute("aria-pressed", "true");
        set(cur >= items.length - 1 ? 0 : cur + 1);
        timer = setInterval(() => (cur >= items.length - 1 ? stop() : set(cur + 1)), 2400);
      }
    });
    cleanup.push(stop);
  }
  async function graphFigure(fg) {
    const states = fg.kind === "states";
    const nodes = fg.nodes.map((n) => {
      const dec = /\?\s*$/.test(n.label);
      return { id: n.id, width: Math.max(states ? 104 : 116, textW(n.label.replace(/`/g, "")) + (dec ? 48 : 30)), height: dec ? 52 : 40, dec, n };
    });
    const edges = fg.edges.map((e, k) => ({ id: `${e.a}>${e.b}#${k}`, sources: [e.a], targets: [e.b], e,
      labels: e.label ? [{ id: `l${k}`, text: e.label, width: textW(e.label.replace(/`/g, ""), 11.5), height: 14 }] : [] }));
    let g = null;
    // lay out left to right; a long chain that comes out much wider than tall is laid out top to bottom
    // instead, so its labels stay legible in a reading column
    const layout = async (dir) => new (await loadELK())().layout({ id: "f", layoutOptions: {
      "elk.algorithm": "layered", "elk.direction": dir, "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.spacing.nodeNodeBetweenLayers": dir === "DOWN" ? "34" : "56", "elk.spacing.nodeNode": "26", "elk.spacing.edgeLabel": "4",
      "elk.edgeLabels.placement": "CENTER", "elk.layered.edgeLabels.sideSelection": "ALWAYS_UP", "elk.padding": "[top=16,left=16,bottom=16,right=16]",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    }, children: nodes.map(({ id, width, height }) => ({ id, width, height })), edges: edges.map(({ id, sources, targets, labels }) => ({ id, sources, targets, labels: labels.map((l) => ({ ...l })) })) });
    try {
      g = await layout("RIGHT");
      if (g.width / g.height > 2.0) g = await layout("DOWN");
    } catch (e) { g = null; }
    if (!g) {  // fallback: one row, straight edges
      let x = 16;
      g = { width: 0, height: 120, children: nodes.map((n) => { const c = { id: n.id, x, y: 30, width: n.width, height: n.height }; x += n.width + 60; return c; }), edges: [] };
      g.width = x;
      g.edges = edges.map((e) => { const A = g.children.find((c) => c.id === e.sources[0]), Bn = g.children.find((c) => c.id === e.targets[0]);
        return { id: e.id, sections: [{ startPoint: { x: A.x + A.width, y: A.y + A.height / 2 }, endPoint: { x: Bn.x, y: Bn.y + Bn.height / 2 } }], labels: [] }; });
    }
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    let out = `<defs><marker id="fa-${fg.id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>`;
    g.edges.forEach((ge) => {
      const sec = (ge.sections || [])[0];
      if (!sec) return;
      const meta = edges.find((x) => x.id === ge.id).e;
      const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map((q) => [q.x, q.y]);
      const key = `${meta.a}>${meta.b}`;
      out += `<path class="fe" data-el="${key}" data-ids="${meta.ids.join(",")}" d="${roundedPath(pts, 7)}" marker-end="url(#fa-${fg.id})"><title>${lbl(meta.label)}: ${meta.ids.join(", ")}</title></path>`;
      (ge.labels || []).forEach((L) => { out += `<text class="fel" data-el="${key}" x="${L.x + L.width / 2}" y="${L.y + L.height - 3}" text-anchor="middle">${lbl(meta.label)}</text>`; });
    });
    g.children.forEach((c) => {
      const n = byId[c.id];
      const shape = n.dec
        ? `<path d="M${c.x + 14},${c.y} L${c.x + c.width - 14},${c.y} L${c.x + c.width},${c.y + c.height / 2} L${c.x + c.width - 14},${c.y + c.height} L${c.x + 14},${c.y + c.height} L${c.x},${c.y + c.height / 2} Z"/>`
        : `<rect x="${c.x}" y="${c.y}" width="${c.width}" height="${c.height}" rx="${states ? c.height / 2 : 8}"/>`;
      out += `<g class="fn${n.dec ? " dec" : ""}" data-el="${c.id}" data-ids="${n.n.ids.join(",")}" tabindex="0">${shape}<text x="${c.x + c.width / 2}" y="${c.y + c.height / 2 + 4.5}" text-anchor="middle">${lbl(n.n.label)}</text><title>${lbl(n.n.label)}: ${n.n.ids.join(", ")}</title></g>`;
    });
    out += `<circle class="token" r="5.5" opacity="0"/>`;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${Math.ceil(g.width)} ${Math.ceil(g.height)}`);
    svg.setAttribute("class", "sfig-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", fg.title.replace(/<[^>]+>/g, ""));
    // small figures may grow to fill the column; large ones keep a legible minimum and scroll on phones
    svg.style.maxWidth = Math.ceil(g.width * 1.6) + "px";
    svg.style.minWidth = Math.min(Math.ceil(g.width * 0.9), 520) + "px";
    svg.innerHTML = out;
    return { svg, geo: g };
  }
  function seqFigure(fg) {
    const parts = fg.actors.length ? fg.actors : [...new Set(fg.edges.flatMap((e) => [e.a, e.b]))].map((id) => ({ id, label: id }));
    const CW = Math.max(120, ...parts.map((p) => textW(p.label) + 26)), TOP = 54, RH = 46;
    const W = parts.length * CW + 20, H = TOP + fg.edges.length * RH + 16;
    const cx = (id) => parts.findIndex((p) => p.id === id) * CW + CW / 2 + 10;
    let out = `<defs><marker id="fa-${fg.id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>`;
    parts.forEach((p) => { out += `<line class="life" x1="${cx(p.id)}" y1="${TOP - 6}" x2="${cx(p.id)}" y2="${H - 6}"/>`; });
    fg.edges.forEach((e, k) => {
      const y = TOP + k * RH + RH / 2 + 4, key = `${e.a}>${e.b}`;
      if (e.a === e.b) {
        const x = cx(e.a) + 4;
        out += `<path class="fe" data-el="${key}" data-ids="${e.ids.join(",")}" d="M${x},${y - 10} C${x + 40},${y - 14} ${x + 40},${y + 10} ${x + 2},${y + 8}" marker-end="url(#fa-${fg.id})"/>`;
        out += `<text class="fel" data-el="${key}" x="${x + 44}" y="${y + 3}">${lbl(e.label)}</text>`;
      } else {
        const dir = cx(e.b) > cx(e.a) ? 1 : -1, x1 = cx(e.a) + 4 * dir, x2 = cx(e.b) - 6 * dir;
        out += `<path class="fe" data-el="${key}" data-ids="${e.ids.join(",")}" d="M${x1},${y} L${x2},${y}" marker-end="url(#fa-${fg.id})"><title>${lbl(e.label)}: ${e.ids.join(", ")}</title></path>`;
        out += `<text class="fel" data-el="${key}" x="${(x1 + x2) / 2}" y="${y - 6}" text-anchor="middle">${lbl(e.label)}</text>`;
      }
    });
    parts.forEach((p) => { out += `<g class="fn" data-el="${p.id}" data-ids=""><rect x="${cx(p.id) - CW / 2 + 8}" y="6" width="${CW - 16}" height="32" rx="8"/><text x="${cx(p.id)}" y="26.5" text-anchor="middle">${lbl(p.label)}</text></g>`; });
    out += `<circle class="token" r="5.5" opacity="0"/>`;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "sfig-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", fg.title.replace(/<[^>]+>/g, ""));
    svg.style.maxWidth = Math.ceil(W * 1.6) + "px";
    svg.style.minWidth = Math.min(Math.ceil(W * 0.9), 520) + "px";
    svg.innerHTML = out;
    return { svg, geo: null };
  }

  async function renderChapter(slug) {
    const f = fileMeta(slug);
    const F = await loadFile(slug);
    const secs = F.sections.slice(1);
    const order = ordered();
    const idx = order.findIndex((x) => x.slug === slug);
    const prev = order[idx - 1], next = order[idx + 1];
    const uses = B.links.filter((l) => l.from === slug).slice(0, 6);
    const usedBy = B.links.filter((l) => l.to === slug).slice(0, 6);
    let n = 0;
    const secId = (s) => `sec-${(n++)}-${s.id}`;
    const ids = secs.map(secId);
    const chapNo = order.filter((x) => x.kind === "module").findIndex((x) => x.slug === slug) + 1;
    const st = F.story;
    const toc = (st ? `<a href="#story-top" data-sec="story-top">In brief</a>${st.sections.map((x, k) => `<a href="#story-${k}" data-sec="story-${k}" class="sub">${esc(x.plain)}</a>`).join("")}<div class="label L3" style="padding:14px 8px 8px">Ledger</div>` : "")
      + `<div class="${st ? "L3" : ""}">` + secs.map((s, k) => `<a href="#${ids[k]}" data-sec="${ids[k]}" class="${s.level > 2 ? "sub" : ""}">${esc(s.title.replace(/`/g, ""))}</a>`).join("") + "</div>";
    const body = secs.map((s, k) => {
      const h = s.level === 2 ? `<h2 id="${ids[k]}">${s.th}</h2>` : `<h3 id="${ids[k]}">${s.th}</h3>`;
      return (s.level === 2 ? `</section><section class="sec">` : "") + h + s.blocks.map((b) => blockHTML(b, F)).join("");
    }).join("");
    view.innerHTML = `<div class="chapter">
      <nav class="toc" aria-label="Sections"><div class="label">${f.kind === "module" ? "Chapter " + chapNo : "Reference"}</div>${toc}</nav>
      <article style="min-width:0">
        <header class="ch-head">
          <div class="kicker">${f.kind === "module" ? `<span class="label">Chapter ${chapNo} · ${esc(pretty(f.module))}</span>` : `<span class="label">Reference</span>`}<span class="label mono" style="letter-spacing:0">${esc(f.prefix || "")}</span>${pill(f.status)}</div>
          <h1>${esc(shortTitle(f))}</h1>
          <div class="ch-meta">
            ${meter(f)}
            ${f.evidence ? `<span class="kv" title="Share of this chapter's confirmed behavior claims that a script ran against the real code and confirmed"><b>${fmtPct(f.evidence)}</b> run against the code</span>` : ""}
            ${glyphCounts(f.claims)}
            <span class="kv">${f.story ? `<span><b>${Math.max(1, Math.round(f.story.words / 238))}</b> min story</span><span><b>${readingMinutes(f)}</b> min ledger</span>` : `<span><b>${readingMinutes(f)}</b> min read</span>`}${f.defects ? `<span><b>${f.defects}</b> suspected defects</span>` : ""}</span>
          </div>
          ${uses.length ? `<div class="neighbors L2"><span>Cites</span>${uses.map((l) => `<a href="#${l.to}" title="${l.n} citations">${esc(nameOf(l.to))}</a>`).join("")}</div>` : ""}
          ${usedBy.length ? `<div class="neighbors L2"><span>Cited by</span>${usedBy.map((l) => `<a href="#${l.from}" title="${l.n} citations">${esc(nameOf(l.from))}</a>`).join("")}</div>` : ""}
          ${f.scope ? `<details class="scope L3"><summary>${f.scope.length} source files in scope</summary>${f.scope.map(esc).join("<br>")}</details>` : ""}
        </header>
        ${st ? `<div id="story-top">${storyHTML(st, f)}</div>` : `<p class="nostory L1">This chapter has no plain-language story yet, so every reading level shows its full ledger.</p>`}
        <section class="sec${st ? " L3" : ""}">${body}</section>
        <nav class="pager">${prev ? `<a href="#${prev.slug}"><span>Previous</span><b>${esc(shortTitle(prev))}</b></a>` : "<span></span>"}${next ? `<a href="#${next.slug}"><span>Next</span><b>${esc(shortTitle(next))}</b></a>` : ""}</nav>
      </article></div>`;
    // source viewer: expands in place, loads the file's snippets once
    view.addEventListener("click", onRefClick);
    cleanup.push(() => view.removeEventListener("click", onRefClick));
    // scroll spy
    const links = $$(".toc a", view);
    const io = new IntersectionObserver((ents) => {
      ents.forEach((e) => { if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.dataset.sec === e.target.id)); });
    }, { rootMargin: "-80px 0px -70% 0px" });
    $$("h2[id], h3[id], #story-top, .st-sec[id]", view).forEach((h) => io.observe(h));
    if (st) {
      defineTerms($("#story-top", view), st.words);
      const figs = st.sections.flatMap((x) => x.blocks.filter((b) => b.t === "fig"));
      for (const fg of figs) { const el = $(`.sfig[data-fig="${fg.id}"]`, view); if (el) drawFigure(el, fg); }
    }
    cleanup.push(() => io.disconnect());
    $$(".toc a", view).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); document.getElementById(a.dataset.sec)?.scrollIntoView({ behavior: motionOn() ? "smooth" : "auto" }); }));
  }
  async function onRefClick(e) {
    const b = e.target.closest(".ref");
    if (!b) return;
    const li = b.closest(".claim");
    const open = b.getAttribute("aria-expanded") === "true";
    $$(".ref", li).forEach((x) => x.setAttribute("aria-expanded", "false"));
    li.querySelector(".src")?.remove();
    if (open) return;
    b.setAttribute("aria-expanded", "true");
    const slug = B.owner[li.id];
    const sn = (await loadSnips(slug))[b.dataset.ref];
    li.querySelector(".body").insertAdjacentHTML("beforeend", srcHTML(b.dataset.ref, sn));
  }

  /* ---------- flow walkthrough ---------- */
  async function renderFlow(fl) {
    const i = B.flows.indexOf(fl);
    const c = flowColor(i);
    const parts = ["caller"];
    fl.steps.forEach((st) => st.who.forEach((w) => { if ((fileMeta(w) || {}).kind === "module" && !parts.includes(w)) parts.push(w); }));
    const prim = fl.steps.map((st) => st.who.find((w) => parts.includes(w)) || "caller");
    const CW = 118, TOP = 58, RH = 58, W = parts.length * CW + 90, H = TOP + fl.steps.length * RH + 24;
    // an arrow is labelled with the first code name its step mentions (what is called or written)
    const lab = (st) => { const m = st.h.match(/<code>([^<]{2,40})<\/code>/); return m ? m[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&").replace(/\(.*$/, "()").slice(0, 28) : ""; };
    const cx = (p) => parts.indexOf(p) * CW + CW / 2;
    let s = `<svg class="seq" viewBox="0 0 ${W} ${H}" role="img" aria-label="Sequence of the ${fl.steps.length} steps across ${parts.length - 1} chapters">
      <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>`;
    parts.forEach((p) => { s += `<line class="life" x1="${cx(p)}" y1="${TOP - 8}" x2="${cx(p)}" y2="${H - 8}"/>`; });
    fl.steps.forEach((st, k) => {
      const y = TOP + k * RH + RH / 2, from = k ? prim[k - 1] : "caller", to = prim[k];
      st.who.filter((w) => parts.includes(w) && w !== to).forEach((w) => { s += `<circle class="touch" data-k="${k}" cx="${cx(w)}" cy="${y}" r="7"/>`; });
      s += `<rect class="act" data-k="${k}" x="${cx(to) - 5}" y="${y - RH / 2 + 8}" width="10" height="${RH - 16}" rx="3"/>`;
      if (from === to) {
        const x = cx(to) + 6;
        s += `<path class="msg" data-k="${k}" d="M${x},${y - 12} C${x + 44},${y - 16} ${x + 44},${y + 12} ${x + 2},${y + 10}" marker-end="url(#ah)"/>`;
        s += `<text class="mlabel" data-k="${k}" x="${x + 46}" y="${y + 4}">${k + 1}${lab(st) ? " " + esc(lab(st)) : ""}</text>`;
      } else {
        const x1 = cx(from) + (cx(to) > cx(from) ? 6 : -6), x2 = cx(to) + (cx(to) > cx(from) ? -7 : 7);
        s += `<path class="msg" data-k="${k}" d="M${x1},${y} L${x2},${y}" marker-end="url(#ah)"/>`;
        s += `<text class="mlabel" data-k="${k}" x="${(x1 + x2) / 2}" y="${y - 7}" text-anchor="middle">${k + 1}${lab(st) && Math.abs(x2 - x1) > 150 ? " " + esc(lab(st)) : ""}</text>`;
      }
    });
    parts.forEach((p) => {
      const label = p === "caller" ? "Caller" : nameOf(p);
      s += `<g class="head" data-p="${p}"><rect x="${cx(p) - CW / 2 + 6}" y="8" width="${CW - 12}" height="34" rx="8"/><text x="${cx(p)}" y="29" text-anchor="middle">${esc(label.length > 17 ? label.slice(0, 16) + "…" : label)}</text><title>${esc(p === "caller" ? "The caller" : shortTitle(fileMeta(p)))}</title></g>`;
    });
    s += `<circle class="packet" r="6" fill="${c}" stroke="var(--sheet)" stroke-width="2" opacity="0"/></svg>`;
    const prevF = B.flows[i - 1], nextF = B.flows[i + 1];
    view.innerHTML = `<div style="--c:${c}">
      <header class="flow-head"><div class="kicker"><i></i>Path ${i + 1} of ${B.flows.length}</div><h1>${esc(fl.title)}</h1></header>
      <div class="flow">
        <ol class="steps">${fl.steps.map((st, k) => `<li class="stepi" data-k="${k}"><span class="n">${k + 1}</span><div>
          <div class="who">${st.who.filter((w) => (fileMeta(w) || {}).kind === "module").map((w) => `<a href="#${w}">${esc(nameOf(w))}</a>`).join("")}</div>
          ${st.plain ? `<div class="tx L-plain">${st.plain}</div><div class="tx L3 exact"><span class="label">Exact</span> ${st.h}</div>` : `<div class="tx">${st.h}</div>`}</div></li>`).join("")}</ol>
        <aside class="stage" aria-label="Sequence diagram"><div class="controls"><span class="label">Step <span id="stepno" class="num">1</span> of ${fl.steps.length}</span>
          <span style="display:flex;gap:6px"><button class="btn" id="s-prev" aria-label="Previous step">←</button><button class="btn" id="s-play" aria-pressed="false">Play</button><button class="btn" id="s-next" aria-label="Next step">→</button></span></div>
          <div class="seq-scroll">${s}</div></aside>
      </div>
      <nav class="pager">${prevF ? `<a href="#${prevF.id}"><span>Previous path</span><b>${esc(prevF.title)}</b></a>` : "<span></span>"}${nextF ? `<a href="#${nextF.id}"><span>Next path</span><b>${esc(nextF.title)}</b></a>` : ""}</nav></div>`;
    const svg = $(".seq", view), packet = $(".packet", svg), steps = $$(".stepi", view);
    let cur = -1, timer = null;
    const set = (k, animate) => {
      if (k === cur || k < 0 || k >= steps.length) return;
      cur = k;
      $("#stepno").textContent = k + 1;
      steps.forEach((el, j) => el.classList.toggle("on", j === k));
      $$(".msg", svg).forEach((m) => { const j = +m.dataset.k; m.classList.toggle("on", j === k); m.classList.toggle("past", j < k); });
      $$(".mlabel", svg).forEach((m) => m.classList.toggle("on", +m.dataset.k === k));
      $$(".act", svg).forEach((m) => m.classList.toggle("on", +m.dataset.k === k));
      $$(".touch", svg).forEach((m) => m.classList.toggle("on", +m.dataset.k === k));
      const who = new Set(fl.steps[k].who.concat(k ? [] : ["caller"]));
      $$(".head", svg).forEach((h) => h.classList.toggle("on", who.has(h.dataset.p) || h.dataset.p === prim[k]));
      const msg = $(`.msg[data-k="${k}"]`, svg);
      const sc = $(".seq-scroll", view);
      const bb = msg.getBBox(), scale = svg.getBoundingClientRect().height / H;
      if (sc.scrollHeight > sc.clientHeight) sc.scrollTo({ top: Math.max(0, bb.y * scale - sc.clientHeight / 2), behavior: motionOn() ? "smooth" : "auto" });
      if (animate && motionOn()) {
        const L = msg.getTotalLength(), t0 = performance.now(), dur = 520 + L * 1.6, me = k;
        const tick = (t) => {
          if (cur !== me) return;
          const q = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - q, 3), p = msg.getPointAtLength(e * L);
          packet.setAttribute("cx", p.x); packet.setAttribute("cy", p.y); packet.setAttribute("opacity", q < 1 ? "1" : "0");
          if (q < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }
    };
    steps.forEach((el) => el.addEventListener("click", (e) => { if (!e.target.closest("a")) set(+el.dataset.k, true); }));
    $("#s-prev").onclick = () => set(cur - 1, true);
    $("#s-next").onclick = () => set(cur + 1, true);
    const stop = () => { clearInterval(timer); timer = null; $("#s-play").setAttribute("aria-pressed", "false"); $("#s-play").textContent = "Play"; };
    $("#s-play").onclick = () => {
      if (timer) return stop();
      $("#s-play").setAttribute("aria-pressed", "true"); $("#s-play").textContent = "Pause";
      if (cur >= steps.length - 1) set(0, true);
      timer = setInterval(() => { if (cur >= steps.length - 1) stop(); else { set(cur + 1, true); steps[cur].scrollIntoView({ block: "center", behavior: motionOn() ? "smooth" : "auto" }); } }, 2600);
    };
    cleanup.push(stop);
    const io = new IntersectionObserver((ents) => {
      if (timer) return;
      const vis = ents.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (vis.length) set(+vis[0].target.dataset.k, true);
    }, { rootMargin: "-35% 0px -55% 0px" });
    steps.forEach((el) => io.observe(el));
    cleanup.push(() => io.disconnect());
    set(0, false);
  }

  /* ---------- claim popover ---------- */
  const pop = $("#pop");
  let popTimer = null, popFor = null;
  function hidePop() { clearTimeout(popTimer); pop.hidden = true; popFor = null; }
  async function showPop(a) {
    const id = a.dataset.id, slug = B.owner[id];
    if (!slug) return;
    popFor = a;
    const F = await loadFile(slug);
    const c = F.claims[id];
    if (!c || popFor !== a) return;
    const f = fileMeta(slug);
    pop.innerHTML = `<div class="ph"><span><i class="g ${c.conf}" style="vertical-align:-1px;margin-right:6px"></i>${id} · ${esc(nameOf(slug))}</span><a href="#${id}">Open in chapter →</a></div><div>${c.h}</div><div class="refs" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px">${c.refs.map((r) => `<span class="ref" style="cursor:default">${esc(refLabel(r))}</span>`).join("")}</div>`;
    pop.hidden = false;
    if (matchMedia("(max-width: 640px)").matches) return;
    const r = a.getBoundingClientRect(), pr = pop.getBoundingClientRect();
    let top = r.bottom + 8;
    if (top + pr.height > innerHeight - 12) top = Math.max(12, r.top - pr.height - 8);
    pop.style.top = top + "px";
    pop.style.left = Math.min(Math.max(12, r.left - 20), innerWidth - pr.width - 12) + "px";
    void f;
  }
  function initPop() {
    const fine = matchMedia("(hover: hover) and (pointer: fine)");
    document.addEventListener("mouseover", (e) => {
      if (!fine.matches) return;
      const a = e.target.closest("a.xr");
      if (a && a !== popFor) { clearTimeout(popTimer); popTimer = setTimeout(() => showPop(a), 220); }
      else if (!a && !e.target.closest("#pop")) { clearTimeout(popTimer); popTimer = setTimeout(hidePop, 260); }
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { hidePop(); closeSearch(); } });
    document.addEventListener("click", (e) => { if (!e.target.closest("#pop") && !e.target.closest("a.xr")) hidePop(); });
  }

  /* ---------- search ---------- */
  let index = null;
  async function buildIndex(status) {
    if (index) return index;
    const slugs = B.files.map((f) => f.slug);
    let done = 0;
    const all = await Promise.all(slugs.map(async (s) => { const F = await loadFile(s); status(`Loading chapters… ${++done}/${slugs.length}`); return F; }));
    index = [];
    all.forEach((F) => Object.values(F.claims).forEach((c) => index.push({ id: c.id, slug: F.slug, plain: c.plain, low: (c.id + " " + c.plain + " " + c.refs.join(" ")).toLowerCase() })));
    return index;
  }
  function openSearch() {
    const s = $("#search");
    s.hidden = false;
    const inp = $("#q"), out = $("#results"), st = $("#qst");
    inp.value = ""; out.innerHTML = ""; inp.focus();
    let sel = -1;
    const run = async () => {
      const q = inp.value.trim().toLowerCase();
      const ix = await buildIndex((m) => (st.textContent = m));
      if (!q) { st.textContent = `${ix.length.toLocaleString()} claims. Search words, a claim ID or a file path.`; out.innerHTML = ""; return; }
      const terms = q.split(/\s+/).filter(Boolean);
      const hits = ix.filter((r) => terms.every((t) => r.low.includes(t)))
        .map((r) => ({ r, s: (r.id.toLowerCase() === q ? 1000 : 0) + terms.reduce((a, t) => a + r.low.split(t).length - 1, 0) - r.plain.length / 2000 }))
        .sort((a, b) => b.s - a.s).slice(0, 60);
      st.textContent = hits.length ? `${hits.length === 60 ? "Top 60" : hits.length} matching claims` : "No claim matches every word. Try fewer words.";
      const rx = new RegExp(terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "gi");
      out.innerHTML = hits.map(({ r }) => `<a href="#${r.id}"><span class="rid">${r.id} · ${esc(nameOf(r.slug))}</span><span>${esc(r.plain.length > 260 ? r.plain.slice(0, 260) + "…" : r.plain).replace(rx, (m) => `<mark>${m}</mark>`)}</span></a>`).join("");
      sel = -1;
    };
    let deb;
    inp.oninput = () => { clearTimeout(deb); deb = setTimeout(run, 120); };
    inp.onkeydown = (e) => {
      const items = $$("#results a");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); sel = Math.max(0, Math.min(items.length - 1, sel + (e.key === "ArrowDown" ? 1 : -1)));
        items.forEach((a, k) => a.classList.toggle("sel", k === sel)); items[sel]?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && items.length) { (items[sel] || items[0]).click(); }
    };
    out.onclick = (e) => { if (e.target.closest("a")) closeSearch(); };
    s.onclick = (e) => { if (e.target === s) closeSearch(); };
    run();
  }
  function closeSearch() { $("#search").hidden = true; }

  /* ---------- boot ---------- */
  async function boot() {
    initChrome();
    initPop();
    try { B = await getJSON("data/book.json"); }
    catch (e) { view.innerHTML = `<p class="empty">The book's data did not load (${esc(e.message)}). Serve this folder over HTTP, or open the published page.</p>`; return; }
    const sysName = (B.title || "Specification").replace(/:\s*overview$/i, "");
    $("#brand-name").textContent = sysName;
    $("#foot").innerHTML = `<span>${esc(sysName)} · compiled from <a href="${esc(B.repo)}/tree/${esc(B.commit)}" target="_blank" rel="noopener">${esc(B.commit.slice(0, 10))}</a></span><span>${B.stats.claims.toLocaleString()} claims · generated by spec-from-code</span>`;
    addEventListener("hashchange", route);
    route();
  }
  boot();
})();
