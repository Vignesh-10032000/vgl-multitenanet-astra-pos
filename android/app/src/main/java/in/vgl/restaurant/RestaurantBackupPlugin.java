package in.vgl.restaurant;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** User-owned SAF backups: append-only documents, never app-private storage or automatic deletion. */
@CapacitorPlugin(name = "RestaurantBackup")
public class RestaurantBackupPlugin extends Plugin {
    private final ExecutorService files = Executors.newSingleThreadExecutor();
    private boolean choosing = false;
    private static final int LIMIT = 100000000;
    private static final String PREFS = "restaurant-shared-backup";
    private void work(PluginCall call, Runnable operation) {
        try { files.execute(operation); }
        catch (RuntimeException error) { call.reject("App closed before the backup operation started", "BACKUP_INTERRUPTED", error); }
    }

    private Uri folder() throws IOException {
        String value = getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("folder", null);
        if (value == null) throw new IOException("Reconnect your shared backup folder");
        Uri uri = Uri.parse(value);
        if (!"content".equals(uri.getScheme())) throw new IOException("Invalid backup folder");
        return uri;
    }
    private JSObject status() {
        JSObject result = new JSObject();
        try {
            Uri uri = folder();
            Uri doc = DocumentsContract.buildDocumentUriUsingTree(uri, DocumentsContract.getTreeDocumentId(uri));
            try (Cursor cursor = getContext().getContentResolver().query(doc,
                    new String[]{DocumentsContract.Document.COLUMN_DISPLAY_NAME}, null, null, null)) {
                if (cursor == null || !cursor.moveToFirst()) throw new IOException("Backup folder is unavailable");
                result.put("connected", true); result.put("name", cursor.getString(0));
            }
        } catch (IOException | RuntimeException error) { result.put("connected", false); result.put("detail", error.getMessage()); }
        return result;
    }
    @PluginMethod public void folderStatus(PluginCall call) { work(call, () -> call.resolve(status())); }

    @PluginMethod public void chooseFolder(PluginCall call) {
        if (choosing) { call.reject("Finish choosing the current folder", "BUSY"); return; }
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION |
            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        choosing = true;
        try { startActivityForResult(call, intent, "folderChosen"); }
        catch (RuntimeException error) { choosing = false; call.reject("Could not open folder picker", "PICKER_FAILED", error); }
    }
    @ActivityCallback private void folderChosen(PluginCall call, ActivityResult result) {
        choosing = false;
        if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) {
            call.reject("Folder selection cancelled", "CANCELLED"); return;
        }
        Uri uri = result.getData().getData();
        try {
            String id = DocumentsContract.getTreeDocumentId(uri).replace('\\', '/').toLowerCase(java.util.Locale.ROOT);
            if (id.contains("android/data") || id.contains("android/obb")) throw new IOException("Choose a folder outside Android/data and Android/obb");
            int flags = result.getData().getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            if (flags != (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)) throw new IOException("The backup folder needs read and write access");
            getContext().getContentResolver().takePersistableUriPermission(uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("folder", uri.toString()).apply();
            work(call, () -> call.resolve(status()));
        } catch (IOException | RuntimeException error) { call.reject("Could not connect backup folder: " + error.getMessage(), "FOLDER_FAILED", error); }
    }

    private List<JSObject> documents() throws IOException {
        Uri tree = folder();
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree));
        List<JSObject> rows = new ArrayList<>();
        try (Cursor cursor = getContext().getContentResolver().query(children, new String[]{
            DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_SIZE, DocumentsContract.Document.COLUMN_LAST_MODIFIED,
            DocumentsContract.Document.COLUMN_MIME_TYPE}, null, null, null)) {
            if (cursor == null) throw new IOException("Could not read the backup folder");
            while (cursor.moveToNext()) {
                String name = cursor.getString(1);
                if (name == null || !name.startsWith("restaurant-backup-") || !name.endsWith(".json") ||
                    DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(4))) continue;
                JSObject row = new JSObject(); row.put("name", name); row.put("size", cursor.getLong(2)); row.put("modified", cursor.getLong(3));
                row.put("uri", DocumentsContract.buildDocumentUriUsingTree(tree, cursor.getString(0)).toString());
                rows.add(row);
            }
        }
        rows.sort((a, b) -> Long.compare(b.optLong("modified"), a.optLong("modified")));
        return rows;
    }
    @PluginMethod public void listBackups(PluginCall call) {
        work(call, () -> {
            try { call.resolve(new JSObject().put("files", new JSArray(documents()))); }
            catch (IOException | RuntimeException error) { call.reject("Could not find backups: " + error.getMessage(), "SCAN_FAILED", error); }
        });
    }
    @PluginMethod public void readBackup(PluginCall call) {
        work(call, () -> {
            try {
                String requested = call.getString("uri", "");
                boolean found = false;
                for (JSObject row : documents()) if (requested.equals(row.getString("uri"))) { found = true; break; }
                if (!found) throw new IOException("Backup is outside the connected folder");
                String source;
                try (InputStream input = getContext().getContentResolver().openInputStream(Uri.parse(requested));
                     ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                    if (input == null) throw new IOException("Backup file is unavailable");
                    byte[] buffer = new byte[16384]; int count;
                    while ((count = input.read(buffer)) != -1) {
                        if ((long)output.size() + count > LIMIT) throw new IOException("Backup exceeds 100 MB limit");
                        output.write(buffer, 0, count);
                    }
                    source = new String(output.toByteArray(), StandardCharsets.UTF_8);
                }
                call.resolve(new JSObject().put("source", source));
            } catch (IOException | RuntimeException error) { call.reject("Could not read backup: " + error.getMessage(), "READ_FAILED", error); }
        });
    }
    @PluginMethod public void writeBackup(PluginCall call) {
        String name = call.getString("name", ""), source = call.getString("source", "");
        if (!name.matches("restaurant-backup-[A-Za-z0-9._-]+\\.json") || source.isEmpty() || source.length() > LIMIT) {
            call.reject("Invalid backup name or size", "INVALID_BACKUP"); return;
        }
        work(call, () -> {
            try {
                byte[] bytes = source.getBytes(StandardCharsets.UTF_8);
                if (bytes.length > LIMIT) throw new IOException("Backup exceeds 100 MB limit");
                Uri tree = folder();
                Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree));
                Uri created = DocumentsContract.createDocument(getContext().getContentResolver(), parent, "application/json", name);
                if (created == null) throw new IOException("The provider could not create a backup");
                DocumentWriter.writeAndClose(getContext().getContentResolver().openOutputStream(created, "wt"), bytes);
                call.resolve(new JSObject().put("state", "saved").put("uri", created.toString()));
            } catch (IOException | RuntimeException error) { call.reject("Backup was not saved: " + error.getMessage(), "WRITE_FAILED", error); }
        });
    }
    @Override protected void handleOnDestroy() { files.shutdown(); super.handleOnDestroy(); }
}
