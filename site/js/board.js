// Progressive enhancement only: the board is complete without JavaScript.
(function () {
  "use strict";
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
  function show(trigger, data) {
    close();
    var pop = document.createElement("div");
    pop.className = "popover";
    pop.setAttribute("role", "dialog");
    if (data.kind === "vote") {
      pop.innerHTML =
        "<strong>" + data.vote + "</strong> on " + data.resolution +
        '<span class="citation">' + data.date +
        ' · <a href="' + data.url + '">UN record</a></span>';
    } else {
      var ev = (data.evidence || []).map(function (e) {
        return '<span class="citation">' +
          (e.quote ? "“" + e.quote + "” · " : "") + e.date +
          (e.url ? ' · <a href="' + e.url + '">source</a>' : "") +
          (e.confidence ? " · " + e.confidence : "") + "</span>";
      }).join("");
      pop.innerHTML = "<strong>" + data.from + " → " + data.to +
        "</strong>" + '<span class="citation">' + data.date + "</span>" + ev;
    }
    document.body.appendChild(pop);
    var r = trigger.getBoundingClientRect();
    if (window.matchMedia("(min-width: 641px)").matches) {
      pop.style.left = Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - pop.offsetWidth - 16) + "px";
      pop.style.top = (window.scrollY + r.bottom + 8) + "px";
    }
    open = pop;
  }
  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-vote],[data-shift]") : null;
    if (t && t.hasAttribute("data-vote")) { show(t, JSON.parse(t.getAttribute("data-vote"))); ev.stopPropagation(); return; }
    if (t && t.hasAttribute("data-shift") && t.classList.contains("shift-node")) { show(t, JSON.parse(t.getAttribute("data-shift"))); ev.stopPropagation(); return; }
    close();
  });
  // Triggers are real <button> elements, so Enter and Space already fire
  // click; only Escape needs handling.
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") close();
  });
})();
