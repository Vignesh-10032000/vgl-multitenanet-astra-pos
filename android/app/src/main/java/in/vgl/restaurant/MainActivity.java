package in.vgl.restaurant;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;
import android.view.WindowManager;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle state) {
        registerPlugin(RestaurantDocumentsPlugin.class);
        registerPlugin(RestaurantBackupPlugin.class);
        registerPlugin(RestaurantPrinterPlugin.class);
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }
}
