package com.spyhex.app.features.firewall;

import android.content.Context;
import android.content.SharedPreferences;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class FirewallManager {
    private static FirewallManager instance;
    private final Context ctx;
    private final SharedPreferences prefs;
    private final List<FirewallRule> rules = new ArrayList<>();
    private boolean enabled = false;

    private FirewallManager() {
        this.ctx = SpyHexApp.getContext();
        this.prefs = ctx.getSharedPreferences("spyhex_firewall", Context.MODE_PRIVATE);
        loadRules();
    }

    public static synchronized FirewallManager getInstance() {
        if (instance == null) instance = new FirewallManager();
        return instance;
    }

    private void loadRules() {
        String stored = prefs.getString("rules", "[]");
        try {
            JSONArray arr = new JSONArray(stored);
            for (int i = 0; i < arr.length(); i++) {
                JSONObject r = arr.getJSONObject(i);
                rules.add(new FirewallRule(
                    r.optString("target"),
                    r.optString("targetValue"),
                    r.optString("ruleType", "block")
                ));
            }
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
    }

    public void block(String target, String rule) {
        rules.add(new FirewallRule(target, rule, "block"));
        saveRules();
        enabled = true;
    }

    public void allow(String target) {
        rules.removeIf(r -> r.target.equals(target));
        saveRules();
    }

    private void saveRules() {
        JSONArray arr = new JSONArray();
        for (FirewallRule r : rules) {
            JSONObject o = new JSONObject();
            try {
                o.put("target", r.target);
                o.put("targetValue", r.targetValue);
                o.put("ruleType", r.ruleType);
                arr.put(o);
            } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        }
        prefs.edit().putString("rules", arr.toString()).apply();
    }

    public boolean isBlocked(String target) {
        for (FirewallRule r : rules) {
            if (r.target.equals(target) && "block".equals(r.ruleType)) {
                return true;
            }
        }
        return false;
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("enabled", enabled);
            s.put("ruleCount", rules.size());
            JSONArray arr = new JSONArray();
            for (FirewallRule r : rules) {
                JSONObject o = new JSONObject();
                o.put("target", r.target);
                o.put("targetValue", r.targetValue);
                o.put("ruleType", r.ruleType);
                arr.put(o);
            }
            s.put("rules", arr);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    private static class FirewallRule {
        String target;
        String targetValue;
        String ruleType;
        FirewallRule(String t, String v, String rt) {
            this.target = t;
            this.targetValue = v;
            this.ruleType = rt;
        }
    }
}
