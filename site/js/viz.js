// The home page's figures and the Votes page's assembly. Enhancement only:
// the build already rendered the flat map as SVG and every state in the
// table, so without this script (or without d3) the page is complete.
// One payload feeds every figure: #viz-data, written at build time from
// approved content only.
(function () {
  "use strict";
  var dataEl = document.getElementById("viz-data");
  if (!dataEl) return;
  var PACK = JSON.parse(dataEl.textContent);
  var DATA = PACK.rows.slice().sort(function (a, b) { return a.n.localeCompare(b.n); });
  var CAP = PACK.captions;
  var POS = ["LBI-BAN", "LBI-OPEN", "REG-SOFT", "CCW-ONLY", "OPPOSE", "AMBIG"];
  var ROWS_ALL = POS.concat(["NONE", ""]);
  var PLAIN = PACK.plain; PLAIN[""] = "Not yet reviewed";
  var VWORD = {Y: "Yes", A: "Abstained", N: "No", X: "Did not vote"};
  var VORDER = ["Y", "A", "N", "X"];
  var YEARS = PACK.years, RES = PACK.resolutions;
  var CONF = PACK.conf;
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hasD3 = typeof window.d3 !== "undefined" && typeof window.topojson !== "undefined";
  function count(f) { return DATA.filter(f).length; }
  function mover(d) { var v = d.v.replace(/X/g, ""); for (var i = 1; i < v.length; i++) if (v[i] !== v[i - 1]) return true; return false; }
  var NMOVERS = count(mover);
  function fill(t, vars) { return t.replace(/\{(\w+)\}/g, function (_, k) { return vars[k] !== undefined ? vars[k] : ""; }); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function findState(q) { q = (q || "").trim().toLowerCase(); if (q.length < 2) return null; return DATA.find(function (d) { return d.n.toLowerCase().indexOf(q) === 0; }) || DATA.find(function (d) { return d.n.toLowerCase().indexOf(q) > -1; }) || null; }

  // ---- Shared tooltip: hover, focus, or tap; Escape or a tap elsewhere closes it ----
  function tipHTML(d) {
    var votes = d.v.split("").map(function (c, i) { return YEARS[i] + " " + VWORD[c]; }).join(" · ");
    var pos = !d.p ? "Not yet reviewed by this site"
      : d.p === "NONE" ? "No stated position found, reviewed " + d.s
      : PLAIN[d.p] + " (" + d.p + "), since " + d.s + ", " + (CONF[d.c] || "");
    return "<strong>" + esc(d.n) + "</strong><span class=\"viz-tip-r\">" + esc(d.r || "") + "</span>" +
      votes + "<br>" + esc(pos) + "<br><a href=\"" + PACK.base + "state/" + d.i + ".html\">Open the state page</a>";
  }
  function makeTip(wrap) {
    var tip = document.createElement("div"); tip.className = "viz-tip"; tip.hidden = true; wrap.appendChild(tip);
    var api = {
      pinned: false,
      show: function (d, cx, cy, pin) {
        tip.innerHTML = tipHTML(d); tip.hidden = false; api.pinned = !!pin;
        var b = wrap.getBoundingClientRect(), x = cx - b.left + 14, y = cy - b.top + 14;
        if (x + tip.offsetWidth > b.width) x = Math.max(0, cx - b.left - tip.offsetWidth - 14);
        if (y + tip.offsetHeight > b.height) y = Math.max(0, cy - b.top - tip.offsetHeight - 14);
        tip.style.left = x + "px"; tip.style.top = y + "px";
      },
      hide: function () { tip.hidden = true; api.pinned = false; }
    };
    document.addEventListener("click", function (e) { if (!tip.contains(e.target) && !wrap.contains(e.target)) api.hide(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") api.hide(); });
    return api;
  }
  function tokens() {
    var s = getComputedStyle(document.documentElement), g = function (k) { return s.getPropertyValue(k).trim(); };
    return {paper: g("--ground"), raise: g("--ground-raise"), ink: g("--ink"), soft: g("--ink-soft"), rule: g("--rule"), faint: g("--rule-faint"),
      hue: {"LBI-BAN": g("--pos-lbiban"), "LBI-OPEN": g("--pos-lbiopen"), "REG-SOFT": g("--pos-regsoft"), "CCW-ONLY": g("--pos-ccwonly"), "OPPOSE": g("--pos-oppose"), "AMBIG": g("--ground"), "NONE": g("--pos-none")}};
  }
  function pressed(sel, btn) { document.querySelectorAll(sel).forEach(function (x) { x.setAttribute("aria-pressed", x === btn ? "true" : "false"); }); }
  function setKey(el, kind) {
    if (!el) return;
    el.innerHTML = kind === "vote"
      ? VORDER.map(function (k) { return "<span><i class=\"vk vk-" + k + "\"></i>" + VWORD[k] + "</span>"; }).join("")
      : ROWS_ALL.map(function (k) { return "<span>" + PACK.swatch[k] + PLAIN[k] + "</span>"; }).join("");
  }

  // ---- The world: globe, flat map, and the states as dots ----
  function world(fig) {
    var wrap = fig.querySelector(".viz-stage"), poster = wrap.querySelector(".viz-poster");
    var canvas = document.createElement("canvas"); canvas.className = "viz-canvas";
    canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", "Interactive globe and charts of the 193 UN member states. The table below has every value.");
    var ctx = canvas.getContext("2d"), tip = makeTip(wrap), C = tokens();
    var VW = PACK.view[0], MAPH = PACK.view[1], VH = MAPH, CX = VW / 2, CY = MAPH / 2, FLAT = PACK.flatScale;
    var caption = fig.querySelector(".viz-caption"), key = fig.querySelector(".viz-key"), yearbar = fig.querySelector(".viz-yearbar");
    fetch(PACK.base + "assets/world.json").then(function (r) { if (!r.ok) throw new Error("world " + r.status); return r.json(); }).then(start).catch(function () { /* the static map stays */ });

    function start(topo) {
      var countries = topojson.feature(topo, topo.objects.countries).features;
      var byIso = new Map(DATA.map(function (d) { return [d.i, d]; }));
      countries.forEach(function (f) { f._d = byIso.get(f.properties.i); });
      wrap.insertBefore(canvas, poster); poster.setAttribute("hidden", ""); fig.classList.add("viz-live");

      var mutate = d3.geoProjectionMutator(function (a) { return function (x, y) { var p = d3.geoOrthographicRaw(x, y), q = d3.geoEqualEarthRaw(x, y); return [p[0] + a * (q[0] - p[0]), p[1] + a * (q[1] - p[1])]; }; });
      var alpha = 0, rot = [-20, -12, 0], proj = mutate(0), path = d3.geoPath(proj, ctx);
      function setProj() { mutate(alpha); proj.rotate(rot).translate([CX, CY]).scale(285 * (1 - alpha) + FLAT * alpha).precision(.4).clipAngle(alpha < .999 ? 90 + alpha * 89.9 : null); }

      var pat = {};
      function mkPat(code, draw) { var c = document.createElement("canvas"); c.width = c.height = 8; var x = c.getContext("2d"); x.fillStyle = C.hue[code]; x.fillRect(0, 0, 8, 8); draw(x); pat[code] = ctx.createPattern(c, "repeat"); }
      var tex = "rgba(255,255,255,.45)";
      mkPat("LBI-OPEN", function (x) { x.fillStyle = tex; x.fillRect(0, 6, 8, 1.5); });
      mkPat("REG-SOFT", function (x) { x.fillStyle = tex; x.fillRect(6, 0, 1.5, 8); x.fillRect(0, 6, 8, 1.5); });
      mkPat("CCW-ONLY", function (x) { x.strokeStyle = tex; x.lineWidth = 1.5; x.beginPath(); x.moveTo(0, 0); x.lineTo(8, 8); x.stroke(); });
      mkPat("OPPOSE", function (x) { x.fillStyle = tex; x.beginPath(); x.arc(4, 4, 1.3, 0, 7); x.fill(); });
      mkPat("AMBIG", function (x) { x.strokeStyle = "rgba(26,26,26,.55)"; x.lineWidth = 1.4; x.beginPath(); x.moveTo(0, 8); x.lineTo(8, 0); x.stroke(); });
      function posFill(d) { return !d || !d.p ? null : (pat[d.p] || C.hue[d.p]); }

      DATA.forEach(function (d) { d._x = CX; d._y = CY; d._r = 0; d._a = 0; });
      var view = "globe", year = 2, movers = false, mapA = 1, labels = [], labA = 0, hover = null, found = null, drag = null, tween = null, spinning = !reduce, pendingVH = null;
      // Dot layouts are computed for the space the reader actually has. The
      // canvas works in a 1100-unit-wide frame; on a phone that frame is
      // scaled down three times, so every size is scaled up by the same k
      // and the groups stack instead of sitting side by side.
      var PITCH = 17, RAD = 6.6, LW = 214, FS = 1, NARROW = false;
      function metrics() { var k = Math.max(1, VW / Math.max(1, wrap.clientWidth)); NARROW = wrap.clientWidth < 700; FS = NARROW ? k * .95 : 1; PITCH = NARROW ? 13 * k : 17; RAD = NARROW ? 5 * k : 6.6; LW = NARROW ? 20 : 214; }
      function pack(list, x0, y0, cols, out) { list.forEach(function (d, i) { out.set(d, [x0 + (i % cols) * PITCH + RAD, y0 + Math.floor(i / cols) * PITCH + RAD]); }); return Math.ceil(list.length / cols); }
      function groupLayout() {
        metrics();
        var out = new Map(), L = [], line = 22 * FS, y, cols = Math.floor((VW - 40) / PITCH);
        if (view === "vote") {
          if (NARROW) {
            y = 10;
            VORDER.forEach(function (k) { var list = DATA.filter(function (d) { return d.v[year] === k; }); L.push({x: 20, y: y + line * .8, t: String(list.length), s: VWORD[k], big: 1}); y += line + 6; y += Math.max(1, pack(list, 20, y, cols, out)) * PITCH + 14; });
          } else {
            var w = {Y: 18, A: 5, N: 5, X: 7}, x = 40;
            VORDER.forEach(function (k) { var list = DATA.filter(function (d) { return d.v[year] === k; }); L.push({x: x, y: 70, t: String(list.length), s: VWORD[k], big: 1}); pack(list, x, 92, w[k], out); x += Math.max(w[k] * PITCH, 110) + 46; });
            y = 92 + Math.ceil(count(function (d) { return d.v[year] === "Y"; }) / 18) * PITCH + 20;
          }
        } else if (view === "position") {
          y = 40 * (NARROW ? .4 : 1); var pc = NARROW ? cols : 46;
          ROWS_ALL.forEach(function (k) { if (k === "NONE") { L.push({rule: 1, y: y - 4}); y += 10; } var list = DATA.filter(function (d) { return d.p === k; });
            if (NARROW) { L.push({x: 20, y: y + line * .8, t: String(list.length), s: PLAIN[k]}); y += line + 4; y += (list.length ? pack(list, 20, y, pc, out) : 0) * PITCH + 12; }
            else { L.push({x: 20, y: y + 11, t: String(list.length), s: PLAIN[k]}); y += Math.max(1, pack(list, LW, y, pc, out)) * PITCH + 9; } });
        } else if (view === "matrix") {
          var w2 = NARROW ? {Y: 11, A: 4, N: 4, X: 4} : {Y: 16, A: 4, N: 4, X: 6}, colX = {}, x2 = LW;
          VORDER.forEach(function (k) { colX[k] = x2; x2 += Math.max(w2[k] * PITCH, NARROW ? 0 : 120) + (NARROW ? PITCH : 26); });
          L.push({x: LW, y: 26 * FS, t: "", s: YEARS[2] + " vote", big: 1});
          VORDER.forEach(function (k) { L.push({x: colX[k], y: 52 * FS, t: String(count(function (d) { return d.v[2] === k; })), s: NARROW ? {Y: "Yes", A: "Abst.", N: "No", X: "Absent"}[k] : VWORD[k]}); });
          y = 66 * FS;
          ROWS_ALL.forEach(function (r) { if (r === "NONE") { L.push({rule: 1, y: y - 4}); y += 10; }
            if (NARROW) { L.push({x: 20, y: y + line * .8, t: String(count(function (d) { return d.p === r; })), s: PLAIN[r]}); y += line + 4; }
            var h = NARROW ? 0 : 1;
            VORDER.forEach(function (k) { var list = DATA.filter(function (d) { return d.p === r && d.v[2] === k; }); if (list.length) h = Math.max(h, pack(list, colX[k], y, w2[k], out)); });
            if (!NARROW) L.push({x: 20, y: y + 11, t: String(count(function (d) { return d.p === r; })), s: PLAIN[r]});
            y += h * PITCH + (NARROW ? 12 : 8); });
        }
        return [out, L, Math.max(y + 10, 200)];
      }
      function geo() { return view === "globe" || view === "map"; }
      function visible(d) { return alpha > .98 || d3.geoDistance([d.lon, d.lat], [-rot[0], -rot[1]]) < Math.PI / 2 - .02; }
      function go(next, toRotOverride) {
        var from = {alpha: alpha, rot: rot.slice(), mapA: mapA, labA: labA};
        view = next; var gl = geo() ? [null, [], MAPH] : groupLayout(); labels = gl[1];
        // The canvas is as tall as the view needs: the map, or the stacked groups.
        var nh = gl[2];
        if (reduce) { pendingVH = null; wrap.classList.remove("h-anim"); wrap.style.height = ""; if (nh !== VH) { VH = nh; size(); } }
        else if (nh !== VH || pendingVH !== null) {
          var cur = wrap.getBoundingClientRect().height;
          VH = Math.max(VH, nh); size();
          wrap.classList.remove("h-anim"); wrap.style.height = cur + "px"; void wrap.offsetHeight;
          wrap.classList.add("h-anim"); wrap.style.height = nh * scale + "px"; pendingVH = nh;
        }
        DATA.forEach(function (d) { d._fx = d._x; d._fy = d._y; d._fr = d._r; d._fa = d._a; d._grp = gl[0] ? gl[0].get(d) : null; });
        tween = {t0: performance.now(), dur: reduce ? 0 : 950, from: from,
          toAlpha: view === "globe" ? 0 : view === "map" ? 1 : alpha,
          toRot: toRotOverride || (view === "map" ? [0, 0, 0] : view === "globe" && from.alpha > .5 ? [-20, -12, 0] : rot.slice()),
          toMap: geo() ? 1 : 0, toLab: geo() ? 0 : 1};
        spinning = view === "globe" && !reduce && !toRotOverride;
        tip.hide(); describe();
      }
      function step(now) {
        var k = 1, e = 1;
        if (tween) { k = tween.dur ? Math.min(1, (now - tween.t0) / tween.dur) : 1; e = d3.easeCubicInOut(k); var f = tween.from;
          alpha = f.alpha + (tween.toAlpha - f.alpha) * e; rot = [0, 1, 2].map(function (i) { return f.rot[i] + (tween.toRot[i] - f.rot[i]) * e; });
          mapA = f.mapA + (tween.toMap - f.mapA) * e; labA = f.labA + (tween.toLab - f.labA) * e; }
        else if (spinning && !hover && !drag && document.visibilityState === "visible") rot[0] += .12;
        setProj();
        DATA.forEach(function (d) {
          var tx, ty, tr, ta;
          if (d._grp) { tx = d._grp[0]; ty = d._grp[1]; tr = RAD; ta = movers && view === "vote" && !mover(d) ? .16 : 1; }
          else { var p = proj([d.lon, d.lat]) || [CX, CY]; tx = p[0]; ty = p[1]; tr = 4.2; ta = d.sm && visible(d) ? 1 : 0; }
          if (tween) { d._x = d._fx + (tx - d._fx) * e; d._y = d._fy + (ty - d._fy) * e; d._r = d._fr + (tr - d._fr) * e; d._a = d._fa + (ta - d._fa) * e; }
          else { d._x = tx; d._y = ty; d._r = tr; d._a = ta; }
        });
        if (tween && k >= 1) { tween = null;
          if (pendingVH !== null) { VH = pendingVH; pendingVH = null; size(); wrap.classList.remove("h-anim"); wrap.style.height = ""; } }
        draw();
      }
      var scale = 1;
      function size() { var w = wrap.clientWidth, dpr = window.devicePixelRatio || 1; scale = w / VW; canvas.width = Math.round(w * dpr); canvas.height = Math.round(VH * scale * dpr); canvas.style.height = VH * scale + "px"; ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0); }
      function dot(d) {
        if (d._a <= .01 || d._r <= .1) return;
        ctx.globalAlpha = d._a; ctx.beginPath(); ctx.arc(d._x, d._y, d._r, 0, Math.PI * 2);
        if (view === "vote" && d._grp) {
          var v = d.v[year];
          if (v === "Y") { ctx.fillStyle = C.soft; ctx.fill(); }
          else if (v === "A") { ctx.fillStyle = C.paper; ctx.fill(); ctx.save(); ctx.clip(); ctx.fillStyle = C.soft; ctx.fillRect(d._x - d._r, d._y - d._r, d._r * 2, d._r); ctx.restore(); ctx.strokeStyle = C.soft; ctx.lineWidth = 1.3; ctx.stroke(); }
          else if (v === "N") { ctx.fillStyle = C.paper; ctx.fill(); ctx.strokeStyle = C.ink; ctx.lineWidth = 2.4; ctx.stroke(); }
          else { ctx.fillStyle = C.paper; ctx.fill(); ctx.strokeStyle = C.rule; ctx.lineWidth = 1.1; ctx.stroke(); }
        } else {
          var f = posFill(d);
          if (f) { ctx.fillStyle = f; ctx.fill(); ctx.strokeStyle = d.p === "AMBIG" ? C.soft : C.paper; ctx.lineWidth = d.p === "AMBIG" ? 1 : 1.4; ctx.stroke(); }
          else { ctx.fillStyle = C.paper; ctx.fill(); ctx.strokeStyle = C.soft; ctx.lineWidth = 1; ctx.stroke(); }
        }
        if (d === hover || d === found) { ctx.globalAlpha = 1; ctx.beginPath(); ctx.arc(d._x, d._y, d._r + 3, 0, Math.PI * 2); ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.stroke(); }
        ctx.globalAlpha = 1;
      }
      var grat = d3.geoGraticule10(), apath = d3.geoPath(proj);
      // Mid-morph the blended projection folds the far side of the globe over
      // the front, and a country cut by the moving clip edge can come back as
      // its complement. No real country covers half the globe, so a fill that
      // large is the artifact: skip it for that frame.
      function folded(f, sph) { return alpha > .001 && alpha < .999 && apath.area(f) > sph * .5; }
      function draw() {
        ctx.clearRect(0, 0, VW, VH);
        if (mapA > .01) {
          ctx.globalAlpha = mapA;
          ctx.beginPath(); path({type: "Sphere"}); ctx.fillStyle = C.raise; ctx.fill(); ctx.strokeStyle = C.rule; ctx.lineWidth = 1; ctx.stroke();
          ctx.beginPath(); path(grat); ctx.strokeStyle = C.faint; ctx.lineWidth = .6; ctx.stroke();
          var sph = alpha > .001 && alpha < .999 ? apath.area({type: "Sphere"}) : 0;
          countries.forEach(function (f) { if (sph && folded(f, sph)) return; var d = f._d, hot = d && (d === hover || d === found); ctx.beginPath(); path(f);
            ctx.fillStyle = !d ? C.faint : posFill(d) || C.paper; ctx.fill(); ctx.strokeStyle = hot ? C.ink : C.rule; ctx.lineWidth = hot ? 1.8 : .5; ctx.stroke(); });
          ctx.globalAlpha = 1;
        }
        DATA.forEach(dot);
        if (labA > .01) {
          ctx.globalAlpha = labA; ctx.textBaseline = "alphabetic";
          labels.forEach(function (l) {
            if (l.rule) { ctx.fillStyle = C.rule; ctx.fillRect(0, l.y, VW, 1); return; }
            var x = l.x, big = Math.round(19 * FS), small = Math.round(13 * FS), body = l.big ? "500 " + big + "px Newsreader, Georgia, serif" : small + "px system-ui, -apple-system, 'Segoe UI', sans-serif";
            if (l.t) { ctx.fillStyle = C.ink; ctx.font = "600 " + (l.big ? big : small) + "px system-ui, -apple-system, 'Segoe UI', sans-serif"; ctx.fillText(l.t, x, l.y); x += ctx.measureText(l.t + " ").width; }
            ctx.font = body; ctx.fillStyle = l.big ? C.ink : C.soft; ctx.fillText(l.s, x, l.y);
          });
          ctx.globalAlpha = 1;
        }
      }
      function pick(e) {
        var b = canvas.getBoundingClientRect(), x = (e.clientX - b.left) / scale, y = (e.clientY - b.top) / scale, best = null, bd = 9;
        DATA.forEach(function (d) { if (d._a < .5) return; var dd = Math.hypot(d._x - x, d._y - y); if (dd < Math.max(bd, d._r + 2)) { bd = dd; best = d; } });
        if (best || !geo() || mapA < .5) return best;
        // The morphing projection has no inverse, so the canvas does the hit test.
        var dpr = window.devicePixelRatio || 1, px = (e.clientX - b.left) * dpr, py = (e.clientY - b.top) * dpr;
        var f = countries.find(function (c) { if (!c._d) return false; ctx.beginPath(); path(c); return ctx.isPointInPath(px, py); });
        return f ? f._d : null;
      }
      canvas.addEventListener("pointerdown", function (e) { if (view === "globe") { drag = {x: e.clientX, y: e.clientY, r: rot.slice(), moved: false}; canvas.setPointerCapture(e.pointerId); } });
      canvas.addEventListener("pointermove", function (e) {
        if (drag) { var dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true; rot = [drag.r[0] + dx * .3, Math.max(-60, Math.min(60, drag.r[1] - dy * .3)), 0]; return; }
        var d = pick(e); hover = d; canvas.style.cursor = d ? "pointer" : view === "globe" ? "grab" : "default";
        if (d && !tip.pinned) tip.show(d, e.clientX, e.clientY, false); else if (!d && !tip.pinned) tip.hide();
      });
      canvas.addEventListener("pointerup", function (e) { var moved = drag && drag.moved; drag = null; if (moved) return; var d = pick(e); if (d) { tip.show(d, e.clientX, e.clientY, true); e.stopPropagation(); } });
      canvas.addEventListener("pointerleave", function () { hover = null; if (!tip.pinned) tip.hide(); });
      function vars() {
        return {year: YEARS[year], res: RES[year], Y: count(function (d) { return d.v[year] === "Y"; }), N: count(function (d) { return d.v[year] === "N"; }),
          A: count(function (d) { return d.v[year] === "A"; }), X: count(function (d) { return d.v[year] === "X"; }), movers: NMOVERS,
          reviewed: count(function (d) { return d.p; }), stated: count(function (d) { return d.p && d.p !== "NONE"; }), none: count(function (d) { return d.p === "NONE"; }), nr: count(function (d) { return !d.p; }), vote2025: YEARS[2]};
      }
      function describe(now) {
        var t = CAP[view] + (view === "vote" && movers ? " " + CAP.movers : ""), kind = view === "vote" ? "vote" : "pos";
        function apply() { caption.textContent = fill(t, vars()); if (key.dataset.kind !== kind) { setKey(key, kind); key.dataset.kind = kind; } caption.style.opacity = key.style.opacity = ""; }
        if (now || reduce) apply();
        else { if (key.dataset.kind !== kind) key.style.opacity = 0; if (caption.textContent !== fill(t, vars())) caption.style.opacity = 0; setTimeout(apply, 170); }
        fig.classList.toggle("is-geo", geo());
        if (yearbar) { yearbar.hidden = false; yearbar.classList.toggle("open", view === "vote"); yearbar.inert = view !== "vote"; }
      }
      fig.querySelectorAll("[data-view]").forEach(function (b) { b.addEventListener("click", function () { pressed("#" + fig.id + " [data-view]", b); go(b.dataset.view); }); });
      fig.querySelectorAll("[data-year]").forEach(function (b) { b.addEventListener("click", function () { year = +b.dataset.year; pressed("#" + fig.id + " [data-year]", b); go("vote"); }); });
      var mv = fig.querySelector(".viz-movers"); if (mv) mv.addEventListener("change", function () { movers = mv.checked; go("vote"); });
      var finder = fig.querySelector(".viz-find");
      if (finder) finder.addEventListener("input", function () {
        found = findState(finder.value);
        if (!found) { tip.hide(); return; }
        if (view === "globe") go("globe", [-found.lon, -Math.max(-50, Math.min(50, found.lat)), 0]);
        setTimeout(function () { if (!found) return; var b = canvas.getBoundingClientRect(); tip.show(found, b.left + found._x * scale, b.top + found._y * scale, true); }, reduce ? 0 : 960);
      });
      size(); var rz; window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(function () { if (geo()) { size(); draw(); } else { var keep = reduce; reduce = true; go(view); reduce = keep; } }, 150); });
      setProj(); describe(true); d3.timer(step);
    }
    // Before the globe loads (or without d3), the static flat map keeps its own caption.
    if (caption) caption.textContent = fill(CAP.map, {reviewed: count(function (d) { return d.p; })});
    setKey(key, "pos");
  }

  // ---- Strands: each state's three votes and its position ----
  function strands(fig) {
    var wrap = fig.querySelector(".viz-stage"), tip = makeTip(wrap), NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "viz-strands"); svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Each state's vote in " + YEARS.join(", ") + " and its position, as one thread per state. The table below has every value.");
    var scroller = document.createElement("div"); scroller.className = "viz-scroll"; scroller.appendChild(svg); wrap.insertBefore(scroller, wrap.firstChild); fig.classList.add("viz-live");
    var W = 1200, H = 860, TOP = 46, GAP = 12, BW = 16, X = [150, 420, 690, 960];
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    var AX = [YEARS[0] + " vote", YEARS[1] + " vote", YEARS[2] + " vote", "Position"], cats = [VORDER, VORDER, VORDER, ROWS_ALL];
    var HUE = {"LBI-BAN": "var(--pos-lbiban)", "LBI-OPEN": "var(--pos-lbiopen)", "REG-SOFT": "var(--pos-regsoft)", "CCW-ONLY": "var(--pos-ccwonly)", "OPPOSE": "var(--pos-oppose)", "AMBIG": "var(--ink-soft)", "NONE": "var(--pos-none)"};
    function keyOf(d, a) { return a < 3 ? d.v[a] : d.p; }
    function el(tag, attrs, parent) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; }
    var gS = el("g", {"class": "strands"}, svg), gB = el("g", {}, svg), onlyMovers = false, onlyRev = false, focus = null;
    var caption = fig.querySelector(".viz-caption");
    function layout() {
      gS.innerHTML = ""; gB.innerHTML = ""; tip.hide();
      var set = DATA.filter(function (d) { return (!onlyMovers || mover(d)) && (!onlyRev || d.p); });
      var unit = (H - TOP - 20 - GAP * 9) / set.length;
      var blocks = cats.map(function (cs, a) { var y = TOP, out = {}; cs.forEach(function (c) { if (a === 3 && c === "NONE") y += GAP * 2; var m = set.filter(function (d) { return keyOf(d, a) === c; }).length; out[c] = {y0: y, n: m}; if (m) y += m * unit + GAP; }); return out; });
      var slot = cats.map(function () { return new Map(); });
      cats.forEach(function (cs, a) { cs.forEach(function (c) {
        set.filter(function (d) { return keyOf(d, a) === c; }).sort(function (p, q) {
          var order = [a - 1, a + 1, a - 2, a + 2, 3];
          for (var i = 0; i < order.length; i++) { var b = order[i]; if (b < 0 || b > 3 || b === a) continue; var d1 = cats[b].indexOf(keyOf(p, b)) - cats[b].indexOf(keyOf(q, b)); if (d1) return d1; }
          return p.n.localeCompare(q.n);
        }).forEach(function (d, i) { slot[a].set(d, blocks[a][c].y0 + (i + .5) * unit); });
      }); });
      set.forEach(function (d) {
        var ys = [0, 1, 2, 3].map(function (a) { return slot[a].get(d); }), p = "M" + (X[0] + BW / 2) + "," + ys[0];
        for (var a = 1; a < 4; a++) { var x0 = X[a - 1] + BW / 2, x1 = X[a] - BW / 2, mx = (x0 + x1) / 2; p += " L" + x0 + "," + ys[a - 1] + " C" + mx + "," + ys[a - 1] + " " + mx + "," + ys[a] + " " + x1 + "," + ys[a] + " L" + (x1 + BW) + "," + ys[a]; }
        var path = el("path", {d: p, "class": "strand"}, gS); path._d = d;
        path.style.stroke = d.p ? HUE[d.p] : "var(--strand)"; if (d.p === "AMBIG") path.style.strokeDasharray = "4 3";
        path.style.strokeWidth = d.p ? Math.max(1.2, Math.min(2.4, unit * .8)) : Math.max(.8, Math.min(1.4, unit * .55));
      });
      cats.forEach(function (cs, a) {
        el("text", {x: X[a], y: 22, "class": "axis-t"}, gB).textContent = AX[a];
        cs.forEach(function (c) { var b = blocks[a][c]; if (!b.n) return;
          var r = el("rect", {x: X[a] - BW / 2, y: b.y0, width: BW, height: Math.max(2, b.n * unit), "class": "block"}, gB);
          if (a < 3) r.style.fill = "var(--ink-soft)"; else if (c) r.setAttribute("class", "block p-" + c); else r.style.fill = "var(--rule)"; r._a = a; r._c = c;
          var left = a === 0, t = el("text", {x: left ? X[a] - BW / 2 - 8 : X[a] + BW / 2 + 8, y: b.y0 + Math.max(2, b.n * unit) / 2 + 4, "class": "blk-t", "text-anchor": left ? "end" : "start"}, gB);
          t.innerHTML = "<tspan class=\"n\">" + b.n + "</tspan> " + esc(a < 3 ? VWORD[c] : PLAIN[c]);
          if (a > 0 && a < 3 && b.n * unit < 12) t.setAttribute("opacity", "0");
        });
      });
      var v = {n: set.length, straight: set.filter(function (d) { return d.v === "YYY"; }).length, movers: NMOVERS};
      caption.textContent = fill(onlyMovers ? CAP.strands_movers : CAP.strands, v);
      applyFocus();
    }
    function applyFocus() {
      var lit = focus ? (focus.d ? [focus.d] : DATA.filter(function (d) { return keyOf(d, focus.a) === focus.c; })) : null;
      gS.classList.toggle("focus", !!lit);
      gS.querySelectorAll(".strand").forEach(function (p) { p.classList.toggle("lit", !!lit && lit.indexOf(p._d) > -1); });
      if (lit) gS.querySelectorAll(".strand.lit").forEach(function (p) { gS.appendChild(p); });
    }
    gS.addEventListener("mousemove", function (e) { var p = e.target.closest(".strand"); if (!p) return; focus = {d: p._d}; applyFocus(); if (!tip.pinned) tip.show(p._d, e.clientX, e.clientY, false); });
    gS.addEventListener("click", function (e) { var p = e.target.closest(".strand"); if (p) { tip.show(p._d, e.clientX, e.clientY, true); e.stopPropagation(); } });
    gB.addEventListener("mousemove", function (e) { var r = e.target.closest("rect"); if (!r) return; focus = {a: r._a, c: r._c}; applyFocus(); });
    svg.addEventListener("mouseleave", function () { focus = null; applyFocus(); if (!tip.pinned) tip.hide(); });
    var finder = fig.querySelector(".viz-find");
    if (finder) finder.addEventListener("input", function () { var d = findState(finder.value); focus = d ? {d: d} : null; applyFocus();
      if (d) { var p = [].slice.call(gS.querySelectorAll(".strand")).find(function (x) { return x._d === d; }); if (p) { var b = p.getBoundingClientRect(); tip.show(d, b.left + b.width / 2, b.top, true); } } else tip.hide(); });
    var m = fig.querySelector(".viz-movers"), rv = fig.querySelector(".viz-reviewed");
    if (m) m.addEventListener("change", function () { onlyMovers = m.checked; layout(); });
    if (rv) rv.addEventListener("change", function () { onlyRev = rv.checked; layout(); });
    layout();
  }

  // ---- The assembly: one seat per state, filled from the left by vote ----
  function assembly(fig) {
    var wrap = fig.querySelector(".viz-stage"), tip = makeTip(wrap), NS = "http://www.w3.org/2000/svg";
    var N = DATA.length, RINGS = 8, R0 = 150, DR = 26, W = 2 * (R0 + RINGS * DR) + 300, CXa = W / 2, CYa = R0 + RINGS * DR + 20, H = CYa + 60;
    var svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "viz-assembly"); svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Hemicycle of 193 seats, one per member state, arranged by vote. The rosters below list every state.");
    var scroller = document.createElement("div"); scroller.className = "viz-scroll"; scroller.appendChild(svg); wrap.insertBefore(scroller, wrap.firstChild); fig.classList.add("viz-live");
    function el(tag, attrs, parent) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; }
    var radii = [], tot = 0; for (var i = 0; i < RINGS; i++) { radii.push(R0 + (i + .5) * DR); tot += radii[i]; }
    var per = radii.map(function (r) { return Math.round(N * r / tot); }); per[RINGS - 1] += N - per.reduce(function (a, b) { return a + b; }, 0);
    var seats = []; radii.forEach(function (r, i) { for (var k = 0; k < per[i]; k++) { var a = Math.PI * (1 - (k + .5) / per[i]); seats.push({x: CXa + r * Math.cos(a), y: CYa - r * Math.sin(a), a: a}); } });
    seats.sort(function (p, q) { return q.a - p.a || p.y - q.y; });
    var g0 = el("g", {}, svg), gL = el("g", {}, svg);
    var hero = el("text", {x: CXa, y: CYa - 26, "class": "hero-n"}, svg), heroL = el("text", {x: CXa, y: CYa + 2, "class": "hero-l"}, svg);
    var marks = DATA.map(function (d) { var g = el("g", {"class": "seat"}, g0); var c = el("circle", {r: 10.5}, g); var t = el("text", {}, g); t.textContent = d.a; g._d = d; g._c = c; g._t = t; return g; });
    var year = 2, colour = "vote", ord = {Y: 0, A: 1, N: 2, X: 3};
    function pord(k) { return k ? ROWS_ALL.indexOf(k) : 99; }
    function style(g) {
      var d = g._d, c = g._c, t = g._t; c.removeAttribute("style"); t.removeAttribute("style");
      g.setAttribute("class", "seat " + (colour === "vote" ? "sv-" + d.v[year] : (d.p ? "sp p-" + d.p + (d.c && d.c !== "EXPLICIT" && d.p !== "AMBIG" && d.p !== "NONE" ? " soft" : "") : "sp nr")));
    }
    var caption = fig.querySelector(".viz-caption"), key = fig.querySelector(".viz-key");
    function render() {
      tip.hide(); gL.innerHTML = "";
      marks.slice().sort(function (p, q) { return ord[p._d.v[year]] - ord[q._d.v[year]] || pord(p._d.p) - pord(q._d.p) || p._d.n.localeCompare(q._d.n); })
        .forEach(function (g, i) { var s = seats[i]; g.style.transform = "translate(" + s.x + "px," + s.y + "px)"; style(g); });
      var i = 0;
      VORDER.forEach(function (k) { var n = count(function (d) { return d.v[year] === k; }); if (!n) return; var mid = seats[i + Math.floor(n / 2)], rr = R0 + RINGS * DR + 16;
        var t = el("text", {x: CXa + rr * Math.cos(mid.a), y: CYa - rr * Math.sin(mid.a), "class": "lbl", "text-anchor": mid.a > Math.PI * .55 ? "end" : mid.a < Math.PI * .45 ? "start" : "middle"}, gL);
        t.innerHTML = "<tspan class=\"n\">" + n + "</tspan> " + VWORD[k]; i += n; });
      hero.textContent = count(function (d) { return d.v[year] === "Y"; }); heroL.textContent = "voted Yes on " + RES[year] + ", " + YEARS[year];
      var moved = year ? count(function (d) { return d.v[year] !== d.v[year - 1] && d.v[year] !== "X" && d.v[year - 1] !== "X"; }) : 0;
      caption.textContent = fill(colour === "vote" ? CAP.assembly + (year ? " " + CAP.assembly_moved : "") : CAP.assembly_position, {moved: moved, year: YEARS[year]});
      setKey(key, colour === "vote" ? "vote" : "pos");
    }
    g0.addEventListener("mousemove", function (e) { var g = e.target.closest(".seat"); if (g && !tip.pinned) tip.show(g._d, e.clientX, e.clientY, false); });
    g0.addEventListener("mouseleave", function () { if (!tip.pinned) tip.hide(); });
    g0.addEventListener("click", function (e) { var g = e.target.closest(".seat"); if (g) { tip.show(g._d, e.clientX, e.clientY, true); e.stopPropagation(); } });
    fig.querySelectorAll("[data-year]").forEach(function (b) { b.addEventListener("click", function () { year = +b.dataset.year; pressed("#" + fig.id + " [data-year]", b); render(); }); });
    fig.querySelectorAll("[data-colour]").forEach(function (b) { b.addEventListener("click", function () { colour = b.dataset.colour; pressed("#" + fig.id + " [data-colour]", b); render(); }); });
    var finder = fig.querySelector(".viz-find");
    if (finder) finder.addEventListener("input", function () { var d = findState(finder.value); marks.forEach(function (g) { g.classList.toggle("hit", g._d === d); });
      if (d) { var b = marks.find(function (g) { return g._d === d; }).getBoundingClientRect(); tip.show(d, b.right, b.top, true); } else tip.hide(); });
    render();
  }

  // ---- The state table: filter by name, sort by column ----
  function table(box) {
    var input = box.querySelector(".states-find"), body = box.querySelector("tbody"), rows = [].slice.call(body.rows), status = box.querySelector(".states-status");
    if (input) input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase(), n = 0;
      rows.forEach(function (r) { var hit = !q || r.getAttribute("data-name").toLowerCase().indexOf(q) > -1; r.hidden = !hit; if (hit) n++; });
      if (status) status.textContent = q ? n + " of " + rows.length + " states" : "";
    });
    box.querySelectorAll("th button[data-sort]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.getAttribute("data-sort"), asc = btn.getAttribute("aria-sort-dir") !== "asc";
        box.querySelectorAll("th").forEach(function (th) { th.removeAttribute("aria-sort"); });
        btn.closest("th").setAttribute("aria-sort", asc ? "ascending" : "descending"); btn.setAttribute("aria-sort-dir", asc ? "asc" : "desc");
        rows.sort(function (a, b) { var x = a.getAttribute("data-" + k), y = b.getAttribute("data-" + k); return (x < y ? -1 : x > y ? 1 : a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"))) * (asc ? 1 : -1); });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  }

  var w = document.getElementById("viz-world"); if (w && hasD3) world(w); else if (w) { var c0 = w.querySelector(".viz-caption"); if (c0) c0.textContent = fill(CAP.map, {reviewed: count(function (d) { return d.p; })}); setKey(w.querySelector(".viz-key"), "pos"); }
  var s = document.getElementById("viz-strands"); if (s) strands(s);
  var a = document.getElementById("viz-assembly"); if (a) assembly(a);
  var t = document.getElementById("states"); if (t) table(t);
})();
