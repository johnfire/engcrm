/* Sizes the organizations list's scroll box (the .table-scroll around .orgs-table) so its bottom edge sits at
   the bottom of the window. The box then shows both its scrollbars at all times:
   the sideways one is never pushed below the fold by a long table. Recomputed on
   resize and on page scroll, so the box grows as the filters above scroll away. */
(function () {
  var table = document.querySelector(".orgs-table");
  var box = table && table.closest(".table-scroll");
  if (!box) return;
  var MIN_HEIGHT = 320;
  var queued = false;
  function fit() {
    queued = false;
    var top = box.getBoundingClientRect().top;
    box.style.maxHeight = Math.max(MIN_HEIGHT, window.innerHeight - Math.max(top, 0) - 8) + "px";
  }
  function queue() {
    if (!queued) {
      queued = true;
      requestAnimationFrame(fit);
    }
  }
  window.addEventListener("resize", queue);
  window.addEventListener("scroll", queue, { passive: true });
  fit();
})();
