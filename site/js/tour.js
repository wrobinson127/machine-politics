// Tour choreography scaffold. The stacked-prose beats and build-time
// figures ARE the page; everything in this file is enhancement and every
// guard below is a semantic rule from DESIGN v2, not an optimization.
(function () {
  "use strict";
  var tour = document.querySelector(".tour");
  if (!tour) return;
  // Reduced motion: instant states only; the stacked scaffold stands.
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // Mobile contract: tap-through stepper (built in P3b), never scroll-driven.
  if (window.matchMedia("(max-width: 720px), (pointer: coarse)").matches) return;
  if (typeof window.gsap === "undefined" || typeof window.ScrollTrigger === "undefined") return;
  window.gsap.registerPlugin(window.ScrollTrigger);
  // P3b wires the four beats here: pinned pane, band draw, release into
  // the board. Phase 0b ships the guards and the scaffold only.
})();
