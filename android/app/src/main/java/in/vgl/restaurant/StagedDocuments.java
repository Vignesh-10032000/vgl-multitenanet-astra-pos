package in.vgl.restaurant;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;

/** Keep export bytes in private cache, never in Android activity saved state. */
final class StagedDocuments {
    private StagedDocuments() {}

    private static File directory(File cache) throws IOException {
        File directory = new File(cache, "restaurant-document-staging");
        if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("Cannot prepare export cache");
        return directory;
    }

    static String stage(File cache, byte[] bytes) throws IOException {
        File file = File.createTempFile("document-", ".pending", directory(cache));
        try {
            DocumentWriter.writeAndClose(new FileOutputStream(file), bytes);
            return file.getName();
        } catch (IOException | RuntimeException error) {
            file.delete();
            throw error;
        }
    }

    private static File resolve(File cache, String token) throws IOException {
        if (token == null || !token.matches("document-[a-zA-Z0-9_-]+\\.pending")) throw new IOException("Invalid staged export");
        File parent = directory(cache).getCanonicalFile();
        File file = new File(parent, token).getCanonicalFile();
        if (!parent.equals(file.getParentFile())) throw new IOException("Invalid staged export location");
        return file;
    }

    static void copyAndClose(File cache, String token, OutputStream destination) throws IOException {
        // Close the provider stream even when Android has evicted the cached export.
        try (OutputStream output = destination) {
            if (output == null) throw new IOException("Document provider returned no output stream");
            File file = resolve(cache, token);
            try (FileInputStream input = new FileInputStream(file)) {
                byte[] buffer = new byte[32768];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                output.flush();
            }
        } finally {
            discard(cache, token);
        }
    }

    static void discard(File cache, String token) {
        try { resolve(cache, token).delete(); }
        catch (IOException ignored) { /* Invalid tokens never select files outside this cache. */ }
    }
}
