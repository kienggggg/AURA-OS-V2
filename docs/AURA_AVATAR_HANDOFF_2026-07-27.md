# AURA Avatar — handoff 2026-07-27

## Device ownership

| Device | Role | Android package |
|---|---|---|
| vivo 1904, Android 11 | Robot head: screen, microphone, speaker, camera | `vn.aura.avatar` |
| Poco X3 | MBBank notification source | `vn.aura.mbbridge` |

Do not merge these apps, pairing files, endpoints or permissions.

## Implemented files

- `core/aura_avatar_pairing.py`
- `core/aura_avatar_relay.py`
- `core/aura_avatar_bridge.py`
- `core/orchestrator.py` — `process_avatar_message()`
- `interface/server.py` — local WebSocket message type `avatar_chat`
- `core/config.py` and `main.py` — optional Avatar relay startup
- `android/aura-avatar/` — standalone Android project
- `tests/test_aura_avatar.py`

Runtime configuration is in `.env`:

```text
AURA_AVATAR_LAN_ENABLED=true
AURA_AVATAR_LAN_HOST=dual
AURA_AVATAR_LAN_PORT=8768
```

`dual` binds the same token-protected conversation relay to localhost and the
active private IPv4 address. The installed Vivo endpoint is currently:

```text
http://192.168.50.102:8768/v1/avatar/chat
```

The address is not a durable identity. Add DHCP reservation or a discovery
mechanism before the robot is treated as unattended.

## Safety boundary

The LAN relay accepts only:

```json
{
  "device_id": "vivo_<android-id>",
  "request_id": "<uuid>",
  "text": "<1..500 chars>"
}
```

It requires `X-AURA-Avatar-Token`, rate-limits each device, and caches request
IDs to prevent repeat processing. It forwards only the `avatar_chat` message
type to AURA's localhost WebSocket.

`process_avatar_message()` is intentionally separate from `process_message()`.
It does not inspect or mutate pending approvals, pending control operations,
profile updates or council decisions. It cannot plan or dispatch tools. The
reply is capped and suited to TTS.

Do not add motor commands to this endpoint. ESP32 control needs a separate,
typed safety gateway with sequence number, TTL, speed clamp, heartbeat timeout
and an ESP32-local emergency stop.

## Android stage 1

The Vivo app currently provides:

- editable endpoint plus a password-masked pairing token;
- typed questions;
- direct `SpeechRecognizer` input in Vietnamese;
- Android Vietnamese `TextToSpeech`;
- camera-app smoke test with an on-device thumbnail only;
- screen-on/show-on-lock-screen behavior for robot-face use;
- synchronous pairing persistence so automated ADB restarts cannot lose the
  Wi-Fi endpoint.

`com.google.android.googlequicksearchbox` had been disabled during an earlier
RAM-cleaning pass. It was re-enabled because it provides
`GoogleRecognitionService`. `RECORD_AUDIO` is granted to `vn.aura.avatar`.
Disabling the Google app again will disable the current voice-input path.

## Verification completed

- `12 passed`:
  `tests/test_aura_avatar.py`, `tests/test_android_mb_bridge.py`,
  `tests/test_android_mb_lan_relay.py`.
- Android Gradle build succeeded with compile/target SDK 35, min SDK 26.
- Installed APK: `android/aura-avatar/app/build/outputs/apk/debug/app-debug.apk`.
- Local relay health: `conversation_only`.
- Local end-to-end reply: `Tôi đang nghe từ Vivo.`
- Vivo-to-laptop TCP over Wi-Fi: open.
- Vivo chat over Wi-Fi after removing `adb reverse tcp:8768`: successful.
- Final UI state: `avatar_status_answered`.
- Camera activity launch: successful.
- Direct microphone recognition pipeline: successful.

`adb reverse --list` retained only `tcp:8766`, which belongs to the old MB
Bridge. The Avatar acceptance test did not use a USB reverse.

## Known limitations / next stage

1. There is no foreground service, boot receiver or reconnect watchdog yet.
2. Camera is only a smoke test; no continuous capture, MediaPipe, object
   detection, privacy filter or selective upload exists.
3. Voice recognition depends on Google's service and may depend on network.
4. No BLE transport or ESP32 firmware exists.
5. No motion-safety protocol exists.
6. The old MB Bridge remains installed on Vivo from an earlier device-role
   misunderstanding. Leave it untouched until the Poco X3 bridge is confirmed,
   then remove it from Vivo deliberately.

Recommended next order:

1. Add a foreground Avatar service with visible notification, reconnect
   backoff and boot restore.
2. Add low-rate camera analysis locally; send structured detections by default,
   thumbnails only on demand, and retain no images by default.
3. Define and test the ESP32 BLE GATT safety protocol before buying or driving
   motors.
4. Add a two-hour heat, battery and Wi-Fi stability soak test.
