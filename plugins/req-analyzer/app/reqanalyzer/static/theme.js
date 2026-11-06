"use strict";
// Runs in <head> before the stylesheet paints, so a chosen theme or the hidden-descriptions mode never flashes (UEUIS §8.9, §8.18).
(function () {
  let t = "system", d = "hide";
  try { t = localStorage.getItem("reqan-theme") || "system"; d = localStorage.getItem("reqan-desc") || "hide"; } catch { /* storage unavailable */ }
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  if (d === "hide") document.documentElement.classList.add("hide-desc");
})();
