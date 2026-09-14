// Progressive enhancement only: the board is complete without JavaScript.
(function () {
  "use strict";
  // The masthead is sticky; the axis and the tour canvas offset by its real
  // height, which wraps on narrow screens, so measure rather than assume.
  function mastheadHeight() {
    var m = document.querySelector("header.masthead");
    // Below 720px the masthead is not sticky (see site.css), so nothing
    // needs to offset by it.
    var narrow = window.matchMedia("(max-width: 720px)").matches;
    if (m) document.documentElement.style.setProperty("--masthead-h", narrow ? "0px" : m.offsetHeight + "px");
  }
  mastheadHeight();
  window.addEventListener("resize", mastheadHeight);
  // Back to top, phones only (CSS hides it on wider screens): appears once
  // the reader is well into the page, scrolls smoothly unless motion is
  // reduced.
  var toTop = document.querySelector(".to-top");
  if (toTop) {
    var onScroll = function () { toTop.classList.toggle("is-on", window.scrollY > 600); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    toTop.addEventListener("click", function () {
      var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  }
  var rowsBox = document.getElementById("board-rows");
  if (rowsBox) {
    document.querySelectorAll(".board-controls button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var mode = btn.getAttribute("data-sort");
        var rows = Array.prototype.slice.call(rowsBox.children);
        rows.sort(function (a, b) {
          if (mode === "name") {
            return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
          }
          var sa = a.getAttribute("data-shift") || "";
          var sb = b.getAttribute("data-shift") || "";
          if (sa !== sb) return sb.localeCompare(sa);
          return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
        });
        rows.forEach(function (r) { rowsBox.appendChild(r); });
        document.querySelectorAll(".board-controls button").forEach(function (b) {
          b.setAttribute("aria-pressed", String(b === btn));
        });
      });
    });
  }

  var open = null;
  function close() {
    if (open) { open.remove(); open = null; }
  }
  // Popovers are built with textContent, never markup injection, because
  // quote and url values come from the content layer.
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }
  function link(url, label) {
    var a = el("a", null, label);
    a.href = url;
    return a;
  }
  function show(trigger, data) {
    close();
    var pop = el("div", "popover");
    pop.setAttribute("role", "dialog");
    if (data.kind === "vote") {
      pop.appendChild(el("strong", null, data.vote));
      pop.appendChild(document.createTextNode(" on " + data.resolution));
      var cite = el("span", "citation", data.date + " · ");
      cite.appendChild(link(data.url, "UN record"));
      pop.appendChild(cite);
    } else {
      pop.appendChild(el("strong", null, data.from + " → " + data.to));
      pop.appendChild(el("span", "citation", data.date));
      if (data.provisional) pop.appendChild(el("span", "citation", data.provisional));
      (data.evidence || []).forEach(function (e) {
        var row = el("span", "citation", (e.quote ? "“" + e.quote + "” · " : "") + e.date);
        if (e.url) {
          row.appendChild(document.createTextNode(" · "));
          row.appendChild(link(e.url, "source"));
        }
        if (e.confidence) row.appendChild(document.createTextNode(" · " + e.confidence));
        pop.appendChild(row);
      });
    }
    document.body.appendChild(pop);
    var r = trigger.getBoundingClientRect();
    if (window.matchMedia("(min-width: 641px)").matches) {
      pop.style.left = Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - pop.offsetWidth - 16) + "px";
      pop.style.top = (window.scrollY + r.bottom + 8) + "px";
    }
    open = pop;
  }
  // Coarse pointers get one sheet per row: adjacent marks are too close
  // together for separate 44px targets, so the track is the target.
  function showRow(track) {
    close();
    var pop = el("div", "popover");
    pop.setAttribute("role", "dialog");
    var row = track.closest ? track.closest(".board-row") : null;
    var label = row ? row.getAttribute("data-name") : "";
    if (label) pop.appendChild(el("strong", null, label));
    track.querySelectorAll("[data-shift]").forEach(function (node) {
      var d = JSON.parse(node.getAttribute("data-shift"));
      var line = el("span", "citation", "Shift " + d.from + " → " + d.to + ", " + d.date);
      (d.evidence || []).forEach(function (e) {
        if (e.url) {
          line.appendChild(document.createTextNode(" · "));
          line.appendChild(link(e.url, "source"));
        }
      });
      pop.appendChild(line);
    });
    track.querySelectorAll("[data-vote]").forEach(function (node) {
      var d = JSON.parse(node.getAttribute("data-vote"));
      var line = el("span", "citation", d.vote + " on " + d.resolution + ", " + d.date + " · ");
      line.appendChild(link(d.url, "UN record"));
      pop.appendChild(line);
    });
    document.body.appendChild(pop);
    if (window.matchMedia("(min-width: 641px)").matches) {
      var r = track.getBoundingClientRect();
      pop.style.left = Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - pop.offsetWidth - 16) + "px";
      pop.style.top = (window.scrollY + r.bottom + 8) + "px";
    }
    open = pop;
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-vote],[data-shift]") : null;
    if (t && t.hasAttribute("data-vote")) { show(t, JSON.parse(t.getAttribute("data-vote"))); ev.stopPropagation(); return; }
    if (t && t.hasAttribute("data-shift") && t.classList.contains("shift-node")) { show(t, JSON.parse(t.getAttribute("data-shift"))); ev.stopPropagation(); return; }
    if (window.matchMedia("(pointer: coarse)").matches) {
      var track = ev.target.closest ? ev.target.closest(".row-track") : null;
      if (track) { showRow(track); ev.stopPropagation(); return; }
    }
    close();
  });
  // Triggers are real <button> elements, so Enter and Space already fire
  // click; only Escape needs handling.
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") close();
  });
})();
