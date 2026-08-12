package vn.aura.mbbridge;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** Stores only the local AURA endpoint and a random pairing token. */
public final class BridgeConfig {
    private static final String PREFS = "aura_mb_bridge";
    private static final String ENDPOINT = "endpoint";
    private static final String TOKEN = "token";
    private static final String SEEN = "seen";
    public static final String DEFAULT_ENDPOINT = "http://127.0.0.1:8766/api/cashflow/incoming";

    private BridgeConfig() { }

    public static void save(Context context, String endpoint, String token) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(ENDPOINT, endpoint == null ? "" : endpoint.trim())
                .putString(TOKEN, token == null ? "" : token.trim())
                .apply();
    }

    public static String endpoint(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(ENDPOINT, DEFAULT_ENDPOINT);
    }

    public static String token(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(TOKEN, "");
    }

    public static boolean isReady(Context context) {
        String url = endpoint(context);
        return url != null && url.startsWith("http") && !token(context).isEmpty();
    }

    public static boolean hasSeen(Context context, String fingerprint) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        return prefs.getStringSet(SEEN, new LinkedHashSet<>()).contains(fingerprint);
    }

    public static void remember(Context context, String fingerprint) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        Set<String> current = new LinkedHashSet<>(prefs.getStringSet(SEEN, new LinkedHashSet<>()));
        current.add(fingerprint);
        List<String> newest = new ArrayList<>(current);
        while (newest.size() > 150) newest.remove(0);
        prefs.edit().putStringSet(SEEN, new LinkedHashSet<>(newest)).apply();
    }
}
