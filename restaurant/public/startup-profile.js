// Opt in via ?startupProfile=1 (or localStorage restaurant.startupProfile=1).
// The timestamps are navigation-relative diagnostics, never device acceptance.
(() => {
  let enabled = new URLSearchParams(location.search).get("startupProfile") === "1";
  try { enabled = enabled || localStorage.getItem("restaurant.startupProfile") === "1"; }
  catch { /* Diagnostics must not prevent startup when storage is unavailable. */ }
  window.restaurantStartupMark = name => {
    if (enabled) performance.mark(`restaurant:${name}`);
  };
  window.restaurantStartupMark("entry");
})();
