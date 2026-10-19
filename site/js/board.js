// Progressive enhancement only: every page is complete without JavaScript.
(function () {
  "use strict";
  // The masthead is sticky; anchored content offsets by its real
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
})();
