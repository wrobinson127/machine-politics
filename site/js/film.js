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
    // the end card, if there is approved copy for one, then the hero
    function ending() {
      if (!card.querySelector("p")) { finish(false); return; }
      cancelAnimationFrame(raf); card.hidden = false; pause.hidden = true;
      requestAnimationFrame(function () { card.classList.add("in"); });
      setTimeout(function () { finish(false); }, 5200);
    }
    function finish(quiet) {
      if (done) return; done = true;
      clearTimeout(giveUp); cancelAnimationFrame(raf);
      if (observer) observer.disconnect();
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", fit);
      video.pause();
      film.classList.remove("in");
      hero.classList.remove("film-on");
      setTimeout(function () {
        film.hidden = true; card.hidden = true; card.classList.remove("in");
        pause.hidden = false; pause.textContent = "Pause";
        stage.textContent = ""; video.removeAttribute("src"); video.load();
      }, quiet ? 0 : 700);
      if (!quiet && film.contains(document.activeElement)) {
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
