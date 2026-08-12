package vn.aura.avatar;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.provider.Settings;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Vivo shell for AURA: typed/voice chat, Vietnamese TTS, a local camera check,
 * and a narrow BLE control surface for the ESP32 safety controller.
 */
public final class MainActivity extends Activity implements TextToSpeech.OnInitListener {
    private static final int REQUEST_CAMERA = 4102;
    private static final int REQUEST_MIC_PERMISSION = 4103;
    private static final int REQUEST_ROVER_PERMISSION = 4104;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText endpoint;
    private EditText token;
    private EditText prompt;
    private TextView status;
    private TextView transcript;
    private ImageView cameraPreview;
    private TextView roverStatus;
    private TextView roverTelemetry;
    private Button roverAuto;
    private TextToSpeech tts;
    private SpeechRecognizer speechRecognizer;
    private RoverBleController rover;
    private boolean ttsReady = false;
    private boolean roverAutoMode = false;
    private String roverKeepAliveCommand;
    private final Handler roverHandler = new Handler(Looper.getMainLooper());
    private final Runnable roverHeartbeat = new Runnable() {
        @Override public void run() {
            if (roverKeepAliveCommand == null || rover == null || !rover.isReady()) return;
            rover.send(roverKeepAliveCommand);
            roverHandler.postDelayed(this, 320);
        }
    };

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                        | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                        | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        );
        rover = new RoverBleController(this, new RoverBleController.Listener() {
            @Override public void onRoverState(String state, boolean ready) {
                if (roverStatus != null) roverStatus.setText(state);
                if (!ready) clearRoverHeartbeat();
            }

            @Override public void onRoverTelemetry(String message) {
                if (roverTelemetry != null) {
                    roverTelemetry.setText(humanizeTelemetry(message));
                }
            }
        });
        buildUi();
        tts = new TextToSpeech(this, this);
        applyIntent(getIntent());
    }

    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyIntent(intent);
    }

    @Override public void onInit(int result) {
        if (result == TextToSpeech.SUCCESS) {
            int language = tts.setLanguage(new Locale("vi", "VN"));
            tts.setSpeechRate(0.95f);
            ttsReady = language != TextToSpeech.LANG_MISSING_DATA
                    && language != TextToSpeech.LANG_NOT_SUPPORTED;
        }
        runOnUiThread(() -> {
            CharSequence marker = status == null ? "" : status.getContentDescription();
            if (!"avatar_status_thinking".contentEquals(marker)
                    && !"avatar_status_answered".contentEquals(marker)
                    && !"avatar_status_error".contentEquals(marker)) {
                refreshStatus();
            }
        });
    }

    private void buildUi() {
        int pad = (int) (18 * getResources().getDisplayMetrics().density);
        int small = pad / 2;

        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root);

        TextView face = new TextView(this);
        face.setText("◉  AURA  ◉");
        face.setTextSize(30);
        face.setGravity(Gravity.CENTER);
        face.setPadding(0, pad, 0, small);
        root.addView(face);

        TextView detail = new TextView(this);
        detail.setText(
                "Phân thân Vivo — nghe, nói, nhìn và điều khiển thân robot. "
                + "Bộ não ở laptop; phản xạ dừng nằm trong ESP32."
        );
        detail.setGravity(Gravity.CENTER);
        detail.setPadding(0, 0, 0, pad);
        root.addView(detail);

        endpoint = new EditText(this);
        endpoint.setHint("Địa chỉ AURA");
        endpoint.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        root.addView(endpoint);

        token = new EditText(this);
        token.setHint("Mã ghép nối riêng");
        token.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
        );
        root.addView(token);

        Button save = new Button(this);
        save.setText("Lưu kết nối");
        save.setOnClickListener(v -> {
            AvatarConfig.save(
                    this, endpoint.getText().toString(), token.getText().toString()
            );
            refreshStatus();
            Toast.makeText(this, "Đã lưu kết nối AURA Avatar.", Toast.LENGTH_SHORT).show();
        });
        root.addView(save);

        prompt = new EditText(this);
        prompt.setHint("Nói hoặc nhập điều muốn hỏi AURA");
        prompt.setMinLines(2);
        prompt.setMaxLines(5);
        root.addView(prompt);

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);

        Button listen = new Button(this);
        listen.setText("🎤 Nói");
        listen.setOnClickListener(v -> startSpeech());
        actions.addView(listen, new LinearLayout.LayoutParams(0, -2, 1f));

        Button ask = new Button(this);
        ask.setText("Gửi AURA");
        ask.setOnClickListener(v -> askAura(prompt.getText().toString()));
        actions.addView(ask, new LinearLayout.LayoutParams(0, -2, 1f));
        root.addView(actions);

        Button camera = new Button(this);
        camera.setText("📷 Thử camera — ảnh chỉ nằm trên máy");
        camera.setOnClickListener(v -> startCameraCheck());
        root.addView(camera);

        cameraPreview = new ImageView(this);
        cameraPreview.setAdjustViewBounds(true);
        cameraPreview.setMaxHeight((int) (220 * getResources().getDisplayMetrics().density));
        cameraPreview.setVisibility(View.GONE);
        root.addView(cameraPreview);

        buildRoverUi(root, pad, small);

        status = new TextView(this);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, pad, 0, small);
        root.addView(status);

        transcript = new TextView(this);
        transcript.setText("AURA đang chờ câu đầu tiên.");
        transcript.setTextSize(18);
        transcript.setPadding(small, small, small, pad);
        root.addView(transcript);

        setContentView(scroll);
        refresh();
    }

    private void buildRoverUi(LinearLayout root, int pad, int small) {
        TextView heading = new TextView(this);
        heading.setText("ROBOT AURA");
        heading.setTextSize(22);
        heading.setGravity(Gravity.CENTER);
        heading.setPadding(0, pad, 0, small);
        root.addView(heading);

        Button connect = new Button(this);
        connect.setText("Bluetooth: kết nối ESP32");
        connect.setOnClickListener(v -> connectRover());
        root.addView(connect);

        roverStatus = new TextView(this);
        roverStatus.setText("Robot chưa kết nối.");
        roverStatus.setGravity(Gravity.CENTER);
        roverStatus.setPadding(0, small, 0, small);
        root.addView(roverStatus);

        Button forward = createDriveButton("▲  TIẾN", "F:145");
        root.addView(forward);

        LinearLayout turnRow = new LinearLayout(this);
        turnRow.setOrientation(LinearLayout.HORIZONTAL);
        turnRow.addView(
                createDriveButton("◀  TRÁI", "L:135"),
                new LinearLayout.LayoutParams(0, -2, 1f)
        );
        Button stop = new Button(this);
        stop.setText("■  DỪNG");
        stop.setOnClickListener(v -> stopRover());
        turnRow.addView(stop, new LinearLayout.LayoutParams(0, -2, 1f));
        turnRow.addView(
                createDriveButton("PHẢI  ▶", "R:135"),
                new LinearLayout.LayoutParams(0, -2, 1f)
        );
        root.addView(turnRow);

        LinearLayout lowerRow = new LinearLayout(this);
        lowerRow.setOrientation(LinearLayout.HORIZONTAL);
        lowerRow.addView(
                createDriveButton("▼  LÙI", "B:125"),
                new LinearLayout.LayoutParams(0, -2, 1f)
        );
        roverAuto = new Button(this);
        roverAuto.setText("TỰ TUẦN TRA");
        roverAuto.setOnClickListener(v -> toggleAutoRover());
        lowerRow.addView(roverAuto, new LinearLayout.LayoutParams(0, -2, 1f));
        root.addView(lowerRow);

        TextView instruction = new TextView(this);
        instruction.setText(
                "Giữ nút để chạy, thả tay là dừng. Lần thử đầu phải nhấc bánh khỏi mặt bàn."
        );
        instruction.setGravity(Gravity.CENTER);
        instruction.setPadding(small, small, small, small);
        root.addView(instruction);

        roverTelemetry = new TextView(this);
        roverTelemetry.setText("Khoảng cách: chưa có • Trạng thái: dừng");
        roverTelemetry.setGravity(Gravity.CENTER);
        roverTelemetry.setPadding(0, small, 0, pad);
        root.addView(roverTelemetry);
    }

    private Button createDriveButton(String label, String command) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(v -> { });
        button.setOnTouchListener((view, event) -> {
            if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                startRoverMotion(command);
                return true;
            }
            if (event.getActionMasked() == MotionEvent.ACTION_UP
                    || event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
                view.performClick();
                stopRover();
                return true;
            }
            return false;
        });
        return button;
    }

    private void connectRover() {
        if (!hasRoverPermissions()) {
            requestRoverPermissions();
            return;
        }
        stopRover();
        rover.scanAndConnect();
    }

    private boolean hasRoverPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN)
                    == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)
                    == PackageManager.PERMISSION_GRANTED;
        }
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void requestRoverPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            requestPermissions(
                    new String[]{
                            Manifest.permission.BLUETOOTH_SCAN,
                            Manifest.permission.BLUETOOTH_CONNECT
                    },
                    REQUEST_ROVER_PERMISSION
            );
        } else {
            requestPermissions(
                    new String[]{Manifest.permission.ACCESS_FINE_LOCATION},
                    REQUEST_ROVER_PERMISSION
            );
        }
    }

    private void startRoverMotion(String command) {
        if (rover == null || !rover.isReady()) {
            roverStatus.setText("Hãy kết nối ESP32 trước.");
            return;
        }
        roverAutoMode = false;
        roverAuto.setText("TỰ TUẦN TRA");
        roverKeepAliveCommand = command;
        roverHandler.removeCallbacks(roverHeartbeat);
        rover.send(command);
        roverHandler.postDelayed(roverHeartbeat, 320);
    }

    private void toggleAutoRover() {
        if (rover == null || !rover.isReady()) {
            roverStatus.setText("Hãy kết nối ESP32 trước.");
            return;
        }
        if (roverAutoMode) {
            stopRover();
            return;
        }
        roverAutoMode = true;
        roverAuto.setText("DỪNG TUẦN TRA");
        roverKeepAliveCommand = "PING";
        roverHandler.removeCallbacks(roverHeartbeat);
        rover.send("AUTO:1");
        roverHandler.postDelayed(roverHeartbeat, 320);
    }

    private void clearRoverHeartbeat() {
        roverHandler.removeCallbacks(roverHeartbeat);
        roverKeepAliveCommand = null;
        roverAutoMode = false;
        if (roverAuto != null) roverAuto.setText("TỰ TUẦN TRA");
    }

    private void stopRover() {
        clearRoverHeartbeat();
        if (rover != null && rover.isReady()) rover.send("S");
    }

    private static String humanizeTelemetry(String raw) {
        if (raw == null || raw.trim().isEmpty()) return "Robot chưa gửi trạng thái.";
        if (!raw.startsWith("DIST:")) return raw.replace('_', ' ');
        String distance = "chưa có";
        String state = "dừng";
        String auto = "tắt";
        for (String field : raw.split(";")) {
            if (field.startsWith("DIST:")) {
                String value = field.substring(5);
                distance = "NA".equals(value) ? "chưa có" : value + " mm";
            } else if (field.startsWith("MOTION:")) {
                state = field.substring(7).toLowerCase(Locale.ROOT).replace('_', ' ');
            } else if (field.startsWith("AUTO:")) {
                auto = field.endsWith("1") ? "bật" : "tắt";
            }
        }
        return "Khoảng cách: " + distance + " • Chuyển động: " + state
                + " • Tự chạy: " + auto;
    }

    private void applyIntent(Intent intent) {
        if (intent == null) return;
        String configuredEndpoint = intent.getStringExtra("aura_endpoint");
        String configuredToken = intent.getStringExtra("aura_token");
        String testPrompt = intent.getStringExtra("aura_test_prompt");
        if (configuredEndpoint != null || configuredToken != null) {
            AvatarConfig.save(
                    this,
                    configuredEndpoint != null
                            ? configuredEndpoint : AvatarConfig.endpoint(this),
                    configuredToken != null ? configuredToken : AvatarConfig.token(this)
            );
            Toast.makeText(
                    this, "Vivo đã ghép với AURA Avatar.", Toast.LENGTH_LONG
            ).show();
        }
        if (endpoint != null) refresh();
        // ADB-only smoke-test hook. It can ask a conversation-only question but cannot
        // expose the pairing token or reach approvals/tools.
        if (testPrompt != null && prompt != null && !testPrompt.trim().isEmpty()) {
            prompt.setText(testPrompt.trim());
            prompt.post(() -> askAura(testPrompt.trim()));
        }
    }

    private void refresh() {
        endpoint.setText(AvatarConfig.endpoint(this));
        token.setText(AvatarConfig.token(this));
        refreshStatus();
    }

    private void refreshStatus() {
        if (status == null) return;
        String connection = AvatarConfig.isReady(this)
                ? "Đã ghép nối"
                : "Chưa có kết nối";
        String voice = ttsReady ? "loa tiếng Việt sẵn sàng" : "đang kiểm tra loa";
        status.setText(connection + " • " + voice);
        status.setContentDescription(
                AvatarConfig.isReady(this) ? "avatar_status_ready" : "avatar_status_unpaired"
        );
    }

    private void startSpeech() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.RECORD_AUDIO},
                    REQUEST_MIC_PERMISSION
            );
            return;
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            status.setText("Máy chưa có dịch vụ nhận giọng nói. Vẫn có thể nhập chữ.");
            status.setContentDescription("avatar_status_voice_unavailable");
            return;
        }
        if (speechRecognizer == null) {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this);
            speechRecognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) {
                    status.setText("AURA đang nghe…");
                    status.setContentDescription("avatar_status_listening");
                }

                @Override public void onBeginningOfSpeech() { }
                @Override public void onRmsChanged(float rmsdB) { }
                @Override public void onBufferReceived(byte[] buffer) { }
                @Override public void onEndOfSpeech() {
                    status.setText("AURA đang nhận dạng câu nói…");
                    status.setContentDescription("avatar_status_recognizing");
                }

                @Override public void onError(int error) {
                    status.setText("Tôi chưa nghe rõ. Hãy chạm Nói và thử lại.");
                    status.setContentDescription("avatar_status_voice_error");
                }

                @Override public void onResults(Bundle results) {
                    ArrayList<String> heard =
                            results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (heard != null && !heard.isEmpty()) {
                        String text = heard.get(0);
                        prompt.setText(text);
                        askAura(text);
                    } else {
                        onError(SpeechRecognizer.ERROR_NO_MATCH);
                    }
                }

                @Override public void onPartialResults(Bundle partialResults) { }
                @Override public void onEvent(int eventType, Bundle params) { }
            });
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
        );
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "vi-VN");
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false);
        speechRecognizer.startListening(intent);
        status.setText("Đang mở micro…");
        status.setContentDescription("avatar_status_listening");
    }

    private void startCameraCheck() {
        try {
            startActivityForResult(
                    new Intent(MediaStore.ACTION_IMAGE_CAPTURE), REQUEST_CAMERA
            );
        } catch (Exception exception) {
            status.setText("Không mở được camera.");
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_CAMERA && resultCode == RESULT_OK && data != null) {
            Object image = data.getExtras() == null ? null : data.getExtras().get("data");
            if (image instanceof Bitmap) {
                cameraPreview.setImageBitmap((Bitmap) image);
                cameraPreview.setVisibility(View.VISIBLE);
                status.setText("Camera Vivo hoạt động. Ảnh thử không gửi ra ngoài.");
            }
        }
    }

    @Override public void onRequestPermissionsResult(
            int requestCode, String[] permissions, int[] grantResults
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_MIC_PERMISSION) {
            if (grantResults.length > 0
                    && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startSpeech();
            } else {
                status.setText("Chưa có quyền micro. AURA vẫn nhận câu nhập bằng chữ.");
                status.setContentDescription("avatar_status_mic_denied");
            }
            return;
        }
        if (requestCode == REQUEST_ROVER_PERMISSION) {
            if (hasRoverPermissions()) {
                rover.scanAndConnect();
            } else {
                roverStatus.setText("Chưa có quyền Bluetooth nên chưa điều khiển robot.");
            }
        }
    }

    private void askAura(String rawText) {
        String text = rawText == null ? "" : rawText.trim();
        if (text.isEmpty()) {
            status.setText("Hãy nói hoặc nhập một câu.");
            status.setContentDescription("avatar_status_empty");
            return;
        }
        // Explicitly addressed motion phrases act locally without waiting for
        // network latency.  The question still continues to the brain below so
        // AURA can observe and remember what its body was asked to do.
        maybeHandleRoverCommand(text);
        AvatarConfig.save(
                this, endpoint.getText().toString(), token.getText().toString()
        );
        if (!AvatarConfig.isReady(this)) {
            status.setText("Chưa ghép nối AURA.");
            status.setContentDescription("avatar_status_unpaired");
            return;
        }
        status.setText("AURA đang suy nghĩ…");
        status.setContentDescription("avatar_status_thinking");
        transcript.setText("Bạn: " + text);
        executor.execute(() -> {
            try {
                String response = postQuestion(text);
                runOnUiThread(() -> {
                    transcript.setText("Bạn: " + text + "\n\nAURA: " + response);
                    status.setText("AURA đã trả lời.");
                    status.setContentDescription("avatar_status_answered");
                    speak(response);
                });
            } catch (Exception exception) {
                runOnUiThread(() -> {
                    status.setText("Chưa nối được bộ não AURA: " + safeMessage(exception));
                    status.setContentDescription("avatar_status_error");
                });
            }
        });
    }

    private void maybeHandleRoverCommand(String original) {
        String normalized = Normalizer.normalize(
                original.toLowerCase(Locale.ROOT), Normalizer.Form.NFD
        ).replaceAll("\\p{M}+", "");
        if (!normalized.contains("robot") && !normalized.startsWith("aura")) return;

        if (normalized.contains("dung") || normalized.contains("stop")) {
            stopRover();
            roverStatus.setText("AURA đã nhận lệnh giọng nói: dừng.");
            return;
        }
        if (normalized.contains("ket noi")) {
            connectRover();
            return;
        }
        if (normalized.contains("tu tuan tra") || normalized.contains("tu chay")) {
            if (!roverAutoMode) toggleAutoRover();
            return;
        }
        if (normalized.contains("tien")) {
            startRoverBurst("F:135", 850, "tiến");
        } else if (normalized.contains("lui")) {
            startRoverBurst("B:115", 700, "lùi");
        } else if (normalized.contains("trai")) {
            startRoverBurst("L:125", 480, "rẽ trái");
        } else if (normalized.contains("phai")) {
            startRoverBurst("R:125", 480, "rẽ phải");
        }
    }

    private void startRoverBurst(String command, long durationMs, String label) {
        if (rover == null || !rover.isReady()) {
            roverStatus.setText("Đã nghe lệnh " + label + ", nhưng ESP32 chưa kết nối.");
            return;
        }
        startRoverMotion(command);
        final String expected = command;
        roverStatus.setText("AURA đã nhận lệnh giọng nói: " + label + ".");
        roverHandler.postDelayed(() -> {
            if (expected.equals(roverKeepAliveCommand)) stopRover();
        }, durationMs);
    }

    private String postQuestion(String text) throws Exception {
        URL url = new URL(AvatarConfig.endpoint(this));
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(120000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty(
                "X-AURA-Avatar-Token", AvatarConfig.token(this)
        );

        String androidId = Settings.Secure.getString(
                getContentResolver(), Settings.Secure.ANDROID_ID
        );
        if (androidId == null || androidId.isEmpty()) androidId = "unknown";
        JSONObject request = new JSONObject();
        request.put("device_id", "vivo_" + androidId.replaceAll("[^A-Za-z0-9._-]", ""));
        request.put("request_id", UUID.randomUUID().toString());
        request.put("text", text);
        byte[] body = request.toString().getBytes(StandardCharsets.UTF_8);
        connection.getOutputStream().write(body);

        int statusCode = connection.getResponseCode();
        InputStream input = statusCode >= 200 && statusCode < 300
                ? connection.getInputStream() : connection.getErrorStream();
        String responseBody = readAll(input);
        connection.disconnect();
        JSONObject response = new JSONObject(responseBody);
        if (statusCode < 200 || statusCode >= 300) {
            throw new IllegalStateException(
                    response.optString("error", "HTTP " + statusCode)
            );
        }
        return response.optString("response", "AURA chưa có câu trả lời.");
    }

    private static String readAll(InputStream input) throws Exception {
        if (input == null) return "{}";
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8)
        );
        StringBuilder builder = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) builder.append(line);
        reader.close();
        return builder.toString();
    }

    private static String safeMessage(Exception exception) {
        String message = exception.getMessage();
        if (message == null || message.trim().isEmpty()) return "lỗi kết nối";
        return message.length() > 120 ? message.substring(0, 120) : message;
    }

    private void speak(String text) {
        if (!ttsReady || tts == null) return;
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "aura-avatar-reply");
    }

    @Override protected void onStop() {
        // A hidden controller must never leave the wheels running.
        stopRover();
        super.onStop();
    }

    @Override protected void onDestroy() {
        stopRover();
        if (rover != null) rover.stopAndDisconnect();
        executor.shutdownNow();
        if (speechRecognizer != null) {
            speechRecognizer.cancel();
            speechRecognizer.destroy();
        }
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        super.onDestroy();
    }
}
