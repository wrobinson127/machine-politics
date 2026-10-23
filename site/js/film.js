/* The opening film. It plays once per browser session over the home page hero,
   then fades out to reveal it. The video is a grey master; this script prints it
   in the site's two inks with an 8x8 ordered dither, one dot per CSS pixel, so it
   stays sharp at any size. It draws only when the video has a new frame and only
   while the film is on screen; on software WebGL (SwiftShader and the like) it
   skips the shader and the video, and shows a still poster instead.

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
  // Is WebGL software-rendered (SwiftShader and the like)? Asked in a throwaway worker:
  // on a software rasteriser, even a short-lived WebGL context on the page slows every
  // canvas drawn after it, so the page makes one only on real hardware.
  var gpu = null;
  function probeGpu(done) {
    if (gpu !== null) { done(gpu); return; }
    var src = "try{var c=new OffscreenCanvas(1,1),g=c.getContext('webgl');if(!g){postMessage('none')}else{var i=g.getExtension('WEBGL_debug_renderer_info');" +
      "postMessage(String(i?g.getParameter(i.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER)))}}catch(e){postMessage('unknown')}";
    var url, w, settle = function (r) { if (w) w.terminate(); if (url) URL.revokeObjectURL(url); gpu = r; done(r); };
    if (!window.Worker || !window.OffscreenCanvas) { settle("unknown"); return; }
    try {
      url = URL.createObjectURL(new Blob([src], { type: "text/javascript" })); w = new Worker(url);
      w.onmessage = function (e) { settle(/swiftshader|llvmpipe|softpipe|software|basic render/i.test(e.data) ? "software" : e.data === "none" ? "none" : "hardware"); };
      w.onerror = function () { settle("unknown"); };
    } catch (e) { settle("unknown"); }
  }

  if (!seen) start(false);

  function start(fromReplay) { probeGpu(function (g) { if (g === "software") poster(fromReplay); else play(fromReplay, g); }); }
  function play(fromReplay, g) {
    var probe = document.createElement("canvas"), gl = g === "none" ? null : dither(probe);
    var video = document.createElement("video");
    // the canvas is drawn at CSS pixels, so the 720p film covers anything under 1000 wide
    var small = (film.parentNode.clientWidth || innerWidth) < 1000;
    // H.264 where the browser has it, VP9 otherwise (some Linux builds ship without H.264)
    var webm = video.canPlayType('video/mp4; codecs="avc1.640028"') === "" && video.canPlayType('video/webm; codecs="vp9"') !== "";
    video.src = film.getAttribute((small ? "data-src-small" : "data-src") + (webm ? "-webm" : ""));
    video.muted = true; video.playsInline = true; video.preload = "auto";
    video.setAttribute("muted", ""); video.setAttribute("playsinline", "");
    var stage = film.querySelector(".film-stage"), card = film.querySelector(".film-card");
    var pause = film.querySelector(".film-pause"), skip = film.querySelector(".film-skip");
    var canvas = probe;
    stage.textContent = "";
    // without WebGL the grey master plays as it is
    stage.appendChild(gl ? canvas : video);
    var done = false, raf = 0, vfc = 0, observer = null, visible = true;
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
      document.addEventListener("visibilitychange", onVisibility);
      // scrolling the hero out of view skips the film
      if ("IntersectionObserver" in window) {
        observer = new IntersectionObserver(function (es) { if (!es[0].isIntersecting) finish(false); }, { threshold: 0.25 });
        observer.observe(hero);
      }
    }
    // one draw per new video frame (24 a second), not per display refresh
    function loop() {
      if (done || !visible || video.paused || video.ended) return;
      if (video.readyState >= 2) gl.draw(video);
      if (video.requestVideoFrameCallback) vfc = video.requestVideoFrameCallback(loop);
      else raf = requestAnimationFrame(loop);
    }
    function stopLoop() {
      cancelAnimationFrame(raf); raf = 0;
      if (vfc && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(vfc); vfc = 0;
    }
    // a background tab pauses the film and its drawing; coming back resumes both
    function onVisibility() {
      visible = document.visibilityState === "visible";
      if (!visible) { stopLoop(); video.pause(); }
      else if (!done && !endCard && pause.textContent === "Pause") { var q = video.play(); if (q && q.catch) q.catch(function () {}); }
    }
    video.addEventListener("play", function () { stopLoop(); if (gl) loop(); });
    video.addEventListener("pause", stopLoop);
    // the end card, if there is approved copy for one: its lines fade in on paper, hold,
    // then the card breaks into dots and drifts away, uncovering the hero underneath
    var endCard = null;
    function ending() {
      if (!card.querySelector("p")) { finish(false); return; }
      stopLoop(); pause.hidden = true;
      card.hidden = false; // the words, for screen readers; the canvas shows them
      endCard = endCardCanvas(film, [].map.call(card.querySelectorAll("p"), function (p) { return p.textContent; }));
      endCard.run(function () { hero.classList.remove("film-on"); stage.textContent = ""; film.classList.add("clear"); },
                  function () { finish(true, true); });
    }
    function finish(quiet, dissolved) {
      if (done) return; done = true;
      clearTimeout(giveUp); stopLoop();
      if (endCard) endCard.stop();
      document.removeEventListener("visibilitychange", onVisibility);
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

  // Software WebGL: no shader, no video decode. The still poster, then the end card.
  function poster(fromReplay) {
    var stage = film.querySelector(".film-stage"), card = film.querySelector(".film-card");
    var pause = film.querySelector(".film-pause"), skip = film.querySelector(".film-skip");
    var img = new Image(), endCard = null, done = false, timer = 0;
    img.alt = ""; img.src = film.getAttribute("data-poster");
    try { sessionStorage.setItem(KEY, "1"); } catch (e) { /* fine */ }
    function close() {
      if (done) return; done = true; clearTimeout(timer);
      if (endCard) endCard.remove();
      document.removeEventListener("keydown", onKey);
      film.classList.remove("in", "clear"); hero.classList.remove("film-on");
      setTimeout(function () { film.hidden = true; card.hidden = true; pause.hidden = false; stage.textContent = ""; }, 600);
      if (film.contains(document.activeElement)) { var h = hero.querySelector("h1"); if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); } }
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    img.onload = function () {
      stage.textContent = ""; stage.appendChild(img);
      film.hidden = false; pause.hidden = true; hero.classList.add("film-on");
      requestAnimationFrame(function () { film.classList.add("in"); });
      skip.onclick = close; document.addEventListener("keydown", onKey);
      timer = setTimeout(function () {
        if (!card.querySelector("p")) { close(); return; }
        card.hidden = false;
        endCard = endCardCanvas(film, [].map.call(card.querySelectorAll("p"), function (p) { return p.textContent; }));
        endCard.run(function () { hero.classList.remove("film-on"); stage.textContent = ""; film.classList.add("clear"); }, close);
      }, 2500);
    };
    img.onerror = function () { done = true; };
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
    var gl = canvas.getContext("webgl", { antialias: false, premultipliedAlpha: false, powerPreference: "low-power" });
    if (!gl) return null;
    var vs = "attribute vec2 p; varying vec2 uv; void main(){ uv = p * .5 + .5; uv.y = 1. - uv.y; gl_Position = vec4(p, 0., 1.); }";
    var fs = [
      "precision mediump float;",
      "uniform sampler2D tex; uniform vec4 box;",
      "varying vec2 uv;",
      // the 8x8 Bayer value: the 2x2 pattern [0 2; 3 1], finest bit most significant
      "float bayer(vec2 q){ float v = 0., s = .25; for (int i = 0; i < 3; i++) {",
      "  vec2 m = mod(floor(q), 2.); v += (m.x * 2. + m.y * 3. - m.x * m.y * 4.) * s; s *= .25; q = floor(q / 2.); }",
      "  return v; }",
      "void main(){",
      "  vec2 px = floor(gl_FragCoord.xy);",
      "  vec2 t = (uv - box.xy) / box.zw;",
      "  if (t.x < 0. || t.y < 0. || t.x > 1. || t.y > 1.) { gl_FragColor = vec4(.102, .102, .102, 1.); return; }",
      "  vec3 c = texture2D(tex, t).rgb;",
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
    var uBox = gl.getUniformLocation(prog, "box");
    return {
      draw: function (video) {
        // CSS pixels: one dot per CSS pixel, and a quarter of the work on a retina screen
        var w = Math.round(canvas.clientWidth), h = Math.round(canvas.clientHeight);
        if (!w || !h) return;
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        gl.viewport(0, 0, w, h);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, video);
        // fit the 16:9 film inside the stage, letterboxed in ink
        var a = (video.videoWidth / video.videoHeight) || 16 / 9, sa = w / h, bw = 1, bh = 1;
        if (sa > a) bw = a / sa; else bh = sa / a;
        gl.uniform4f(uBox, (1 - bw) / 2, (1 - bh) / 2, bw, bh);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      },
    };
  }
})();
