package in.vgl.restaurant;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.print.PageRange;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintJob;
import android.print.PrintManager;
import android.util.Base64;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** System document picker and the already-proven Android USB print-service path. */
@CapacitorPlugin(name = "RestaurantDocuments")
public class RestaurantDocumentsPlugin extends Plugin {
    private final ExecutorService files = Executors.newSingleThreadExecutor();
    private volatile boolean pickerOpen = false;
    private boolean printing = false;

    @PluginMethod
    public void saveDocument(PluginCall call) {
        if (pickerOpen) { call.reject("Finish the current file save first", "BUSY"); return; }
        String name = call.getString("name");
        String mime = call.getString("mime");
        String data = call.getString("data");
        if (name == null || name.length() > 256 || mime == null || mime.length() > 128 || data == null || data.length() > 140000000) {
            call.reject("Invalid document or file too large", "INVALID_DOCUMENT"); return;
        }
        // Capacitor persists call options twice when the picker backgrounds this app.
        // Remove the large payload before any activity starts; save only a cache token.
        call.getData().remove("data");
        call.getData().remove("stagedDocument");
        pickerOpen = true;
        try {
            files.execute(() -> {
                try {
                    String token = StagedDocuments.stage(getContext().getCacheDir(), Base64.decode(data, Base64.DEFAULT));
                    call.getData().put("stagedDocument", token);
                    getActivity().runOnUiThread(() -> {
                        try {
                            if (getActivity().isFinishing() || getActivity().isDestroyed()) throw new IllegalStateException("Activity closed");
                            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                            intent.addCategory(Intent.CATEGORY_OPENABLE);
                            intent.setType(mime);
                            intent.putExtra(Intent.EXTRA_TITLE, name.replaceAll("[^a-zA-Z0-9._-]", "_"));
                            startActivityForResult(call, intent, "documentChosen");
                        } catch (RuntimeException error) {
                            pickerOpen = false;
                            StagedDocuments.discard(getContext().getCacheDir(), token);
                            call.reject("Could not open file picker", "PICKER_FAILED", error);
                        }
                    });
                } catch (IOException | RuntimeException error) {
                    pickerOpen = false;
                    StagedDocuments.discard(getContext().getCacheDir(), call.getString("stagedDocument"));
                    call.reject("Could not prepare document", "STAGING_FAILED", error);
                }
            });
        } catch (RuntimeException error) {
            pickerOpen = false;
            call.reject("App closed before export started", "WRITE_INTERRUPTED", error);
        }
    }

    @ActivityCallback
    private void documentChosen(PluginCall call, ActivityResult result) {
        pickerOpen = false;
        if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) {
            StagedDocuments.discard(getContext().getCacheDir(), call.getString("stagedDocument"));
            call.reject("File save cancelled", "CANCELLED"); return;
        }
        Uri uri = result.getData().getData();
        try {
            files.execute(() -> {
                try {
                    StagedDocuments.copyAndClose(getContext().getCacheDir(), call.getString("stagedDocument"),
                        getContext().getContentResolver().openOutputStream(uri, "wt"));
                    JSObject response = new JSObject(); response.put("state", "saved"); call.resolve(response);
                } catch (IOException | RuntimeException error) {
                    StagedDocuments.discard(getContext().getCacheDir(), call.getString("stagedDocument"));
                    call.reject("Could not save document: " + error.getMessage(), "WRITE_FAILED", error);
                }
            });
        } catch (RuntimeException error) {
            StagedDocuments.discard(getContext().getCacheDir(), call.getString("stagedDocument"));
            call.reject("App closed before the file save started", "WRITE_INTERRUPTED", error);
        }
    }

    @PluginMethod
    public void printReceipt(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (printing) { call.reject("Finish the current print dialog first", "PRINT_BUSY"); return; }
            if (!PrinterServiceSetup.requireReady(getActivity())) {
                call.reject("Configure and enable ESC POS USB Print Service in Printer setup, or use Print to USB. Save as PDF does not print to the RP 3230.", "PRINT_SERVICE_NOT_READY"); return;
            }
            PrintManager manager = (PrintManager)getContext().getSystemService(Context.PRINT_SERVICE);
            if (manager == null) { call.reject("Android printing is unavailable", "PRINT_UNAVAILABLE"); return; }
            printing = true;
            String name = call.getString("name", "Saved restaurant bill");
            PrintDocumentAdapter web = getBridge().getWebView().createPrintDocumentAdapter(name);
            final PrintJob[] job = new PrintJob[1];
            PrintDocumentAdapter adapter = new PrintDocumentAdapter() {
                @Override public void onStart() { web.onStart(); }
                @Override public void onLayout(PrintAttributes oldAttrs, PrintAttributes newAttrs, CancellationSignal cancellation, LayoutResultCallback callback, Bundle extras) { web.onLayout(oldAttrs, newAttrs, cancellation, callback, extras); }
                @Override public void onWrite(PageRange[] ranges, ParcelFileDescriptor destination, CancellationSignal cancellation, WriteResultCallback callback) { web.onWrite(ranges, destination, cancellation, callback); }
                @Override public void onFinish() {
                    web.onFinish(); printing = false;
                    JSObject response = new JSObject();
                    String state = job[0] != null && job[0].isCancelled() ? "cancelled" : job[0] != null && job[0].isFailed() ? "failed" : "submitted";
                    response.put("state", state);
                    response.put("detail", "Android print dialog finished. Paper output must be checked at printer.");
                    call.resolve(response);
                }
            };
            try {
                PrintAttributes attributes = new PrintAttributes.Builder()
                    .setMediaSize(new PrintAttributes.MediaSize("RECEIPT_80MM", "80 mm receipt", 3150, 11693))
                    .setResolution(new PrintAttributes.Resolution("THERMAL_203", "203 DPI", 203, 203))
                    .setMinMargins(PrintAttributes.Margins.NO_MARGINS)
                    .setColorMode(PrintAttributes.COLOR_MODE_MONOCHROME).build();
                job[0] = manager.print(name, adapter, attributes);
            } catch (RuntimeException error) { printing = false; call.reject("Could not open print service", "PRINT_FAILED", error); }
        });
    }

    @Override protected void handleOnDestroy() { files.shutdown(); super.handleOnDestroy(); }
}
