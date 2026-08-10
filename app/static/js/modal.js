document.addEventListener("DOMContentLoaded", () => {
  const backdrop = document.querySelector("[data-modal]");
  if (!backdrop) return;

  const openBtn = document.querySelector("[data-open-modal]");
  const closeEls = document.querySelectorAll("[data-close-modal]");

  openBtn?.addEventListener("click", () => {
    backdrop.hidden = false;
  });

  closeEls.forEach((el) =>
    el.addEventListener("click", () => {
      backdrop.hidden = true;
    })
  );

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.hidden = true;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") backdrop.hidden = true;
  });
});
