import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/** Build the Android shell from the original billing template, without Flask at runtime. */
export function originalBillingTemplate() {
  const path = resolve(
    import.meta.dirname,
    "../src/vglpos/web/templates/pos.html",
  );
  const dashboardPath = resolve(
    import.meta.dirname,
    "../src/vglpos/web/templates/dashboard.html",
  );
  return {
    name: "original-billing-template",
    buildStart() {
      this.addWatchFile(path);
      this.addWatchFile(dashboardPath);
    },
    configureServer(server) {
      server.watcher.add(path);
      server.watcher.add(dashboardPath);
      server.watcher.on("change", (changed) => {
        if (
          [path, dashboardPath].some(
            (p) => changed.replaceAll("\\", "/") === p.replaceAll("\\", "/"),
          )
        )
          server.ws.send({ type: "full-reload" });
      });
    },
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        const source = readFileSync(path, "utf8");
        const content = source
          .split("{% block content %}")[1]
          ?.split("{% endblock %}")[0];
        if (!content || /\{%|\{\{/.test(content))
          throw new Error("Billing content must be standalone HTML");
        const boundary = content.search(/<dialog\s+id="payment-dialog"/);
        if (boundary < 0) throw new Error("Original payment dialog missing");
        const dashboard = readFileSync(dashboardPath, "utf8")
          .split("{% block content %}")[1]
          ?.split("{% endblock %}")[0];
        if (!dashboard || /\{%|\{\{/.test(dashboard))
          throw new Error("Dashboard content must be standalone HTML");
        return html
          .replace("__RESTAURANT_NAME__", JSON.parse(readFileSync(resolve(import.meta.dirname, "store-defaults.json"), "utf8")).name.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]))
          .replace("<!-- ORIGINAL_DASHBOARD -->", dashboard)
          .replace("<!-- ORIGINAL_BILLING -->", content.slice(0, boundary))
          .replace(
            "<!-- ORIGINAL_BILLING_DIALOGS -->",
            content.slice(boundary),
          );
      },
    },
  };
}
