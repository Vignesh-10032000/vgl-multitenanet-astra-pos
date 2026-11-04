package in.vgl.restaurant;

import java.io.IOException;
import java.io.OutputStream;

/** A provider save succeeds only after writing, flushing and closing its stream. */
final class DocumentWriter {
    private DocumentWriter() {}

    static void writeAndClose(OutputStream destination, byte[] data) throws IOException {
        if (destination == null) throw new IOException("Document provider returned no output stream");
        try (OutputStream stream = destination) {
            stream.write(data);
            stream.flush();
        }
    }
}
