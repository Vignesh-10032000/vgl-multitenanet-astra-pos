package in.vgl.restaurant;

import org.junit.Test;
import static org.junit.Assert.*;

public class PrinterServiceSetupTest {
    @Test public void disabledAndMalformedSettingsAreNotReady() {
        assertFalse(PrinterServiceSetup.containsService(null));
        assertFalse(PrinterServiceSetup.containsService(""));
        assertFalse(PrinterServiceSetup.containsService("com.loopedlabs.usbprintservice"));
        assertFalse(PrinterServiceSetup.containsService("com.loopedlabs.usbprintservice/"));
    }

    @Test public void unrelatedAndSimilarlyNamedServicesDoNotEnableTheUsbRoute() {
        assertFalse(PrinterServiceSetup.containsService("com.android.bips/.BuiltinPrintService"));
        assertFalse(PrinterServiceSetup.containsService("com.loopedlabs.usbprintservice.other/.Service"));
    }

    @Test public void verifiedServiceIsRecognizedAmongOtherEnabledServices() {
        assertTrue(PrinterServiceSetup.containsService("com.loopedlabs.usbprintservice/.UsbService"));
        assertTrue(PrinterServiceSetup.containsService("com.android.bips/.BuiltinPrintService:com.loopedlabs.usbprintservice/com.loopedlabs.usbprintservice.PrintService"));
    }
}
