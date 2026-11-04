package in.vgl.restaurant;

import java.io.IOException;

/** Bounded raster packets and exact USB progress; contains no invoice arithmetic. */
final class EscPos {
    private EscPos() {}

    interface Transfer { int write(byte[] bytes, int offset, int length); }

    static void writeFully(Transfer transfer, byte[] bytes) throws IOException {
        int offset = 0;
        while (offset < bytes.length) {
            int length = Math.min(4096, bytes.length - offset);
            int written = transfer.write(bytes, offset, length);
            if (written <= 0 || written > length) {
                throw new IOException("USB write stopped. Receipt may be partially printed; check paper before reprinting.");
            }
            offset += written;
        }
    }

    static byte[] raster(int width, int height, int[] pixels) {
        if (width < 8 || width > 832 || width % 8 != 0 || height < 1 || height > 256
                || pixels.length != width * height) throw new IllegalArgumentException("Invalid raster stripe");
        int stride = width / 8;
        byte[] packet = new byte[8 + stride * height];
        byte[] header = { 0x1d, 0x76, 0x30, 0, (byte)stride, (byte)(stride >> 8), (byte)height, (byte)(height >> 8) };
        System.arraycopy(header, 0, packet, 0, header.length);
        for (int i = 0; i < pixels.length; i++) {
            int p = pixels[i];
            int luminance = (((p >> 16) & 255) * 299 + ((p >> 8) & 255) * 587 + (p & 255) * 114) / 1000;
            if (luminance < 160) packet[8 + i / 8] |= (byte)(0x80 >> (i % 8));
        }
        return packet;
    }
}
