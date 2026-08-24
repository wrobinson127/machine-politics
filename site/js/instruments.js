// Instruments page enhancements. The server-rendered lists and tables ARE
// the content; the quadrant scrub and the wave map only add sequence.
// Endorsement renders in the instrument's own hue; not-yet-endorsed renders
// as paper, never as an opposing color. No motion here encodes valence, and
// every update is an instant state change (reduced-motion safe by design).
(function () {
  "use strict";

  // ---- Quadrant time scrub ----
  var qNode = document.getElementById("quadrant-data");
  var qSvg = document.getElementById("quadrant-svg");
  var qRange = document.getElementById("quadrant-time");
  var qOut = document.getElementById("quadrant-step");
  if (qNode && qSvg && qRange && qOut) {
    var q = JSON.parse(qNode.textContent);
    var dots = {};
    qSvg.querySelectorAll("[data-iso3]").forEach(function (d) {
      dots[d.getAttribute("data-iso3")] = d;
    });
    var applyStep = function (i) {
      var step = q.steps[i];
      qOut.textContent = step.date + " \u00b7 " + step.label;
      q.states.forEach(function (st) {
        var dot = dots[st.iso3];
        if (!dot) return;
        var yes = st.yes.filter(function (d) { return d <= step.date; }).length;
        var endorsed = !!(st.endorsed && st.endorsed <= step.date);
        dot.setAttribute("cx", (q.layout.cols[yes] + st.jx).toFixed(1));
        dot.setAttribute(
          "cy",
          ((endorsed ? q.layout.rowEndorsed : q.layout.rowNot) + st.jy).toFixed(1)
        );
        var title = dot.querySelector("title");
        if (title) {
          title.textContent = st.name + " (" + st.iso3 + "): " + yes +
            " Yes vote" + (yes === 1 ? "" : "s") + "; " +
            (endorsed ? "endorsed" : "not listed") + ", as of " + step.date;
        }
      });
    };
    qRange.disabled = false;
    qRange.addEventListener("input", function () {
      applyStep(Number(qRange.value));
    });
    applyStep(Number(qRange.value));

    // ---- State search (primary nav, DESIGN v2 mobile contract) ----
    // A match rings the state's dot (ink stroke, radius bump, never a color
    // change), scrolls the chart to it when overflowed, and filters the
    // fallback table to that state. Clearing restores everything.
    var qSearch = document.getElementById("quadrant-search");
    var qTable = document.getElementById("quadrant-table");
    var qScroll = qSvg.parentElement;
    if (qSearch) {
      var lookup = {};
      q.states.forEach(function (st) {
        lookup[st.name.toLowerCase()] = st.iso3;
        lookup[st.iso3.toLowerCase()] = st.iso3;
        lookup[(st.name + " (" + st.iso3 + ")").toLowerCase()] = st.iso3;
      });
      var applySearch = function () {
        var hit = lookup[qSearch.value.trim().toLowerCase()] || null;
        Object.keys(dots).forEach(function (iso3) {
          var dot = dots[iso3];
          if (iso3 === hit) {
            dot.classList.add("q-hit");
            dot.setAttribute("r", "7");
          } else {
            dot.classList.remove("q-hit");
            dot.setAttribute("r", "5");
          }
        });
        if (hit && dots[hit]) {
          // Redraw the ringed dot above its neighbors.
          dots[hit].parentNode.appendChild(dots[hit]);
          if (qScroll && qScroll.scrollWidth > qScroll.clientWidth) {
            var vw = qSvg.viewBox.baseVal.width || 1;
            var x = (Number(dots[hit].getAttribute("cx")) / vw) * qScroll.scrollWidth;
            qScroll.scrollLeft = Math.max(0, x - qScroll.clientWidth / 2);
          }
        }
        if (qTable) {
          qTable.querySelectorAll("tr").forEach(function (row) {
            var link = row.querySelector('a[href^="state/"]');
            if (!link) return; // header row always stands
            row.hidden = !!hit &&
              link.getAttribute("href") !== "state/" + hit + ".html";
          });
        }
      };
      qSearch.disabled = false;
      qSearch.addEventListener("input", applySearch);
    }
  }

  // ---- Endorsement wave map ----
  var mNode = document.getElementById("map-data");
  var box = document.getElementById("wave-map");
  var fallback = document.getElementById("map-fallback");
  var mRange = document.getElementById("map-time");
  var mOut = document.getElementById("map-month");
  if (!mNode || !box || !mRange || !mOut) return;
  var m = JSON.parse(mNode.textContent);
  function hasWebgl() {
    try {
      var c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch (err) {
      return false;
    }
  }
  // Without MapLibre or WebGL the fallback text stands; the lists above
  // are the data either way. file:// cannot serve the local GeoJSON to
  // fetch(), so the fallback stands there too, without console noise.
  if (typeof window.maplibregl === "undefined" || !hasWebgl()) return;
  if (window.location.protocol === "file:") return;

  function currentInstrument() {
    var checked = document.querySelector('input[name="map-instrument"]:checked');
    if (!checked) return m.instruments[0];
    return m.instruments.filter(function (i) { return i.id === checked.value; })[0];
  }
  function paint(map) {
    var inst = currentInstrument();
    var month = m.months[Number(mRange.value)];
    mOut.textContent = month;
    var endorsed = inst.states
      .filter(function (s) { return s.date.slice(0, 7) <= month; })
      .map(function (s) { return s.iso3; });
    map.setPaintProperty("countries-fill", "fill-color", [
      "case",
      ["in", ["get", "iso3"], ["literal", endorsed]],
      inst.hue,
      m.paper
    ]);
  }
  fetch("assets/countries.geojson")
    .then(function (r) {
      if (!r.ok) throw new Error("geojson " + r.status);
      return r.json();
    })
    .then(function (geo) {
      box.classList.add("wave-map-live");
      var map = new maplibregl.Map({
        container: box,
        style: m.style,
        center: [10, 22],
        zoom: 0.9,
        minZoom: 0.4,
        maxZoom: 6,
        cooperativeGestures: true,
        attributionControl: { compact: false }
      });
      map.on("load", function () {
        map.addSource("countries", { type: "geojson", data: geo });
        map.addLayer({
          id: "countries-fill",
          type: "fill",
          source: "countries",
          paint: { "fill-color": m.paper, "fill-opacity": 0.75 }
        });
        map.addLayer({
          id: "countries-line",
          type: "line",
          source: "countries",
          paint: { "line-color": m.ink, "line-opacity": 0.25, "line-width": 0.5 }
        });
        // Only a fully loaded map replaces the fallback text.
        if (fallback) fallback.hidden = true;
        mRange.disabled = false;
        paint(map);
        mRange.addEventListener("input", function () { paint(map); });
        document.querySelectorAll('input[name="map-instrument"]').forEach(function (r) {
          r.addEventListener("change", function () { paint(map); });
        });
        map.resize();
      });
    })
    .catch(function () {
      box.classList.remove("wave-map-live");
      /* fallback stands */
    });
})();
