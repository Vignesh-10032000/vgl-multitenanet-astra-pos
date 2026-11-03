// Runs synchronously after the login shell is parsed, before its first paint.
(() => {
  const screen = document.querySelector("#access-screen");
  let brand = { name: screen.dataset.defaultName, logo: "./branding/v2/arafa-logo.jpg" };
  try {
    const cached = JSON.parse(localStorage.getItem("restaurant.branding"));
    if (cached && typeof cached.name === "string" &&
        (cached.logo === null || /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(cached.logo))) brand = cached;
    document.documentElement.dataset.theme = localStorage.getItem("vglpos.theme") === "dark" ? "dark" : "light";
  } catch { /* The database remains authoritative; cache access is optional. */ }
  document.title = brand.name;
  document.querySelector("#access-brand-name").textContent = brand.name;
  if (brand.logo) {
    const image = document.createElement("img");
    image.className = "access-custom-logo";
    image.alt = "";
    image.src = brand.logo;
    document.querySelector("#access-brand-logo").append(image);
  }
})();
