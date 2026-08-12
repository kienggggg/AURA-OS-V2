# AURA Avatar for Vivo

This is the robot-phone app, package `vn.aura.avatar`. It is independent from
`vn.aura.mbbridge`, the MBBank notification app intended for the Poco X3.

Stage 1 provides:

- typed or Android speech-recognition input;
- conversation-only access to the AURA brain;
- Vietnamese Android text-to-speech output;
- an on-device camera smoke test;
- USB pairing through `adb reverse` on port 8768.
- dual localhost + private-Wi-Fi listening, so the same Vivo can continue over
  the LAN after USB is removed once its endpoint is switched to the laptop IP.

Stage 2 adds a deliberately narrow BLE panel for `AURA-ROVER`: press-and-hold
manual drive, hard stop, distance telemetry, and supervised auto patrol. The
ESP32 owns the motion watchdog and obstacle stop. The conversation relay still
cannot call arbitrary motor actions and still has no financial access, tool
execution, approval handling, background camera capture or continuous recording.

Explicit phrases addressed to `AURA` or `robot` are also recognized locally:
`tiến`, `lùi`, `trái`, `phải`, `dừng`, `kết nối`, and `tự tuần tra`. Short
movement phrases run as bounded bursts, while the original sentence still goes
to the laptop brain so AURA can observe the instruction.
