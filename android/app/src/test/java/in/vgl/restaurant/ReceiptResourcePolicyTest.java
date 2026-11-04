package in.vgl.restaurant;

import org.junit.Test;
import static org.junit.Assert.*;

public class ReceiptResourcePolicyTest {
    private static final String ORIGIN = "https://localhost";

    @Test public void tvsReceiptLoadRegressionLeavesEmbeddedDocumentAndImagesToWebView() {
        for (String url : new String[]{
            "data:text/html;charset=utf-8,%3Carticle%3Ereceipt%3C/article%3E",
            "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
            "data:image/png;base64,iVBORw0KGgo=",
            "data:image/svg+xml,%3Csvg%3E%3C/svg%3E",
            "data:font/woff2;base64,d09GMg=="
        }) assertEquals(url, ReceiptResourcePolicy.Route.WEBVIEW_DATA, ReceiptResourcePolicy.route(url, ORIGIN));
    }

    @Test public void bundledStylesFontsAndLogoRetainTheOfflineAppServer() {
        for (String path : new String[]{
            "/assets/index.css", "/static/fonts/noto-sans-tamil-tamil-400-normal.woff2", "/branding/logo.jpeg"
        }) {
            assertEquals(ReceiptResourcePolicy.Route.APP_ASSET, ReceiptResourcePolicy.route(ORIGIN + path, ORIGIN));
            assertEquals(ReceiptResourcePolicy.Route.APP_ASSET, ReceiptResourcePolicy.route(ORIGIN + path, ORIGIN + "/"));
        }
    }

    @Test public void unrelatedHostsAndDeviceFilesRemainBlocked() {
        for (String url : new String[]{
            "https://localhost.attacker.invalid/logo.png", "https://other.invalid/logo.png",
            "http://localhost/assets/index.css", "file:///sdcard/Download/logo.png",
            "content://documents/logo", "javascript:alert(1)", "blob:https://localhost/image"
        }) assertEquals(url, ReceiptResourcePolicy.Route.BLOCK, ReceiptResourcePolicy.route(url, ORIGIN));
    }
}
