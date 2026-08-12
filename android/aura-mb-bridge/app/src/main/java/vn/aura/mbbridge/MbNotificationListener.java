package vn.aura.mbbridge;

import android.app.Notification;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONObject;

import java.io.BufferedOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Filters by the MB Bank app label/package before inspecting content. The raw notification
 * body never leaves the phone: only amount, timestamp and a one-way transaction fingerprint
 * are sent to AURA.
 */
public final class MbNotificationListener extends NotificationListenerService {
    private static final Pattern AMOUNT = Pattern.compile(
            "(?iu)(?:\\+\\s*)?([0-9][0-9.,\\s]{0,24})\\s*(?:vnd|vnđ|đ)");
    private final ExecutorService sender = Executors.newSingleThreadExecutor();

    @Override public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || !isMbBank(sbn)) return;
        String text = notificationText(sbn.getNotification());
        if (!looksIncoming(text)) return;
        double amount = amountFrom(text);
        if (amount <= 0 || !BridgeConfig.isReady(this)) return;

        String fingerprint = sha256(sbn.getPackageName() + "|" + normalize(text));
        if (BridgeConfig.hasSeen(this, fingerprint)) return;
        long seconds = Math.max(1L, sbn.getPostTime() / 1000L);
        sender.execute(() -> post(amount, fingerprint, seconds));
    }

    @Override public void onDestroy() {
        sender.shutdownNow();
        super.onDestroy();
    }

    private boolean isMbBank(StatusBarNotification sbn) {
        String packageName = sbn.getPackageName() == null ? "" : sbn.getPackageName().toLowerCase(Locale.ROOT);
        if (packageName.contains("mbmobile") || packageName.contains("mbbank")) return true;
        try {
            ApplicationInfo info = getPackageManager().getApplicationInfo(sbn.getPackageName(), 0);
            String label = getPackageManager().getApplicationLabel(info).toString().toLowerCase(Locale.ROOT);
            return label.contains("mb bank") || label.equals("mbbank");
        } catch (PackageManager.NameNotFoundException ignored) {
            return false;
        }
    }

    private static String notificationText(Notification notification) {
        if (notification == null) return "";
        Bundle extras = notification.extras;
        if (extras == null) return "";
        StringBuilder out = new StringBuilder();
        append(out, extras.getCharSequence(Notification.EXTRA_TITLE));
        append(out, extras.getCharSequence(Notification.EXTRA_TEXT));
        append(out, extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
        return out.toString();
    }

    private static void append(StringBuilder out, CharSequence value) {
        if (value != null && value.length() > 0) {
            if (out.length() > 0) out.append(' ');
            out.append(value);
        }
    }

    private static boolean looksIncoming(String text) {
        String normalized = normalize(text);
        return normalized.contains("bao co") || normalized.contains("ghi co")
                || normalized.contains("nhan tien") || normalized.contains("tang so du")
                || Pattern.compile("\\+\\s*[0-9][0-9.,\\s]*\\s*(vnd|đ)").matcher(normalized).find();
    }

    private static double amountFrom(String text) {
        Matcher matcher = AMOUNT.matcher(text == null ? "" : text);
        if (!matcher.find()) return 0;
        String digits = matcher.group(1).replaceAll("[^0-9]", "");
        try {
            return Double.parseDouble(digits);
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private void post(double amount, String reference, long receivedAt) {
        HttpURLConnection connection = null;
        try {
            JSONObject body = new JSONObject();
            body.put("amount", amount);
            body.put("currency", "VND");
            body.put("source", "mbbank_android_notification");
            body.put("reference", reference);
            body.put("description", "MB Bank báo có từ Android");
            body.put("received_at", receivedAt);
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) new URL(BridgeConfig.endpoint(this)).openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(10_000);
            connection.setReadTimeout(10_000);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("X-AURA-Cashflow-Token", BridgeConfig.token(this));
            connection.setFixedLengthStreamingMode(bytes.length);
            try (BufferedOutputStream output = new BufferedOutputStream(connection.getOutputStream())) {
                output.write(bytes);
            }
            int code = connection.getResponseCode(); // AURA is the source of truth and deduplicates again.
            if (code >= 200 && code < 300) BridgeConfig.remember(this, reference);
        } catch (Exception ignored) {
            // Network may be absent temporarily. A future MB notification can retry; no data is logged here.
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static String normalize(String value) {
        if (value == null) return "";
        String decomposed = Normalizer.normalize(value, Normalizer.Form.NFD)
                .replaceAll("\\p{M}", "");
        return decomposed.toLowerCase(Locale.ROOT).replaceAll("\\s+", " ").trim();
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : digest) hex.append(String.format(Locale.ROOT, "%02x", b & 0xff));
            return hex.toString();
        } catch (Exception ignored) {
            return Integer.toHexString(value.hashCode());
        }
    }
}
