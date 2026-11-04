package in.vgl.restaurant;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;

/** Configuration of the exact optional print service documented in the local field report. */
final class PrinterServiceSetup {
    static final String PACKAGE = "com.loopedlabs.usbprintservice";
    private PrinterServiceSetup() {}

    static boolean containsService(String services) {
        if (services == null) return false;
        for (String component : services.split(":")) {
            if (component.startsWith(PACKAGE + "/") && component.length() > PACKAGE.length() + 1) return true;
        }
        return false;
    }

    static boolean installed(Context context) {
        try { context.getPackageManager().getPackageInfo(PACKAGE, 0); return true; }
        catch (PackageManager.NameNotFoundException error) { return false; }
    }

    /** A restricted settings read is unknown; never report an installed service as absent. */
    static Boolean enabled(Context context) {
        try { return containsService(Settings.Secure.getString(context.getContentResolver(), "enabled_print_services")); }
        catch (SecurityException error) { return null; }
    }

    static boolean requireReady(Activity activity) {
        if (installed(activity) && !Boolean.FALSE.equals(enabled(activity))) return true;
        show(activity);
        return false;
    }

    static void show(Activity activity) {
        boolean present = installed(activity);
        String status = !present ? "ESC POS USB Print Service is not installed."
            : Boolean.TRUE.equals(enabled(activity)) ? "ESC POS USB Print Service is enabled."
            : "Enable ESC POS USB Print Service in Android print settings.";
        String version;
        try { version = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionName; }
        catch (PackageManager.NameNotFoundException error) { version = "unknown"; }
        new AlertDialog.Builder(activity).setTitle("RP 3230 printer setup · " + version)
            .setMessage("For direct printing, return to the saved bill and tap Print to USB. Allow USB access when asked.\n\n"
                + status + "\n\nFor the Android print-service route: open ESC POS USB Print Service by Looped Labs, select the connected USB printer, set 3 inch / 80 mm and 203 DPI, and allow USB access. Keep auto-cut and cash drawer off.\n\nAndroid's default printer search does not discover this USB printer. Save as PDF saves a file; it does not send paper to the RP 3230.")
            .setPositiveButton(present ? "Open USB Print Service" : "Get USB Print Service", (dialog, which) -> {
                Intent intent = present ? activity.getPackageManager().getLaunchIntentForPackage(PACKAGE)
                    : new Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=" + PACKAGE));
                launch(activity, intent == null ? new Intent(Settings.ACTION_PRINT_SETTINGS) : intent);
            })
            .setNeutralButton("Android print settings", (dialog, which) -> launch(activity, new Intent(Settings.ACTION_PRINT_SETTINGS)))
            .setNegativeButton("Close", null).show();
    }

    private static void launch(Activity activity, Intent intent) {
        try { activity.startActivity(intent); }
        catch (ActivityNotFoundException error) {
            new AlertDialog.Builder(activity).setTitle("Open printer settings manually")
                .setMessage("Open Android Settings → Printing and enable ESC POS USB Print Service. The bill remains saved.")
                .setPositiveButton("Close", null).show();
        }
    }
}
