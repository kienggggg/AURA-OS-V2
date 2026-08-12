package vn.aura.mbbridge;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/** One-screen setup. AURA can populate it via an explicit ADB intent after pairing. */
public final class MainActivity extends Activity {
    private EditText endpoint;
    private EditText token;
    private TextView status;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        applyIntent(getIntent());
    }

    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyIntent(intent);
    }

    private void buildUi() {
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("AURA MB Bridge");
        title.setTextSize(24);
        root.addView(title);

        TextView detail = new TextView(this);
        detail.setText("Chỉ nghe thông báo MB Bank có tiền vào. Không đọc mật khẩu, OTP, số tài khoản hoặc thông báo ứng dụng khác.");
        detail.setPadding(0, pad / 2, 0, pad / 2);
        root.addView(detail);

        endpoint = new EditText(this);
        endpoint.setHint("AURA endpoint");
        endpoint.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        root.addView(endpoint);

        token = new EditText(this);
        token.setHint("Mã ghép nối AURA");
        token.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(token);

        Button save = new Button(this);
        save.setText("Lưu kết nối AURA");
        save.setOnClickListener(v -> save());
        root.addView(save);

        Button permission = new Button(this);
        permission.setText("Cấp quyền đọc thông báo");
        permission.setOnClickListener(v -> openNotificationAccess());
        root.addView(permission);

        status = new TextView(this);
        status.setGravity(Gravity.CENTER_HORIZONTAL);
        status.setPadding(0, pad, 0, 0);
        root.addView(status);
        setContentView(root);
        refresh();
    }

    private void applyIntent(Intent intent) {
        if (intent == null) return;
        String configuredEndpoint = intent.getStringExtra("aura_endpoint");
        String configuredToken = intent.getStringExtra("aura_token");
        if (configuredEndpoint != null || configuredToken != null) {
            BridgeConfig.save(this,
                    configuredEndpoint != null ? configuredEndpoint : BridgeConfig.endpoint(this),
                    configuredToken != null ? configuredToken : BridgeConfig.token(this));
            Toast.makeText(this, "AURA đã ghép nối. Hãy cấp quyền đọc thông báo.", Toast.LENGTH_LONG).show();
        }
        if (endpoint != null) refresh();
    }

    private void save() {
        BridgeConfig.save(this, endpoint.getText().toString(), token.getText().toString());
        refresh();
        Toast.makeText(this, "Đã lưu kết nối cục bộ.", Toast.LENGTH_SHORT).show();
    }

    private void openNotificationAccess() {
        try {
            startActivity(new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"));
        } catch (Exception ignored) {
            startActivity(new Intent(Settings.ACTION_SETTINGS));
        }
    }

    private void refresh() {
        endpoint.setText(BridgeConfig.endpoint(this));
        token.setText(BridgeConfig.token(this));
        status.setText(BridgeConfig.isReady(this)
                ? "Đã ghép AURA. Bước còn lại: bật quyền đọc thông báo cho AURA MB Bridge."
                : "Chờ AURA ghép nối qua cáp/ADB hoặc nhập endpoint + mã ghép nối.");
    }
}
