// Saves a list row's stage select (partials/deal_stage_selects.html) in the background, so
// the list stays where it is while stages are changed one after another. Anything that is
// not a clean save (an error, an expired login, a network failure) falls back to the
// normal form submit, which shows the server's answer as before.
(function () {
  function recolor(select) {
    select.className = select.className.replace(/badge-stage-\S+/, "badge-stage-" + select.value);
  }

  async function save(form) {
    const select = form.querySelector("select[name='stage']");
    const previous = select ? select.dataset.saved : undefined;
    if (!select) return form.submit();
    // Read the form before disabling the select: a disabled field is left out of FormData.
    const body = new URLSearchParams(new FormData(form));
    select.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body,
        credentials: "same-origin",
        redirect: "follow",
      });
      if (!response.ok || new URL(response.url).pathname.startsWith("/login")) return form.submit();
      select.dataset.saved = select.value;
      recolor(select);
      select.disabled = false;
    } catch (error) {
      if (previous !== undefined) select.value = previous;
      select.disabled = false;
      form.submit();
    }
  }

  document.addEventListener("focusin", (event) => {
    const select = event.target;
    if (select instanceof HTMLSelectElement && select.closest(".stage-form") && !select.dataset.saved) {
      select.dataset.saved = select.value;
    }
  });

  window.keepPlaceSubmit = save;
})();
