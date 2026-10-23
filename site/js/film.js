/* The opening film. It plays once per browser session over the home page hero,
   then fades out to reveal it. The video is a grey master; this script prints it
   in the site's two inks with an 8x8 ordered dither at the screen's own pixels,
   so it stays sharp at any size. Only the deep red of UNKNOWN passes through.

   Without JavaScript, under reduced motion, without autoplay or without a
   playable video, nothing happens and the hero stands as it is. */
(function () {
  "use strict";
  var film = document.getElementById("film"), hero = document.getElementById("hero");
  if (!film || !hero) return;
  var KEY = "mp-film-seen", replay = hero.querySelector(".film-replay");
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var seen = false;
  try { seen = sessionStorage.getItem(KEY) === "1"; } catch (e) { /* storage blocked: play once per load */ }
  if (reduced) return;
  if (replay) { replay.hidden = false; replay.addEventListener("click", function () { start(true); }); }
  if (!seen) start(false);

  function start(fromReplay) {
    var video = document.createElement("video");
    var small = Math.max(screen.width, screen.height) * (window.devicePixelRatio || 1) < 1600;
    // H.264 where the browser has it, VP9 otherwise (some Linux builds ship without H.264)
    var webm = video.canPlayType('video/mp4; codecs="avc1.640028"') === "" && video.canPlayType('video/webm; codecs="vp9"') !== "";
    video.src = film.getAttribute((small ? "data-src-small" : "data-src") + (webm ? "-webm" : ""));
    video.muted = true; video.playsInline = true; video.preload = "auto";
    video.setAttribute("muted", ""); video.setAttribute("playsinline", "");
    var stage = film.querySelector(".film-stage"), card = film.querySelector(".film-card");
    var pause = film.querySelector(".film-pause"), skip = film.querySelector(".film-skip");
    var canvas = document.createElement("canvas"), gl = dither(canvas);
    stage.textContent = "";
    // without WebGL the grey master plays as it is
    stage.appendChild(gl ? canvas : video);
    var done = false, raf = 0, observer = null;
    try { sessionStorage.setItem(KEY, "1"); } catch (e) { /* fine */ }

    var giveUp = setTimeout(function () { if (video.readyState < 3) finish(true); }, fromReplay ? 8000 : 3000);
    video.addEventListener("canplay", function once() {
      video.removeEventListener("canplay", once); clearTimeout(giveUp);
      var p = video.play();
      if (p && p.catch) p.catch(function () { finish(true); });
      show();
    });
    video.addEventListener("ended", ending);
    video.addEventListener("error", function () { finish(true); });

    // on tall layouts (phones: the globe stacks under the words) the hero runs far
    // past the screen, so the panel takes only the part of it that is in view
    function fit() {
      var top = Math.max(0, hero.getBoundingClientRect().top), room = window.innerHeight - top;
      film.style.height = hero.offsetHeight > room + 40 ? Math.max(320, room) + "px" : "";
    }
    function show() {
      fit(); window.addEventListener("resize", fit);
      film.hidden = false; card.hidden = true;
      hero.classList.add("film-on");
      requestAnimationFrame(function () { film.classList.add("in"); });
      skip.focus({ preventScroll: true });
      if (gl) loop();
      // scrolling the hero out of view skips the film
      if ("IntersectionObserver" in window) {
        observer = new IntersectionObserver(function (es) { if (!es[0].isIntersecting) finish(false); }, { threshold: 0.25 });
        observer.observe(hero);
      }
    }
    function loop() {
      if (done) return;
      if (video.readyState >= 2) gl.draw(video);
      raf = requestAnimationFrame(loop);
    }
    // the end card, if there is approved copy for one: its lines fade in on paper, hold,
    // then the card breaks into dots and drifts away, uncovering the hero underneath
    var endCard = null;
    function ending() {
      if (!card.querySelector("p")) { finish(false); return; }
      cancelAnimationFrame(raf); pause.hidden = true;
      card.hidden = false; // the words, for screen readers; the canvas shows them
      endCard = endCardCanvas(film, [].map.call(card.querySelectorAll("p"), function (p) { return p.textContent; }));
      endCard.run(function () { hero.classList.remove("film-on"); stage.textContent = ""; film.classList.add("clear"); },
                  function () { finish(true, true); });
    }
    function finish(quiet, dissolved) {
      if (done) return; done = true;
      clearTimeout(giveUp); cancelAnimationFrame(raf);
      if (endCard) endCard.stop();
      if (observer) observer.disconnect();
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", fit);
      video.pause();
      film.classList.remove("in");
      hero.classList.remove("film-on");
      setTimeout(function () {
        film.hidden = true; card.hidden = true; film.classList.remove("clear");
        if (endCard) { endCard.remove(); endCard = null; }
        pause.hidden = false; pause.textContent = "Pause";
        stage.textContent = ""; video.removeAttribute("src"); video.load();
      }, quiet ? 0 : 700);
      if ((!quiet || dissolved) && film.contains(document.activeElement)) {
        var h = hero.querySelector("h1"); if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
      }
    }
    function onKey(e) { if (e.key === "Escape") finish(false); }
    document.addEventListener("keydown", onKey);
    skip.onclick = function () { finish(false); };
    pause.onclick = function () {
      if (video.paused) { video.play(); pause.textContent = "Pause"; } else { video.pause(); pause.textContent = "Play"; }
    };
  }

  // The end card on a canvas, so the same pixels can come apart. Timings in seconds.
  var LINE_IN = [0.2, 1.2, 2.1], FADE = 0.6, HOLD_UNTIL = 7.2, DISSOLVE = 1.8;
  function endCardCanvas(film, lines) {
    var cv = document.createElement("canvas"); cv.className = "film-end";
    film.insertBefore(cv, film.querySelector(".film-controls"));
    var x = cv.getContext("2d"), dpr = window.devicePixelRatio || 1, W, H, raf = 0, t0 = 0;
    var cs = getComputedStyle(document.documentElement);
    var PAPER = cs.getPropertyValue("--ground").trim() || "#F7F4EE", INK = cs.getPropertyValue("--ink").trim() || "#1A1A1A",
        SOFT = cs.getPropertyValue("--ink-soft").trim() || "#55524C", FONT = cs.getPropertyValue("--font-display").trim() || "Georgia, serif";
    var layout = [], particles = null, cells = null, CELL = 6;
    function size() {
      W = film.clientWidth; H = film.clientHeight; cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      x.setTransform(dpr, 0, 0, dpr, 0, 0);
      var clampv = function (lo, v, hi) { return Math.max(lo, Math.min(hi, v)); };
      var pad = clampv(20, W * 0.1, 144), big = clampv(32, W * 0.05, 67), small = clampv(18, W * 0.024, 30), maxW = Math.min(W - 2 * pad, 30 * big * 0.52);
      layout = []; var y = 0;
      lines.forEach(function (text, i) {
        var fs = i ? small : big, font = (i ? "400 " : "italic 500 ") + fs + "px " + FONT, lh = fs * (i ? 1.3 : 1.05);
        x.font = font; var words = text.split(" "), line = "", rows = [];
        words.forEach(function (w) { var tryL = line ? line + " " + w : w; if (x.measureText(tryL).width > maxW && line) { rows.push(line); line = w; } else line = tryL; });
        rows.push(line);
        rows.forEach(function (r) { layout.push({ text: r, font: font, y: y + fs, i: i }); y += lh; });
        y += i ? small * 0.4 : big * 0.5;
      });
      var top = (H - y) / 2; layout.forEach(function (l) { l.x = pad; l.y += top; });
    }
    function paint(alphaFor) {
      x.clearRect(0, 0, W, H); x.fillStyle = PAPER; x.fillRect(0, 0, W, H);
      layout.forEach(function (l) { x.globalAlpha = alphaFor(l.i); x.font = l.font; x.fillStyle = l.i === 2 ? SOFT : INK; x.fillText(l.text, l.x, l.y); });
      x.globalAlpha = 1;
    }
    // freeze the finished card into particles (ink) and cells (paper)
    function shatter() {
      paint(function () { return 1; });
      var img = x.getImageData(0, 0, cv.width, cv.height).data, step = Math.max(2, Math.round(2 * dpr)), seed = 7;
      var rand = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      particles = [];
      for (var py = 0; py < cv.height; py += step) for (var px = 0; px < cv.width; px += step) {
        var o = (py * cv.width + px) * 4, l = img[o] + img[o + 1] + img[o + 2];
        if (l < 380) particles.push({ x: px / dpr, y: py / dpr, c: l < 200 ? INK : SOFT, d: (px / cv.width) * 0.75 + rand() * 0.2,
          vx: 20 + rand() * 60, vy: -30 - rand() * 70, s: step / dpr });
      }
      cells = [];
      for (var cy = 0; cy < H; cy += CELL) for (var cx = 0; cx < W; cx += CELL) cells.push({ x: cx, y: cy, d: (cx / W) * 0.75 + rand() * 0.25 });
    }
    function frame(now) {
      var t = (now - t0) / 1000;
      if (t < HOLD_UNTIL) {
        paint(function (i) { return Math.max(0, Math.min(1, (t - LINE_IN[i]) / FADE)); });
      } else {
        if (!particles) { shatter(); onClear(); }
        var p = (t - HOLD_UNTIL) / DISSOLVE;
        x.clearRect(0, 0, W, H);
        x.fillStyle = PAPER;
        cells.forEach(function (c) { if (p < c.d) x.fillRect(c.x, c.y, CELL, CELL); });
        particles.forEach(function (q) {
          var a = (p - q.d) / 0.35; if (a > 1) return;
          var k = Math.max(0, a), dt = k * 1.1;
          x.globalAlpha = 1 - k; x.fillStyle = q.c;
          x.fillRect(q.x + q.vx * dt + Math.sin(q.y * 0.05 + dt * 6) * 6 * k, q.y + q.vy * dt, q.s * (1 - k * 0.5), q.s * (1 - k * 0.5));
        });
        x.globalAlpha = 1;
        if (p >= 1.3) { done(); return; }
      }
      raf = requestAnimationFrame(frame);
    }
    var onClear, done;
    return {
      run: function (cleared, finished) {
        onClear = cleared; done = finished; size();
        var go = function () { t0 = performance.now(); raf = requestAnimationFrame(frame); };
        if (document.fonts && document.fonts.load) document.fonts.load("italic 500 40px " + FONT).then(go, go); else go();
      },
      stop: function () { cancelAnimationFrame(raf); },
      remove: function () { cancelAnimationFrame(raf); cv.remove(); },
    };
  }

  // The dither: one quad, the video as a texture, the threshold from an 8x8
  // Bayer matrix at device pixels (one dot per CSS pixel on high-density screens)
  function dither(canvas) {
    var gl = canvas.getContext("webgl", { antialias: false, premultipliedAlpha: false });
    if (!gl) return null;
    var vs = "attribute vec2 p; varying vec2 uv; void main(){ uv = p * .5 + .5; uv.y = 1. - uv.y; gl_Position = vec4(p, 0., 1.); }";
    var fs = [
      "precision mediump float;",
      "uniform sampler2D tex; uniform vec2 size; uniform vec4 box; uniform float dotSize;",
      "varying vec2 uv;",
      // the 8x8 Bayer value: the 2x2 pattern [0 2; 3 1], finest bit most significant
      "float bayer(vec2 q){ float v = 0., s = .25; for (int i = 0; i < 3; i++) {",
      "  vec2 m = mod(floor(q), 2.); v += (m.x * 2. + m.y * 3. - m.x * m.y * 4.) * s; s *= .25; q = floor(q / 2.); }",
      "  return v; }",
      "void main(){",
      "  vec2 px = floor(gl_FragCoord.xy / dotSize);",
      "  vec2 t = (uv - box.xy) / box.zw;",
      "  if (t.x < 0. || t.y < 0. || t.x > 1. || t.y > 1.) { gl_FragColor = vec4(.102, .102, .102, 1.); return; }",
      "  vec3 c = texture2D(tex, t).rgb;",
      "  if (c.r - c.g > .22 && c.r > .3) { gl_FragColor = vec4(.627, 0., .039, 1.); return; }",
      "  float l = dot(c, vec3(.2126, .7152, .0722));",
      "  l = clamp((l - .1) / .82, 0., 1.);",
      "  float th = (bayer(vec2(px.x, px.y)) * 64. + .5) / 64.;",
      "  gl_FragColor = l >= th ? vec4(.969, .957, .933, 1.) : vec4(.102, .102, .102, 1.);",
      "}"].join("\n");
    function sh(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; }
    var prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    gl.useProgram(prog);
    var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
    [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T].forEach(function (k) { gl.texParameteri(gl.TEXTURE_2D, k, gl.CLAMP_TO_EDGE); });
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    var uBox = gl.getUniformLocation(prog, "box"), uDot = gl.getUniformLocation(prog, "dotSize");
    return {
      draw: function (video) {
        var dpr = window.devicePixelRatio || 1, w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
        if (!w || !h) return;
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        gl.viewport(0, 0, w, h);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, video);
        // fit the 16:9 film inside the stage, letterboxed in ink
        var a = (video.videoWidth / video.videoHeight) || 16 / 9, sa = w / h, bw = 1, bh = 1;
        if (sa > a) bw = a / sa; else bh = sa / a;
        gl.uniform4f(uBox, (1 - bw) / 2, (1 - bh) / 2, bw, bh);
        gl.uniform1f(uDot, Math.max(1, Math.round(dpr)));
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      },
    };
  }
})();
