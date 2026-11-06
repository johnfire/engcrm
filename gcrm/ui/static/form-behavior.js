// Native forms retain validation, translated confirmation and repeat-submit protection.
(() => {
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
      return;
    }
    if (form.hasAttribute("data-disable-submit")) {
      const button = event.submitter || form.querySelector("button");
      if (button) button.disabled = true;
    }
  });
  document.addEventListener("change", (event) => {
    const select = event.target.closest("select[data-submit-on-change]");
    if (!select?.form) return;
    if (select.dataset.keepPlace === "true" && window.keepPlaceSubmit) {
      window.keepPlaceSubmit(select.form);
    } else {
      select.form.requestSubmit();
    }
  });
})();
