import "../src/vglpos/web/static/src/css/pos.css";
import "./style.css";
import "./workspace-style.css";
import { Capacitor } from "@capacitor/core";
import { initializePreferences, workspaceText, translateWorkspace } from "./preferences.js";
import { registerIcons } from "../src/vglpos/web/static/src/js/ui.js";
import { workspaceIcons } from "./workspace-icons.js";
import { posIcons } from "../src/vglpos/web/static/src/js/pos-icons.js";

const form = document.querySelector("#access-form");
let ready = false, queued = false;
// A keyboard or programmatic submit during DB initialization waits for readiness.
form.addEventListener("submit", event => {
  if (ready) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  queued = true;
}, true);
document.querySelector("#access-retry").addEventListener("click", () => location.reload());
document.addEventListener("restaurant:access-ready", () => {
  ready = true;
  if (queued) { queued = false; form.requestSubmit(); }
});

async function boot() {
  registerIcons({ ...posIcons, ...workspaceIcons });
  await initializePreferences(async () => {
    document.dispatchEvent(new Event("restaurant:language-changed"));
  });
  translateWorkspace();
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  window.restaurantStartupMark?.("login-first-paint");
  if (Capacitor.isNativePlatform()) {
    import("@capacitor/splash-screen").then(({ SplashScreen }) => SplashScreen.hide()).catch(error => console.warn("Splash hide failed", error));
  }
  const { start } = await import("./app.js");
  await start();
}
boot().catch(error => {
  console.error("Restaurant startup failed", error);
  document.querySelector("#access-title").textContent = workspaceText("openFailed");
  document.querySelector("#access-description").textContent = workspaceText("openFailedHelp");
  document.querySelector("#access-submit").disabled = true;
  document.querySelector("#access-retry").hidden = false;
  document.querySelector("#access-startup-status").textContent = "";
  form.setAttribute("aria-busy", "false");
  if (Capacitor.isNativePlatform())
    import("@capacitor/splash-screen").then(({ SplashScreen }) => SplashScreen.hide()).catch(hideError => console.warn("Splash hide failed", hideError));
});
