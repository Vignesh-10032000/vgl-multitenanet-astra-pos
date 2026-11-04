package in.vgl.restaurant;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Arrays;

public class EscPosTest {
    @Test public void rasterHeaderAndBitOrderPreserveRowBoundaries() {
        int[] pixels = new int[16];
        Arrays.fill(pixels, 0xffffffff);
        pixels[0] = 0xff000000;
        pixels[7] = 0xff000000;
        pixels[9] = 0xff000000;
        assertArrayEquals(new byte[]{29, 118, 48, 0, 1, 0, 2, 0, (byte)0x81, 0x40}, EscPos.raster(8, 2, pixels));
    }

    @Test public void fullStripeUsesLittleEndianHeightAndWhiteStaysUnprinted() {
        int[] pixels = new int[576 * 256];
        Arrays.fill(pixels, 0xffffffff);
        byte[] bytes = EscPos.raster(576, 256, pixels);
        assertEquals(72, bytes[4]);
        assertEquals(0, bytes[6]);
        assertEquals(1, bytes[7]);
        assertEquals(8 + 72 * 256, bytes.length);
        for (int i = 8; i < bytes.length; i++) assertEquals(0, bytes[i]);
    }

    @Test public void partialWritesPreserveEveryByteWithoutDuplication() throws Exception {
        byte[] bytes = new byte[9000];
        for (int i = 0; i < bytes.length; i++) bytes[i] = (byte)i;
        ByteArrayOutputStream received = new ByteArrayOutputStream();
        EscPos.writeFully((data, offset, length) -> {
            assertTrue(length <= 4096);
            int count = Math.min(37, length);
            received.write(data, offset, count);
            return count;
        }, bytes);
        assertArrayEquals(bytes, received.toByteArray());
    }

    @Test public void failedOrStalledWritesStopWithoutAutomaticRetry() {
        for (int result : new int[]{0, -1, 999}) {
            int[] calls = {0};
            assertThrows(IOException.class, () -> EscPos.writeFully((data, offset, length) -> { calls[0]++; return result; }, new byte[8]));
            assertEquals(1, calls[0]);
        }
    }

    @Test public void oversizedOrIncompleteStripesAreRejected() {
        assertThrows(IllegalArgumentException.class, () -> EscPos.raster(575, 1, new int[575]));
        assertThrows(IllegalArgumentException.class, () -> EscPos.raster(576, 257, new int[576 * 257]));
        assertThrows(IllegalArgumentException.class, () -> EscPos.raster(576, 1, new int[8]));
    }
}
