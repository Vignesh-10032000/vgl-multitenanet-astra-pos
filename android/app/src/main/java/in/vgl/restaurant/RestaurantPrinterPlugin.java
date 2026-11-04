package in.vgl.restaurant;

import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;
import android.hardware.usb.UsbManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Direct USB ESC/POS output. Each explicit attempt enumerates, opens and closes afresh. */
@CapacitorPlugin(name = "RestaurantPrinter")
public class RestaurantPrinterPlugin extends Plugin {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private PluginCall pending;
    private BroadcastReceiver permission;
    private AlertDialog chooser;
    private ReceiptRaster raster;
    private volatile UsbDeviceConnection connection;
    private String html;
    private final Runnable permissionTimeout = () -> reject("USB permission timed out. Reconnect the printer and try again.", "USB_PERMISSION_TIMEOUT");

    private static final class Port {
        final UsbDevice device;
        final UsbInterface face;
        final UsbEndpoint out;
        Port(UsbDevice d, UsbInterface f, UsbEndpoint e) { device = d; face = f; out = e; }
        String label() {
            return (device.getProductName() == null ? "USB printer" : device.getProductName())
                + " (" + device.getVendorId() + ":" + device.getProductId() + ", interface " + face.getId() + ")";
        }
    }

    @PluginMethod public void printReceipt(PluginCall call) {
        main.post(() -> {
            if (pending != null) { call.reject("Finish the current print attempt first", "PRINT_BUSY"); return; }
            String document = call.getString("html");
            if (document == null || document.length() > 12000000 || !document.contains("receipt-paper")) {
                call.reject("Invalid saved receipt", "INVALID_RECEIPT"); return;
            }
            pending = call;
            html = document;
            call.getData().remove("html");
            try { choosePrinter(); }
            catch (RuntimeException error) { reject("Could not access USB printers: " + error.getMessage(), "USB_UNAVAILABLE"); }
        });
    }

    private UsbManager usb() { return (UsbManager)getContext().getSystemService(Context.USB_SERVICE); }

    @PluginMethod public void openPrinterSetup(PluginCall call) {
        main.post(() -> {
            if (pending != null) { call.reject("Finish the current print attempt first", "PRINT_BUSY"); return; }
            try { PrinterServiceSetup.show(getActivity()); call.resolve(); }
            catch (RuntimeException error) { call.reject("Could not open printer setup", "PRINT_SETUP_FAILED", error); }
        });
    }

    private void choosePrinter() {
        List<Port> ports = new ArrayList<>();
        UsbManager manager = usb();
        if (manager != null) for (UsbDevice device : manager.getDeviceList().values()) {
            for (int i = 0; i < device.getInterfaceCount(); i++) {
                UsbInterface face = device.getInterface(i);
                // Never send receipt bytes to unrelated storage/HID/serial interfaces.
                if (face.getInterfaceClass() != UsbConstants.USB_CLASS_PRINTER
                        && face.getInterfaceClass() != UsbConstants.USB_CLASS_VENDOR_SPEC) continue;
                for (int e = 0; e < face.getEndpointCount(); e++) {
                    UsbEndpoint endpoint = face.getEndpoint(e);
                    if (endpoint.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK && endpoint.getDirection() == UsbConstants.USB_DIR_OUT) {
                        ports.add(new Port(device, face, endpoint)); break;
                    }
                }
            }
        }
        if (ports.isEmpty()) {
            reject("Android reports no compatible USB printer. Connect the RP 3230 to this POS by USB and power it on. Use Printer setup for the separate Android service route.", "USB_NOT_FOUND");
            return;
        }
        // A single standard printer is unambiguous. Do not divert it into Android's PDF dialog.
        if (ports.size() == 1 && ports.get(0).face.getInterfaceClass() == UsbConstants.USB_CLASS_PRINTER) {
            requestAccess(ports.get(0));
            return;
        }
        // Require explicit selection for multiple printers or an unknown vendor-specific interface.
        String[] labels = new String[ports.size()];
        for (int i = 0; i < ports.size(); i++) labels[i] = ports.get(i).label();
        chooser = new AlertDialog.Builder(getActivity()).setTitle("Select ESC/POS USB printer")
            .setItems(labels, (dialog, index) -> requestAccess(ports.get(index)))
            .setNegativeButton("Cancel", (dialog, which) -> cancelled())
            .setOnCancelListener(dialog -> cancelled()).show();
    }

