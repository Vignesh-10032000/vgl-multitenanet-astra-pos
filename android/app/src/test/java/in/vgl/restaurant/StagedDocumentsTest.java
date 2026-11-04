package in.vgl.restaurant;

import static org.junit.Assert.*;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.util.Arrays;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class StagedDocumentsTest {
    @Rule public TemporaryFolder temporary = new TemporaryFolder();
    private File staged(String token) { return new File(new File(temporary.getRoot(), "restaurant-document-staging"), token); }

    @Test public void multiMegabyteExportUsesSmallTokenAndCopiesExactly() throws Exception {
        byte[] source = new byte[3 * 1024 * 1024];
        Arrays.fill(source, (byte) 173);
        String token = StagedDocuments.stage(temporary.getRoot(), source);
        assertTrue(token.length() < 100);
        assertEquals(source.length, staged(token).length());
        final boolean[] closed = {false}, flushed = {false};
        ByteArrayOutputStream output = new ByteArrayOutputStream() {
            @Override public void flush() { flushed[0] = true; }
            @Override public void close() { closed[0] = true; }
        };
        StagedDocuments.copyAndClose(temporary.getRoot(), token, output);
        assertArrayEquals(source, output.toByteArray());
        assertTrue(closed[0]); assertTrue(flushed[0]); assertFalse(staged(token).exists());
    }

    @Test public void cancellingRemovesOnlyTheStagedExport() throws Exception {
        String first = StagedDocuments.stage(temporary.getRoot(), new byte[]{1});
        String second = StagedDocuments.stage(temporary.getRoot(), new byte[]{2});
        StagedDocuments.discard(temporary.getRoot(), first);
        assertFalse(staged(first).exists()); assertTrue(staged(second).exists());
    }

    @Test public void providerWriteFailureClosesAndPropagates() throws Exception {
        String token = StagedDocuments.stage(temporary.getRoot(), new byte[]{1});
        final boolean[] closed = {false};
        OutputStream output = new OutputStream() {
            @Override public void write(int value) throws IOException { throw new IOException("disk full"); }
            @Override public void close() { closed[0] = true; }
        };
        IOException error = assertThrows(IOException.class, () -> StagedDocuments.copyAndClose(temporary.getRoot(), token, output));
        assertEquals("disk full", error.getMessage()); assertTrue(closed[0]); assertFalse(staged(token).exists());
    }

    @Test public void missingCacheAndMissingProviderStreamFailExplicitly() throws Exception {
        final boolean[] closed = {false};
        OutputStream output = new ByteArrayOutputStream() { @Override public void close() { closed[0] = true; } };
        assertThrows(IOException.class, () -> StagedDocuments.copyAndClose(temporary.getRoot(), "document-missing.pending", output));
        assertTrue(closed[0]);
        String token = StagedDocuments.stage(temporary.getRoot(), new byte[]{1});
        assertThrows(IOException.class, () -> StagedDocuments.copyAndClose(temporary.getRoot(), token, null));
        assertFalse(staged(token).exists());
    }

    @Test public void providerCloseFailureCannotReportSuccessfulSave() throws Exception {
        String token = StagedDocuments.stage(temporary.getRoot(), new byte[]{1});
        OutputStream output = new ByteArrayOutputStream() {
            @Override public void close() throws IOException { throw new IOException("provider close failed"); }
        };
        IOException error = assertThrows(IOException.class, () -> StagedDocuments.copyAndClose(temporary.getRoot(), token, output));
        assertEquals("provider close failed", error.getMessage()); assertFalse(staged(token).exists());
    }

    @Test public void invalidTokensCannotReadOrDeleteOtherFiles() throws Exception {
        File backup = new File(temporary.getRoot(), "backup.json");
        try (FileOutputStream output = new FileOutputStream(backup)) { output.write(new byte[]{9,8,7}); }
        assertThrows(IOException.class, () -> StagedDocuments.copyAndClose(temporary.getRoot(), "../backup.json", new ByteArrayOutputStream()));
        StagedDocuments.discard(temporary.getRoot(), "../backup.json");
        assertArrayEquals(new byte[]{9,8,7}, Files.readAllBytes(backup.toPath()));
    }
}
