package com.spyhex.app.features.addresses;

import android.content.Context;
import android.content.SharedPreferences;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class AddressManager {
    private static AddressManager instance;
    private final Context ctx;
    private final SharedPreferences prefs;
    private final List<AddressEntry> addresses = new ArrayList<>();

    private AddressManager() {
        this.ctx = SpyHexApp.getContext();
        this.prefs = ctx.getSharedPreferences("spyhex_addresses", Context.MODE_PRIVATE);
        loadAddresses();
    }

    public static synchronized AddressManager getInstance() {
        if (instance == null) instance = new AddressManager();
        return instance;
    }

    private void loadAddresses() {
        String stored = prefs.getString("addresses", "[]");
        try {
            JSONArray arr = new JSONArray(stored);
            for (int i = 0; i < arr.length(); i++) {
                JSONObject o = arr.getJSONObject(i);
                addresses.add(new AddressEntry(
                    o.optString("label"),
                    o.optString("address"),
                    o.optString("cryptoType", "btc")
                ));
            }
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
    }

    public void addAddress(String label, String address, String cryptoType) {
        addresses.add(new AddressEntry(label, address, cryptoType));
        saveAddresses();
    }

    private void saveAddresses() {
        JSONArray arr = new JSONArray();
        for (AddressEntry a : addresses) {
            JSONObject o = new JSONObject();
            try {
                o.put("label", a.label);
                o.put("address", a.address);
                o.put("cryptoType", a.cryptoType);
                arr.put(o);
            } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        }
        prefs.edit().putString("addresses", arr.toString()).apply();
    }

    public JSONObject getAddresses() {
        JSONObject r = new JSONObject();
        JSONArray arr = new JSONArray();
        for (AddressEntry a : addresses) {
            JSONObject o = new JSONObject();
            try {
                o.put("label", a.label);
                o.put("address", a.address);
                o.put("cryptoType", a.cryptoType);
                arr.put(o);
            } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        }
        try {
            r.put("addresses", arr);
            r.put("count", addresses.size());
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return r;
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("count", addresses.size());
            s.put("ready", true);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    private static class AddressEntry {
        String label, address, cryptoType;
        AddressEntry(String l, String a, String c) {
            this.label = l; this.address = a; this.cryptoType = c;
        }
    }
}
