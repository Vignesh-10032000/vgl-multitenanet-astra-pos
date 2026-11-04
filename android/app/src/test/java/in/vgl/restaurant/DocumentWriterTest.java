package in.vgl.restaurant;

import static org.junit.Assert.*;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import org.junit.Test;

public class DocumentWriterTest {
    @Test public void successWaitsForFlushAndClose() throws Exception {
        final boolean[] closed = {false};
        final boolean[] flushed = {false};
        ByteArrayOutputStream output = new ByteArrayOutputStream() {
            @Override public void flush() { flushed[0] = true; }
            @Override public void close() { closed[0] = true; }
        };
        DocumentWriter.writeAndClose(output, new byte[] {1, 2, 3});
        assertArrayEquals(new byte[] {1, 2, 3}, output.toByteArray());
        assertTrue(flushed[0]);
        assertTrue(closed[0]);
    }

    @Test public void writeFailureStillClosesAndPropagates() {
        final boolean[] closed = {false};
        OutputStream output = new OutputStream() {
            @Override public void write(int value) throws IOException { throw new IOException("disk full"); }
            @Override public void close() { closed[0] = true; }
        };
        IOException error = assertThrows(IOException.class, () -> DocumentWriter.writeAndClose(output, new byte[] {1}));
        assertEquals("disk full", error.getMessage());
        assertTrue(closed[0]);
    }

    @Test public void closeFailureCannotReportSuccessfulSave() {
        OutputStream output = new ByteArrayOutputStream() {
            @Override public void close() throws IOException { throw new IOException("provider close failed"); }
        };
        IOException error = assertThrows(IOException.class, () -> DocumentWriter.writeAndClose(output, new byte[] {1}));
        assertEquals("provider close failed", error.getMessage());
    }

    @Test public void missingProviderStreamFailsExplicitly() {
        assertThrows(IOException.class, () -> DocumentWriter.writeAndClose(null, new byte[0]));
    }
}
