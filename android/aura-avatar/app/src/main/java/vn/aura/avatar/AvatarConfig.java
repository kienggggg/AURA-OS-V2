package vn.aura.avatar;

import android.content.Context;

/** Stores only the endpoint and the dedicated AURA Avatar pairing token. */
public final class AvatarConfig {
    private static final String PREFS = "aura_avatar";
    private static final String ENDPOINT = "endpoint";
    private static final String TOKEN = "token";
    public static final String DEFAULT_ENDPOINT =
            "http://127.0.0.1:8768/v1/avatar/chat";

    private AvatarConfig() { }

    public static void save(Context context, String endpoint, String token) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(ENDPOINT, endpoint == null ? "" : endpoint.trim())
                .putString(TOKEN, token == null ? "" : token.trim())
                // Pairing is immediately followed by automated restart/testing over ADB.
                // Persist synchronously so Android cannot lose the new Wi-Fi endpoint.
                .commit();
    }

    public static String endpoint(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(ENDPOINT, DEFAULT_ENDPOINT);
    }

    public static String token(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(TOKEN, "");
    }

    public static boolean isReady(Context context) {
        String endpoint = endpoint(context);
        return endpoint != null
                && endpoint.startsWith("http://")
                && endpoint.endsWith("/v1/avatar/chat")
                && !token(context).isEmpty();
    }
}
