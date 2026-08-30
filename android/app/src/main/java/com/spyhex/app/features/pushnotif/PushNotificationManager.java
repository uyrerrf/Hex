package com.spyhex.app.features.pushnotif;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import androidx.core.app.NotificationCompat;

import com.spyhex.app.R;
import com.spyhex.app.core.SpyHexApp;

import org.json.JSONObject;

public class PushNotificationManager {
    private static PushNotificationManager instance;
    private final Context ctx;
    private final NotificationManager nm;
    private static final String CHANNEL_ID = "spyhex_channel";

    private PushNotificationManager() {
        this.ctx = SpyHexApp.getContext();
        this.nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        createChannel();
    }

    public static synchronized PushNotificationManager getInstance() {
        if (instance == null) instance = new PushNotificationManager();
        return instance;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "SpyHex Notifications",
                NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("SpyHex push notification channel");
            nm.createNotificationChannel(channel);
        }
    }

    public static void show(String title, String body) {
        Context ctx = SpyHexApp.getContext();
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);

        Intent intent = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        PendingIntent pendingIntent = PendingIntent.getActivity(ctx, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent);

        nm.notify((int) System.currentTimeMillis(), builder.build());
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("ready", true);
            s.put("channelCreated", true);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }
}
