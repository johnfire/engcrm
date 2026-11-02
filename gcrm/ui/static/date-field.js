// Calendar button for the European date fields (partials/date_field.html): opens
// the browser's own calendar, then writes the picked day back as 28.10.2026.
(function () {
  function iso(text) {
    const m = (text || "").trim().match(/^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2}|\d{4})?)?$/);
    if (!m) return /^\d{4}-\d{2}-\d{2}$/.test(text || "") ? text : "";
    const year = m[3] ? (m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3])) : new Date().getFullYear();
    return `${year}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
  }
  function dmy(isoDay) {
    const [y, m, d] = isoDay.split("-");
    return `${d}.${m}.${y}`;
  }
  function wire(field) {
    const text = field.querySelector('input[type="text"]');
    const calendar = field.querySelector(".date-field__calendar");
    const button = field.querySelector(".date-field__pick");
    if (!calendar || !button || typeof calendar.showPicker !== "function") return;
    button.hidden = false;
    button.addEventListener("click", () => {
      calendar.value = iso(text.value);
      try { calendar.showPicker(); } catch (e) { text.focus(); }
    });
    calendar.addEventListener("change", () => {
      if (calendar.value) text.value = dmy(calendar.value);
      text.dispatchEvent(new Event("input", { bubbles: true }));
      text.focus();
    });
  }
  function wireAll(root) {
    root.querySelectorAll(".date-field").forEach((field) => {
      if (field.dataset.wired) return;
      field.dataset.wired = "1";
      wire(field);
    });
  }
  document.addEventListener("DOMContentLoaded", () => wireAll(document));
  document.addEventListener("htmx:afterSwap", (event) => wireAll(event.target));
})();
