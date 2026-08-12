package vn.aura.avatar;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

/**
 * A deliberately narrow BLE bridge to the ESP32 safety controller.  It cannot
 * execute arbitrary AURA tools; it only sends the rover's tiny command set.
 */
final class RoverBleController {
    interface Listener {
        void onRoverState(String state, boolean ready);
        void onRoverTelemetry(String message);
    }

    private static final String ROVER_NAME = "AURA-ROVER";
    private static final UUID SERVICE_UUID = UUID.fromString(
            "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
    );
    private static final UUID COMMAND_UUID = UUID.fromString(
            "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
    );
    private static final UUID TELEMETRY_UUID = UUID.fromString(
            "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
    );
    private static final UUID CLIENT_CONFIG_UUID = UUID.fromString(
            "00002902-0000-1000-8000-00805f9b34fb"
    );

    private final Context context;
    private final Listener listener;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic commandCharacteristic;
    private boolean scanning;
    private boolean ready;

    RoverBleController(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }

    boolean isReady() {
        return ready;
    }

    @SuppressLint("MissingPermission")
    void scanAndConnect() {
        stopScan();
        closeGatt();
        BluetoothManager manager = (BluetoothManager)
                context.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
        if (adapter == null) {
            publishState("Vivo không có Bluetooth.", false);
            return;
        }
        if (!adapter.isEnabled()) {
            publishState("Hãy bật Bluetooth trên Vivo rồi chạm Kết nối lại.", false);
            return;
        }
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) {
            publishState("Chưa mở được bộ quét Bluetooth.", false);
            return;
        }
        scanning = true;
        publishState("Đang tìm AURA-ROVER…", false);
        scanner.startScan(scanCallback);
        mainHandler.postDelayed(scanTimeout, 12000);
    }

    @SuppressLint("MissingPermission")
    private void stopScan() {
        mainHandler.removeCallbacks(scanTimeout);
        if (scanning && scanner != null) {
            try {
                scanner.stopScan(scanCallback);
            } catch (Exception ignored) {
                // Permission state can change while the settings screen is open.
            }
        }
        scanning = false;
    }

    private final Runnable scanTimeout = () -> {
        if (!scanning) return;
        stopScan();
        publishState("Không thấy ESP32. Kiểm tra nguồn và đèn bo mạch.", false);
    };

    private final ScanCallback scanCallback = new ScanCallback() {
        @SuppressLint("MissingPermission")
        @Override public void onScanResult(int callbackType, ScanResult result) {
            String name = result.getScanRecord() == null
                    ? null : result.getScanRecord().getDeviceName();
            if (name == null) name = result.getDevice().getName();
            if (!ROVER_NAME.equals(name)) return;
            stopScan();
            publishState("Đã thấy ESP32, đang ghép điều khiển…", false);
            gatt = result.getDevice().connectGatt(
                    context, false, gattCallback, android.bluetooth.BluetoothDevice.TRANSPORT_LE
            );
        }

        @Override public void onScanFailed(int errorCode) {
            scanning = false;
            publishState("Quét Bluetooth lỗi " + errorCode + ".", false);
        }
    };

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        @Override public void onConnectionStateChange(
                BluetoothGatt activeGatt, int status, int newState
        ) {
            if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
                publishState("Đã nối ESP32, đang kiểm tra kênh an toàn…", false);
                activeGatt.discoverServices();
                return;
            }
            ready = false;
            commandCharacteristic = null;
            publishState("Robot đã ngắt kết nối — bánh xe đã được lệnh dừng.", false);
            try {
                activeGatt.close();
            } catch (Exception ignored) {
            }
        }

        @SuppressLint("MissingPermission")
        @Override public void onServicesDiscovered(BluetoothGatt activeGatt, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                publishState("ESP32 không trả danh sách dịch vụ.", false);
                return;
            }
            BluetoothGattService service = activeGatt.getService(SERVICE_UUID);
            if (service == null) {
                publishState("ESP32 chưa chạy đúng firmware AURA Rover.", false);
                return;
            }
            commandCharacteristic = service.getCharacteristic(COMMAND_UUID);
            BluetoothGattCharacteristic telemetryCharacteristic =
                    service.getCharacteristic(TELEMETRY_UUID);
            if (commandCharacteristic == null || telemetryCharacteristic == null) {
                commandCharacteristic = null;
                publishState("Firmware thiếu kênh lệnh hoặc trạng thái.", false);
                return;
            }
            activeGatt.setCharacteristicNotification(telemetryCharacteristic, true);
            BluetoothGattDescriptor descriptor =
                    telemetryCharacteristic.getDescriptor(CLIENT_CONFIG_UUID);
            if (descriptor != null) {
                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                activeGatt.writeDescriptor(descriptor);
            }
            ready = true;
            publishState("Robot sẵn sàng • giữ nút để chạy", true);
            send("S");
        }

        @Override public void onCharacteristicChanged(
                BluetoothGatt activeGatt, BluetoothGattCharacteristic characteristic
        ) {
            publishTelemetry(new String(
                    characteristic.getValue(), StandardCharsets.UTF_8
            ));
        }
    };

    @SuppressLint("MissingPermission")
    boolean send(String command) {
        BluetoothGattCharacteristic characteristic = commandCharacteristic;
        BluetoothGatt activeGatt = gatt;
        if (!ready || activeGatt == null || characteristic == null) return false;
        characteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
        characteristic.setValue(command.toUpperCase(Locale.ROOT).getBytes(StandardCharsets.UTF_8));
        return activeGatt.writeCharacteristic(characteristic);
    }

    @SuppressLint("MissingPermission")
    void stopAndDisconnect() {
        if (ready) send("S");
        stopScan();
        closeGatt();
        publishState("Robot chưa kết nối.", false);
    }

    @SuppressLint("MissingPermission")
    private void closeGatt() {
        ready = false;
        commandCharacteristic = null;
        BluetoothGatt activeGatt = gatt;
        gatt = null;
        if (activeGatt == null) return;
        try {
            activeGatt.disconnect();
            activeGatt.close();
        } catch (Exception ignored) {
        }
    }

    private void publishState(String state, boolean isReady) {
        ready = isReady;
        mainHandler.post(() -> listener.onRoverState(state, isReady));
    }

    private void publishTelemetry(String message) {
        mainHandler.post(() -> listener.onRoverTelemetry(message));
    }
}
