const mailMenu = document.querySelector(".nav-mail");

if (mailMenu) {
  document.addEventListener("click", (event) => {
    if (!mailMenu.contains(event.target)) mailMenu.open = false;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mailMenu.open) {
      mailMenu.open = false;
      mailMenu.querySelector("summary").focus();
    }
  });

  document.addEventListener("focusin", (event) => {
    if (!mailMenu.contains(event.target)) mailMenu.open = false;
  });
}
