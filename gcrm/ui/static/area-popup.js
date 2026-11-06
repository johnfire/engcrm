// Treat saved labels as text; no label becomes HTML or an executable attribute.
window.buildAreaPopup = (area, label, buttonLabel, onView) => {
  const popup = document.createElement("div");
  popup.className = "area-popup";
  const title = document.createElement("strong");
  title.textContent = label;
  const radius = document.createElement("p");
  radius.textContent = `${area.radius_m}m`;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = buttonLabel;
  button.addEventListener("click", () => onView(area.id, label));
  popup.append(title, radius, button);
  return popup;
};
