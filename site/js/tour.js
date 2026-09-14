// Scrollytelling behavior. The stacked prose and the classic board ARE
// the page; everything here is enhancement behind guards. Division of
// labor per the craft standard: Scrollama says WHEN, CSS sticky HOLDS,
// GSAP DRAWS; state application is CSS-transition-driven so it lands on
// final values even if rendering stalls. Motion is one tempo in every
// direction (neutrality in motion, DESIGN v2).
(function () {
  "use strict";
  var tour = document.querySelector(".tour");
  if (!tour) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var mobile = window.matchMedia("(max-width: 720px), (pointer: coarse)").matches;

  var canvas = document.getElementById("scrolly-canvas");
  var board = document.getElementById("c-board");

  // ---- Canvas machinery, shared by the scroll and stepper modes ----
  var setBeat = null;
  if (canvas && board) setBeat = initCanvas();

  function initCanvas() {
    var gsap = window.gsap;
    // Reduced-motion users get instant states everywhere: the CSS media
    // query zeroes the transitions, and the flag below turns off the one
    // GSAP draw (which would not otherwise honor the preference).
    var hasDraw = !reduced && gsap && typeof window.DrawSVGPlugin !== "undefined";
    if (hasDraw) gsap.registerPlugin(window.DrawSVGPlugin);

    var rows = Array.prototype.slice.call(board.querySelectorAll(".c-row"));
    var ALL = rows.map(function (r) { return r.getAttribute("data-iso3"); });

    function byName(a, b) {
      return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
    }
    // The movers, sorted by when each state last moved (beat 7).
    var MOVERS = rows.filter(function (r) { return r.hasAttribute("data-move-year"); })
      .sort(function (a, b) {
        var ya = a.getAttribute("data-move-year"), yb = b.getAttribute("data-move-year");
        if (ya !== yb) return ya < yb ? -1 : 1;
        return byName(a, b);
      })
      .map(function (r) { return r.getAttribute("data-iso3"); });
    // The coded states, grouped into camps by category (beat 8). The
    // order is the rubric's own category order: a listing, never a rank.
    var CODE_ORDER = ["LBI-BAN", "LBI-OPEN", "REG-SOFT", "CCW-ONLY", "OPPOSE", "AMBIG", "NONE"];
    var CODED = rows.filter(function (r) { return r.hasAttribute("data-code"); })
      .sort(function (a, b) {
        var ca = CODE_ORDER.indexOf(a.getAttribute("data-code"));
        var cb = CODE_ORDER.indexOf(b.getAttribute("data-code"));
        if (ca !== cb) return ca - cb;
        return byName(a, b);
      })
      .map(function (r) { return r.getAttribute("data-iso3"); });

    var SCALES = { xl: 88, m: 26, s: 13, xs: 3.4 };
    // The full wall must fit the stage: at poster scale the row height
    // shrinks to fill at most 58% of the viewport.
    function rowHeight(st) {
      var h = SCALES[st.scale];
      if (st.scale === "xs" && st.order.length) {
        h = Math.max(2, Math.min(h, (window.innerHeight * 0.58) / st.order.length));
      }
      return h;
    }

    // One entry per storyboard beat: what is on the canvas, at what
    // scale, which marks and layers have been taught so far. Color
    // arrives as an event at beat 5 and never leaves; the movers keep
    // the two known rows saturated as anchors (muting is focus, not
    // valence); beat 10 unlocks the board (c-live: telemetry on, the
    // release affordance appears).
    var STATES = [null,
      { order: [], scale: "xl", set: "b1", deadline: "faint", marks: 0 },
      { order: ["USA"], scale: "xl", set: "b2", marks: 1 },
      { order: ["USA"], scale: "xl", set: "b3", marks: 3, draw: "no-ring" },
      { order: ["USA"], scale: "xl", set: "b4", marks: 3 },
      { order: ["USA"], scale: "xl", set: "b5", marks: 3, bands: true },
      { order: ["USA", "IND"], scale: "xl", set: "b6", marks: 3, bands: true },
      { order: MOVERS, scale: "m", set: "b7", marks: 3, bands: true, anchors: ["USA", "IND"] },
      { order: CODED, scale: "m", set: "b8", marks: 3, bands: true },
      { order: ALL, scale: "xs", set: "b9", marks: 3, bands: true },
      { order: ALL, scale: "xs", set: "b10", marks: 3, bands: true, deadline: "draw", live: true }
    ];

    function showSet(cls, set) {
      Array.prototype.forEach.call(canvas.querySelectorAll("." + cls), function (el) {
        el.hidden = el.getAttribute("data-set") !== set;
      });
    }

    var lastBeat = 0;
    function apply(n) {
      var st = STATES[n];
      if (!st) return;
      board.setAttribute("data-beat", String(n));
      board.setAttribute("data-scale", st.scale);
      board.classList.toggle("c-marks-0", st.marks === 0);
      board.classList.toggle("c-marks-1", st.marks === 1);
      board.classList.toggle("c-bands-on", !!st.bands);
      canvas.classList.toggle("c-live", !!st.live);
      var release = canvas.querySelector(".c-release");
      if (release) release.hidden = !st.live;
      var h = rowHeight(st);
      var pos = {};
      st.order.forEach(function (iso, i) { pos[iso] = i; });
      rows.forEach(function (row) {
        var iso = row.getAttribute("data-iso3");
        row.classList.toggle("c-dim",
          !!st.anchors && iso in pos && st.anchors.indexOf(iso) === -1);
        if (iso in pos) {
          row.style.transform = "translateY(" + (pos[iso] * h).toFixed(2) + "px)";
          row.style.height = Math.max(h - (h > 10 ? 2 : 0.6), 2).toFixed(2) + "px";
          row.classList.remove("c-off");
        } else {
          row.classList.add("c-off");
        }
      });
      board.style.height = (Math.max(st.order.length, 4) * h).toFixed(1) + "px";
      showSet("c-teach", st.set);
      showSet("c-statset", st.set);
      // The one within-beat GSAP draw so far: the crossed ring draws
      // itself as the word arrives (beat 3, forward entries only). Same
      // tempo as every other reveal; motion teaches the glyph, never a
      // verdict.
      if (st.draw === "no-ring" && hasDraw && lastBeat < n) {
        var ring = board.querySelectorAll('.c-row[data-iso3="USA"] .c-mark-N svg *');
        if (ring.length) {
          gsap.fromTo(ring, { drawSVG: "0%" },
            { drawSVG: "100%", duration: 0.7, ease: "none", stagger: 0.15 });
        }
      }
      // The deadline draws by CSS clip reveal keyed off data-state, so
      // the stroke keeps its dashed identity.
      var dl = canvas.querySelector(".c-deadline");
      if (dl) dl.setAttribute("data-state", st.deadline || "off");
      lastBeat = n;
    }

    initTelemetry();
    rows.forEach(function (row) { row.classList.add("c-off"); });
    return apply;
  }

  // ---- Row telemetry (Shift5 mechanic, P4c): once the board is live,
  // tapping or clicking a row surfaces its record: every vote with its
  // resolution, date, and UN record link; the coded position with its
  // since-date, confidence, and any provisional note; the state page.
  // Built with textContent, never markup injection. The keyboard path
  // to the same record is the release link into the classic board,
  // where every mark is a real button.
  function initTelemetry() {
    var pop = null;
    var hideTimer = null;
    function close() { if (pop) { pop.remove(); pop = null; } }
    function scheduleClose() {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(close, 300);
    }
    function cancelClose() {
      if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    }
    function el(tag, cls, text) {
      var node = document.createElement(tag);
      if (cls) node.className = cls;
      if (text) node.textContent = text;
      return node;
    }
    var RES = [];
    try { RES = JSON.parse(board.getAttribute("data-resolutions") || "[]"); }
    catch (e) { RES = []; }
    var WORDS = { Y: "voted Yes", N: "voted No", A: "abstained", X: "non-voting" };
    function showFor(row) {
      close();
      pop = el("div", "popover");
      pop.setAttribute("data-for", row.getAttribute("data-iso3"));
      pop.appendChild(el("strong", null, row.getAttribute("data-name")));
      var votes = (row.getAttribute("data-votes") || "").split(",");
      RES.forEach(function (r, i) {
        var line = el("span", "citation",
          (WORDS[votes[i]] || votes[i]) + " on " + r.key + " \u00b7 " + r.date + " \u00b7 ");
        var a = el("a", null, "UN record");
        a.href = r.url;
        line.appendChild(a);
        pop.appendChild(line);
      });
      Array.prototype.forEach.call(row.querySelectorAll(".c-band"), function (b) {
        var code = b.getAttribute("data-code");
        // NONE is a coverage statement: its date is the review date, not a start.
        var plain = b.getAttribute("data-plain") || code;
        var confPlain = b.getAttribute("data-conf-plain") || "";
        var when = code === "NONE"
          ? "No stated position (NONE), reviewed " + b.getAttribute("data-since") + ", " + confPlain
          : plain + " (" + code + "), since " + b.getAttribute("data-since") + ", " + confPlain + " (" + b.getAttribute("data-conf") + ")";
        pop.appendChild(el("span", "citation", when));
      });
      var note = row.querySelector(".c-note");
      if (note) pop.appendChild(el("span", "citation", note.textContent));
      var more = el("a", null, "Full record: state page");
      more.href = "state/" + row.getAttribute("data-iso3") + ".html";
      pop.appendChild(more);
      pop.addEventListener("mouseenter", cancelClose);
      pop.addEventListener("mouseleave", scheduleClose);
      document.body.appendChild(pop);
      var r = row.getBoundingClientRect();
      pop.style.top = (window.scrollY + r.bottom + 6) + "px";
      pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 330)) + "px";
    }
    function liveRow(ev) {
      if (!canvas.classList.contains("c-live")) return null;
      var row = ev.target.closest ? ev.target.closest(".c-row") : null;
      if (!row || row.classList.contains("c-off")) return null;
      return row;
    }
    board.addEventListener("click", function (ev) {
      var row = liveRow(ev);
      if (!row) return;
      showFor(row);
      ev.stopPropagation();
    });
    // Hover surfaces the same readout for fine pointers (the storyboard's
    // hover telemetry); a short grace period lets the pointer travel into
    // the popover to reach its links.
    board.addEventListener("mouseover", function (ev) {
      if (!window.matchMedia("(hover: hover)").matches) return;
      var row = liveRow(ev);
      if (!row) return;
      cancelClose();
      if (pop && pop.getAttribute("data-for") === row.getAttribute("data-iso3")) return;
      showFor(row);
    });
    board.addEventListener("mouseleave", function () {
      if (pop) scheduleClose();
    });
    document.addEventListener("click", function (ev) {
      if (pop && !pop.contains(ev.target)) close();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") close();
    });
  }

  // ---- Mobile contract: tap-through stepper driving the same canvas
  // states, never scroll-driven. Reduced-motion users get the same
  // stepper with instant state changes (the transition media query
  // zeroes every canvas transition).
  if (mobile) {
    var beats = Array.prototype.slice.call(tour.querySelectorAll(".beat"));
    if (beats.length < 2) return;
    var index = 0;
    var nav = document.createElement("div");
    nav.className = "tour-stepper";
    var prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "Back";
    var counter = document.createElement("span");
    counter.setAttribute("aria-live", "polite");
    var next = document.createElement("button");
    next.type = "button";
    next.textContent = "Next";
    nav.appendChild(prev); nav.appendChild(counter); nav.appendChild(next);
    tour.classList.add("tour-stepped");
    tour.appendChild(nav);
    if (canvas && setBeat) canvas.hidden = false;
    function show(i) {
      index = Math.max(0, Math.min(beats.length - 1, i));
      beats.forEach(function (b, j) { b.hidden = j !== index; });
      counter.textContent = "Beat " + (index + 1) + " of " + beats.length;
      prev.disabled = index === 0;
      next.textContent = index === beats.length - 1 ? "To the board" : "Next";
      if (setBeat) {
        setBeat(index + 1);
        // keep the canvas card in view as the reader taps through
        if (index > 0 && !canvas.hidden) canvas.scrollIntoView({ block: "start" });
      }
    }
    prev.addEventListener("click", function () { show(index - 1); });
    next.addEventListener("click", function () {
      if (index === beats.length - 1) {
        document.getElementById("board-top").scrollIntoView();
        return;
      }
      show(index + 1);
    });
    show(0);
    return;
  }

  // ---- Reduced motion (desktop): instant states; the stacked scaffold
  // with the classic board below IS the designed static path ----
  if (reduced) return;
  if (typeof window.scrollama === "undefined" || typeof window.gsap === "undefined") return;
  if (!canvas || !board || !setBeat) return;

  tour.classList.add("tour-enhanced");
  canvas.hidden = false;

  var scroller = window.scrollama();
  scroller.setup({ step: ".scrolly-steps .beat", offset: 0.55 })
    .onStepEnter(function (r) { setBeat(r.index + 1); });
  window.addEventListener("resize", function () { scroller.resize(); });

  setBeat(1);

  // Positions depend on the serif loading; recalc offsets once it
  // settles.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () { scroller.resize(); });
  }
})();
