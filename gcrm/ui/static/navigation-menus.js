document.querySelectorAll(".nav-dropdown").forEach((dropdown) => {
  document.addEventListener("click", (event) => {
    if (!dropdown.contains(event.target)) dropdown.open = false;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && dropdown.open) {
      dropdown.open = false;
      dropdown.querySelector("summary").focus();
    }
  });

  document.addEventListener("focusin", (event) => {
    if (!dropdown.contains(event.target)) dropdown.open = false;
  });
});