    private void requestAccess(Port port) {
        try {
            if (usb().hasPermission(port.device)) { render(port); return; }
            String action = getContext().getPackageName() + ".USB_PRINT_PERMISSION";
            permission = new BroadcastReceiver() {
                @Override public void onReceive(Context context, Intent intent) {
                    if (!action.equals(intent.getAction()) || pending == null) return;
                    clearPermission();
                    // The OS permission state is authoritative, not broadcast extras.
                    if (usb().hasPermission(port.device)) render(port);
                    else reject("USB access denied or printer disconnected. Allow access and reprint the saved bill.", "USB_PERMISSION_DENIED");
                }
            };
            if (Build.VERSION.SDK_INT >= 33) getContext().registerReceiver(permission, new IntentFilter(action), Context.RECEIVER_NOT_EXPORTED);
            else getContext().registerReceiver(permission, new IntentFilter(action));
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
            PendingIntent request = PendingIntent.getBroadcast(getContext(), 0, new Intent(action).setPackage(getContext().getPackageName()), flags);
            main.postDelayed(permissionTimeout, 60000);
            usb().requestPermission(port.device, request);
        } catch (RuntimeException error) { reject("Could not request USB access: " + error.getMessage(), "USB_PERMISSION_FAILED"); }
    }

    private void render(Port port) {
        try {
            int dots = getConfig().getInt("printableDots", 576);
            if (dots < 384 || dots > 832 || dots % 8 != 0) throw new IllegalArgumentException("printableDots must be a multiple of 8 between 384 and 832");
            raster = new ReceiptRaster(getBridge(), html, dots, new ReceiptRaster.Ready() {
                @Override public void ready(ReceiptRaster ready) {
                    html = null;
                    try { worker.execute(() -> send(port, ready)); }
                    catch (RuntimeException error) { reject("Print worker unavailable", "PRINT_INTERRUPTED"); }
                }
                @Override public void failed(Exception error) { reject(error.getMessage(), "RENDER_FAILED"); }
            });
        } catch (RuntimeException error) { reject("Could not render saved receipt: " + error.getMessage(), "RENDER_FAILED"); }
    }

    private void send(Port port, ReceiptRaster ready) {
        UsbDeviceConnection opened = null;
        boolean claimed = false;
        Exception failure = null;
        try {
            opened = usb().openDevice(port.device);
            if (opened == null) throw new IOException("Printer disconnected or USB access lost");
            connection = opened;
            claimed = opened.claimInterface(port.face, true);
            if (!claimed) throw new IOException("USB printer is busy. Close other printer apps/services and retry.");
            UsbDeviceConnection output = opened;
            EscPos.Transfer transfer = (bytes, offset, length) -> output.bulkTransfer(port.out, bytes, offset, length, 5000);
            EscPos.writeFully(transfer, new byte[]{ 0x1b, 0x40 });
            int height = ready.height();
            for (int top = 0; top < height; top += 256) {
                if (Thread.currentThread().isInterrupted()) throw new IOException("Printing interrupted");
                EscPos.writeFully(transfer, ready.stripe(top, Math.min(256, height - top)));
            }
            // Feed for manual tear. No cutter, drawer or automatic retry commands.
            EscPos.writeFully(transfer, new byte[]{ 0x1b, 0x64, 0x04 });
        } catch (Exception error) { failure = error; }
        finally {
            if (opened != null) {
                try { if (claimed) opened.releaseInterface(port.face); }
                catch (RuntimeException error) { if (failure == null) failure = error; }
                try { opened.close(); }
                catch (RuntimeException error) { if (failure == null) failure = error; }
            }
            connection = null;
        }
        Exception result = failure;
        main.post(() -> {
            if (pending == null) return;
            if (result != null) reject("USB printing stopped: " + result.getMessage() + ". Check paper before reprinting; the bill remains saved.", "USB_WRITE_FAILED");
            else {
                JSObject response = new JSObject();
                response.put("state", "submitted");
                response.put("detail", "ESC/POS USB bytes sent. Check physical paper output; completion is not confirmed.");
                PluginCall call = pending;
                cleanup();
                call.resolve(response);
            }
        });
    }

    private void clearPermission() {
        main.removeCallbacks(permissionTimeout);
        if (permission != null) { getContext().unregisterReceiver(permission); permission = null; }
    }

    private void cleanup() {
        clearPermission();
        if (chooser != null) { chooser.dismiss(); chooser = null; }
        if (raster != null) { raster.close(); raster = null; }
        pending = null;
        html = null;
    }

    private void reject(String message, String code) {
        PluginCall call = pending;
        cleanup();
        if (call != null) call.reject(message, code);
    }

    private void cancelled() {
        finishChoice("cancelled");
    }

    private void finishChoice(String state) {
        PluginCall call = pending;
        cleanup();
        if (call != null) { JSObject response = new JSObject(); response.put("state", state); call.resolve(response); }
    }

    @Override protected void handleOnDestroy() {
        reject("App closed during printing. Check paper before reprinting the saved bill.", "PRINT_INTERRUPTED");
        worker.shutdownNow();
        UsbDeviceConnection opened = connection;
        if (opened != null) opened.close();
        super.handleOnDestroy();
    }
}
