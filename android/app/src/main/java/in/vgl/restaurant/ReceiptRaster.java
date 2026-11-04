package in.vgl.restaurant;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebResourceError;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import com.getcapacitor.Bridge;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

/** Separate local-only receipt WebView; one 256-row bitmap at a time, never a full-roll bitmap. */
final class ReceiptRaster implements AutoCloseable {
    interface Ready { void ready(ReceiptRaster raster); void failed(Exception error); }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final WebView view;
    private final int nativeWidth;
    private int nativeHeight;
    private int dotWidth;
    private boolean finished;
    private volatile boolean closed;
    private final Ready callback;
    private final Runnable timeout = () -> fail(new IOException("Receipt rendering timed out; no USB bytes sent."));

    ReceiptRaster(Bridge bridge, String html, int dots, Ready callback) {
        this.callback = callback;
        dotWidth = dots;
        float density = bridge.getActivity().getResources().getDisplayMetrics().density;
        nativeWidth = (int)Math.ceil(80.0 / 25.4 * 96 * density);
        view = new WebView(bridge.getActivity());
        view.setLayerType(View.LAYER_TYPE_SOFTWARE, null);
        view.setBackgroundColor(Color.WHITE);
        view.getSettings().setJavaScriptEnabled(true);
        view.getSettings().setAllowFileAccess(false);
        view.getSettings().setAllowContentAccess(false);
        view.getSettings().setTextZoom(100);
        view.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest request) {
                ReceiptResourcePolicy.Route route = ReceiptResourcePolicy.route(request.getUrl().toString(), bridge.getLocalUrl());
                if (route == ReceiptResourcePolicy.Route.WEBVIEW_DATA) return null;
                if (route == ReceiptResourcePolicy.Route.APP_ASSET) {
                    WebResourceResponse response = bridge.getLocalServer().shouldInterceptRequest(request);
                    if (response != null) return response;
                }
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Offline receipt assets only", null, new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return true; }
            @Override public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError error) {
                fail(new IOException("Receipt load failed (" + error.getErrorCode() + ", " + assetName(r) + "): " + error.getDescription() + "; no USB bytes sent."));
            }
            @Override public void onReceivedHttpError(WebView v, WebResourceRequest r, WebResourceResponse response) {
                fail(new IOException("Receipt asset rejected (HTTP " + response.getStatusCode() + ", " + assetName(r) + "); no USB bytes sent."));
            }
            @Override public void onPageFinished(WebView v, String url) {
                if (closed || finished) return;
                v.evaluateJavascript("window.receiptReady=0;Promise.all([document.fonts.ready,...Array.from(document.images,i=>i.decode())]).then(()=>{window.receiptReady=Array.from(document.fonts).some(f=>f.status==='error')?-1:1},()=>{window.receiptReady=-1})", null);
                awaitAssets();
            }
        });
        ViewGroup root = bridge.getActivity().findViewById(android.R.id.content);
        root.addView(view, 0, new FrameLayout.LayoutParams(nativeWidth, 1));
        view.measure(View.MeasureSpec.makeMeasureSpec(nativeWidth, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(1, View.MeasureSpec.EXACTLY));
        view.layout(0, 0, nativeWidth, 1);
        main.postDelayed(timeout, 20000);
        view.loadDataWithBaseURL(bridge.getLocalUrl() + "/", html, "text/html", "UTF-8", null);
    }

    private static String assetName(WebResourceRequest request) {
        if ("data".equals(request.getUrl().getScheme())) return "embedded data";
        String name = request.getUrl().getLastPathSegment();
        if (name == null || name.isEmpty()) return "receipt document";
        return name.substring(0, Math.min(name.length(), 120));
    }

    private void awaitAssets() {
        if (closed || finished) return;
        view.evaluateJavascript("window.receiptReady || 0", result -> {
            if (closed || finished) return;
            if ("-1".equals(result)) { fail(new IOException("Receipt image or font could not be loaded; no USB bytes sent.")); return; }
            if (!"1".equals(result)) { main.postDelayed(this::awaitAssets, 50); return; }
            view.evaluateJavascript("Math.ceil(document.querySelector('.receipt-paper').getBoundingClientRect().height)", height -> {
                if (closed || finished) return;
                try {
                    int cssHeight = Integer.parseInt(height);
                    nativeHeight = (int)Math.ceil(cssHeight * view.getResources().getDisplayMetrics().density);
                    if (cssHeight < 1 || nativeHeight > 40000) throw new IOException("Receipt is too long for direct printing; use Android print service.");
                    view.setLayoutParams(new FrameLayout.LayoutParams(nativeWidth, nativeHeight));
                    view.measure(View.MeasureSpec.makeMeasureSpec(nativeWidth, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(nativeHeight, View.MeasureSpec.EXACTLY));
                    view.layout(0, 0, nativeWidth, nativeHeight);
                    view.postVisualStateCallback(1, new WebView.VisualStateCallback() {
                        @Override public void onComplete(long id) {
                            if (closed || finished) return;
                            finished = true;
                            main.removeCallbacks(timeout);
                            callback.ready(ReceiptRaster.this);
                        }
                    });
                } catch (IOException | RuntimeException error) { fail(error); }
            });
        });
    }

    int height() { return (int)Math.ceil((double)nativeHeight * dotWidth / nativeWidth); }

    /** Called on the USB worker; only WebView drawing runs on the main thread. */
    byte[] stripe(int top, int rows) throws Exception {
        FutureTask<int[]> draw = new FutureTask<>(() -> {
            if (closed) throw new IOException("Receipt renderer closed");
            Bitmap bitmap = Bitmap.createBitmap(dotWidth, rows, Bitmap.Config.ARGB_8888);
            try {
                Canvas canvas = new Canvas(bitmap);
                canvas.drawColor(Color.WHITE);
                canvas.translate(0, -top);
                float scale = (float)dotWidth / nativeWidth;
                canvas.scale(scale, scale);
                view.draw(canvas);
                int[] pixels = new int[dotWidth * rows];
                bitmap.getPixels(pixels, 0, dotWidth, 0, 0, dotWidth, rows);
                return pixels;
            } finally { bitmap.recycle(); }
        });
        main.post(draw);
        return EscPos.raster(dotWidth, rows, draw.get(10, TimeUnit.SECONDS));
    }

    private void fail(Exception error) {
        if (closed || finished) return;
        finished = true;
        main.removeCallbacks(timeout);
        callback.failed(error);
        close();
    }

    @Override public void close() {
        if (closed) return;
        closed = true;
        main.removeCallbacks(timeout);
        view.stopLoading();
        if (view.getParent() != null) ((ViewGroup)view.getParent()).removeView(view);
        view.destroy();
    }
}
