package in.vgl.restaurant;

/** Resource routing shared by the renderer and its Android-independent regression tests. */
final class ReceiptResourcePolicy {
    enum Route { WEBVIEW_DATA, APP_ASSET, BLOCK }
    private ReceiptResourcePolicy() {}

    static Route route(String url, String appOrigin) {
        // WebViewClient also intercepts data: URLs. Only WebView should decode these bytes.
        if (url.regionMatches(true, 0, "data:", 0, 5)) return Route.WEBVIEW_DATA;
        String prefix = appOrigin.endsWith("/") ? appOrigin : appOrigin + "/";
        if (url.startsWith(prefix)) return Route.APP_ASSET;
        return Route.BLOCK;
    }
}
