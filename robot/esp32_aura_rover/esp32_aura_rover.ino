#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>

// AURA Rover v1: the ESP32 is the safety spine.  It never trusts a remote
// command forever: BLE loss, heartbeat loss, stale sonar, or a close obstacle
// all make the motors stop locally.

namespace Pins {
constexpr uint8_t kAin1 = 25;
constexpr uint8_t kAin2 = 26;
constexpr uint8_t kPwma = 27;
constexpr uint8_t kBin1 = 32;
constexpr uint8_t kBin2 = 33;
constexpr uint8_t kPwmb = 14;
constexpr uint8_t kStandby = 13;
constexpr uint8_t kUs100Rx = 16;  // ESP32 RX -> US-100 Echo/RX
constexpr uint8_t kUs100Tx = 17;  // ESP32 TX -> US-100 Trig/TX
}

namespace BleIds {
// Nordic-UART-compatible UUIDs, used here as a small private command pipe.
constexpr char kService[] = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
constexpr char kCommand[] = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
constexpr char kTelemetry[] = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";
}

constexpr uint16_t kMotorPwmHz = 18000;
constexpr uint8_t kPwmBits = 8;
// Hạ tốc 05/08/2026: ở tốc cũ xe chui gầm tủ trước khi Sếp kịp nhìn/can thiệp.
// Chạy trong nhà thì chậm mới quan sát và nghiệm thu được.
constexpr uint8_t kDefaultSpeed = 120;
constexpr uint8_t kTurnSpeed = 120;
constexpr uint16_t kEmergencyDistanceMm = 150;
constexpr uint16_t kAutoClearDistanceMm = 260;
constexpr uint32_t kHeartbeatTimeoutMs = 1100;
constexpr uint32_t kSonarFreshMs = 650;
constexpr uint32_t kSonarRequestEveryMs = 110;
constexpr uint32_t kSonarReplyTimeoutMs = 90;

// If a wheel runs backward during the lifted-wheel test, change only the
// matching flag, or swap that motor's two AO/BO wires.
constexpr bool kInvertLeftMotor = false;
constexpr bool kInvertRightMotor = true;

// Bù lệch bánh (05/08/2026): hai motor TT không bao giờ khoẻ bằng nhau. Đo thực
// tế trên xe: motor cắm AO (kênh A) khoẻ hơn -> xe lệch. Ghì kênh A lại cho cân.
// 06/08/2026 — ĐỔI BÊN sau khi tháo xe ra lắp lên khung: giờ motor ở BO mới là
// motor khoẻ (Sếp quan sát "bánh BO nhanh hơn rõ rệt so với AO"). Trước đó ghì
// kênh A là ghì nhầm bánh vốn đã yếu -> lệch nặng gấp đôi, xe chạy vòng cung.
// Chỉnh dần: xe còn lệch về phía kênh A thì HẠ tiếp kTrimB (0.82, 0.78...).
constexpr float kTrimA = 1.00f;
constexpr float kTrimB = 0.86f;
// Sàn tốc độ: dưới mức này motor chỉ rít mà không quay, nên đừng ghì quá tay.
constexpr uint8_t kMinMovingDuty = 90;

enum class Motion : uint8_t { kStopped, kForward, kBackward, kLeft, kRight };
enum class AutoPhase : uint8_t { kCruise, kReverse, kTurn };

HardwareSerial sonar(2);
BLEServer* bleServer = nullptr;
BLECharacteristic* telemetry = nullptr;

volatile bool bleConnected = false;
volatile bool restartAdvertising = false;
bool autoMode = false;
bool sonarWaiting = false;
bool distanceValid = false;
bool sonarCrossedWiring = false;
uint16_t distanceMm = 0;
uint8_t sonarMisses = 0;
uint32_t lastCommandAt = 0;
uint32_t lastDistanceAt = 0;
uint32_t sonarRequestAt = 0;
uint32_t nextSonarRequestAt = 0;
uint32_t lastTelemetryAt = 0;
uint32_t autoPhaseAt = 0;
bool turnRightNext = true;
Motion motion = Motion::kStopped;
AutoPhase autoPhase = AutoPhase::kCruise;

constexpr uint8_t kPwmChannelA = 0;
constexpr uint8_t kPwmChannelB = 1;

uint8_t clampSpeed(int value) {
  if (value < 0) return 0;
  if (value > 255) return 255;
  return static_cast<uint8_t>(value);
}

const char* motionName(Motion value) {
  switch (value) {
    case Motion::kForward: return "FORWARD";
    case Motion::kBackward: return "BACKWARD";
    case Motion::kLeft: return "LEFT";
    case Motion::kRight: return "RIGHT";
    default: return "STOPPED";
  }
}

void writePwmA(uint8_t duty) {
  ledcWrite(kPwmChannelA, duty);
}

void writePwmB(uint8_t duty) {
  ledcWrite(kPwmChannelB, duty);
}

void notifyText(const String& text) {
  Serial.println(text);
  if (!bleConnected || telemetry == nullptr) return;
  telemetry->setValue(text.c_str());
  telemetry->notify();
}

void setChannel(uint8_t in1, uint8_t in2, int signedSpeed, bool invert,
                bool channelA) {
  if (invert) signedSpeed = -signedSpeed;
  uint8_t duty = clampSpeed(abs(signedSpeed));
  // Bù lệch bánh. Giữ nguyên số 0 (dừng vẫn là dừng tuyệt đối) và không ghì
  // xuống dưới sàn quay được, kẻo bánh yếu đứng ì làm xe lệch ngược lại.
  if (duty > 0) {
    const int trimmed = static_cast<int>(duty * (channelA ? kTrimA : kTrimB));
    duty = clampSpeed(trimmed < kMinMovingDuty ? min<int>(duty, kMinMovingDuty)
                                               : trimmed);
  }
  if (signedSpeed > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else if (signedSpeed < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
  if (channelA) writePwmA(duty); else writePwmB(duty);
}

void stopMotors(const char* reason, bool announce = true) {
  writePwmA(0);
  writePwmB(0);
  digitalWrite(Pins::kAin1, LOW);
  digitalWrite(Pins::kAin2, LOW);
  digitalWrite(Pins::kBin1, LOW);
  digitalWrite(Pins::kBin2, LOW);
  digitalWrite(Pins::kStandby, LOW);
  const bool changed = motion != Motion::kStopped;
  motion = Motion::kStopped;
  if (announce && (changed || strcmp(reason, "COMMAND") != 0)) {
    notifyText(String("STOP:") + reason);
  }
}

bool sonarFresh() {
  return distanceValid && millis() - lastDistanceAt <= kSonarFreshMs;
}

bool frontClear() {
  return sonarFresh() && distanceMm > kEmergencyDistanceMm;
}

void driveSigned(int left, int right, Motion nextMotion) {
  // A front obstacle blocks forward travel, but the escape state machine must
  // still be allowed to reverse or turn away from it.
  if (nextMotion == Motion::kForward && !frontClear()) {
    stopMotors(sonarFresh() ? "OBSTACLE" : "SONAR_NOT_READY");
    return;
  }
  digitalWrite(Pins::kStandby, HIGH);
  setChannel(Pins::kAin1, Pins::kAin2, left, kInvertLeftMotor, true);
  setChannel(Pins::kBin1, Pins::kBin2, right, kInvertRightMotor, false);
  motion = nextMotion;
}

int commandSpeed(const String& command) {
  const int colon = command.indexOf(':');
  if (colon < 0) return kDefaultSpeed;
  return clampSpeed(command.substring(colon + 1).toInt());
}

void enterAutoMode() {
  if (!sonarFresh()) {
    autoMode = false;
    stopMotors("SONAR_NOT_READY");
    return;
  }
  autoMode = true;
  autoPhase = AutoPhase::kCruise;
  autoPhaseAt = millis();
  notifyText("AUTO:ON");
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();
  lastCommandAt = millis();

  if (command == "PING") return;
  if (command == "S" || command == "STOP" || command == "AUTO:0") {
    autoMode = false;
    stopMotors("COMMAND");
    notifyText("ACK:STOP");
    return;
  }
  if (command == "AUTO:1") {
    enterAutoMode();
    return;
  }

  autoMode = false;
  const int speed = commandSpeed(command);
  if (command.startsWith("F")) {
    driveSigned(speed, speed, Motion::kForward);
  } else if (command.startsWith("B")) {
    driveSigned(-speed, -speed, Motion::kBackward);
  } else if (command.startsWith("L")) {
    driveSigned(-speed, speed, Motion::kLeft);
  } else if (command.startsWith("R")) {
    driveSigned(speed, -speed, Motion::kRight);
  } else {
    stopMotors("BAD_COMMAND");
    notifyText("ERROR:BAD_COMMAND");
    return;
  }
  notifyText(String("ACK:") + motionName(motion));
}

class CommandCallbacks final : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* characteristic) override {
    const String raw(characteristic->getValue().c_str());
    if (raw.length() > 0) handleCommand(raw);
  }
};

class ServerCallbacks final : public BLEServerCallbacks {
  void onConnect(BLEServer*) override {
    bleConnected = true;
    lastCommandAt = millis();
    notifyText("BLE:CONNECTED");
  }

  void onDisconnect(BLEServer*) override {
    bleConnected = false;
    autoMode = false;
    stopMotors("BLE_LOST", false);
    restartAdvertising = true;
  }
};

void startSonarRequest() {
  while (sonar.available()) sonar.read();
  // US-100 UART mode: jumper installed, 9600 baud, request distance with 0x55.
  sonar.write(0x55);
  sonar.flush();
  sonarWaiting = true;
  sonarRequestAt = millis();
}

void beginSonar(bool crossed) {
  sonar.end();
  sonarCrossedWiring = crossed;
  // Official US-100 boards use TX-to-TX/RX-to-RX. Some clones expose the
  // labels from the sensor's viewpoint and therefore need the opposite UART
  // assignment. Try both in firmware so the owner does not swap live wires.
  const uint8_t rxPin = crossed ? Pins::kUs100Tx : Pins::kUs100Rx;
  const uint8_t txPin = crossed ? Pins::kUs100Rx : Pins::kUs100Tx;
  sonar.begin(9600, SERIAL_8N1, rxPin, txPin);
  sonarWaiting = false;
  sonarMisses = 0;
  nextSonarRequestAt = millis() + 120;
}

void pollSonar() {
  const uint32_t now = millis();
  if (!sonarWaiting && now >= nextSonarRequestAt) {
    startSonarRequest();
    return;
  }
  if (!sonarWaiting) return;

  if (sonar.available() >= 2) {
    const uint16_t measured =
        (static_cast<uint16_t>(sonar.read()) << 8) | sonar.read();
    sonarWaiting = false;
    nextSonarRequestAt = now + kSonarRequestEveryMs;
    if (measured >= 20 && measured <= 4500) {
      distanceMm = measured;
      distanceValid = true;
      sonarMisses = 0;
      lastDistanceAt = now;
    } else {
      distanceValid = false;
    }
    return;
  }

  if (now - sonarRequestAt > kSonarReplyTimeoutMs) {
    sonarWaiting = false;
    nextSonarRequestAt = now + kSonarRequestEveryMs;
    ++sonarMisses;
    if (sonarMisses >= 3) distanceValid = false;
    if (sonarMisses >= 8) {
      beginSonar(!sonarCrossedWiring);
      notifyText(sonarCrossedWiring
                     ? "SONAR:TRY_CROSSED"
                     : "SONAR:TRY_DIRECT");
    }
  }
}

void runAutoPilot() {
  if (!autoMode) return;
  const uint32_t now = millis();
  if (!sonarFresh()) {
    autoMode = false;
    stopMotors("SONAR_LOST");
    return;
  }

  switch (autoPhase) {
    case AutoPhase::kCruise:
      if (distanceMm <= kAutoClearDistanceMm) {
        stopMotors("AUTO_OBSTACLE", false);
        driveSigned(-115, -115, Motion::kBackward);
        autoPhase = AutoPhase::kReverse;
        autoPhaseAt = now;
      } else {
        driveSigned(125, 125, Motion::kForward);
      }
      break;
    case AutoPhase::kReverse:
      if (now - autoPhaseAt >= 360) {
        if (turnRightNext) {
          driveSigned(kTurnSpeed, -kTurnSpeed, Motion::kRight);
        } else {
          driveSigned(-kTurnSpeed, kTurnSpeed, Motion::kLeft);
        }
        turnRightNext = !turnRightNext;
        autoPhase = AutoPhase::kTurn;
        autoPhaseAt = now;
      }
      break;
    case AutoPhase::kTurn:
      if (now - autoPhaseAt >= 520) {
        autoPhase = AutoPhase::kCruise;
        autoPhaseAt = now;
      }
      break;
  }
}

void setupMotorPins() {
  pinMode(Pins::kAin1, OUTPUT);
  pinMode(Pins::kAin2, OUTPUT);
  pinMode(Pins::kBin1, OUTPUT);
  pinMode(Pins::kBin2, OUTPUT);
  pinMode(Pins::kStandby, OUTPUT);
  ledcSetup(kPwmChannelA, kMotorPwmHz, kPwmBits);
  ledcSetup(kPwmChannelB, kMotorPwmHz, kPwmBits);
  ledcAttachPin(Pins::kPwma, kPwmChannelA);
  ledcAttachPin(Pins::kPwmb, kPwmChannelB);
  stopMotors("BOOT", false);
}

void setupBle() {
  BLEDevice::init("AURA-ROVER");
  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());
  BLEService* service = bleServer->createService(BleIds::kService);
  BLECharacteristic* command = service->createCharacteristic(
      BleIds::kCommand,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  command->setCallbacks(new CommandCallbacks());
  telemetry = service->createCharacteristic(
      BleIds::kTelemetry,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  telemetry->addDescriptor(new BLE2902());
  telemetry->setValue("BOOTING");
  service->start();

  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(BleIds::kService);
  advertising->setScanResponse(true);
  advertising->start();
}

void setup() {
  Serial.begin(115200);
  setupMotorPins();
  beginSonar(false);
  setupBle();
  notifyText("AURA_ROVER:READY");
}

void loop() {
  const uint32_t now = millis();
  pollSonar();

  if (restartAdvertising) {
    restartAdvertising = false;
    BLEDevice::startAdvertising();
  }

  if (!bleConnected) {
    if (motion != Motion::kStopped) stopMotors("BLE_LOST");
    autoMode = false;
  } else if (now - lastCommandAt > kHeartbeatTimeoutMs) {
    if (motion != Motion::kStopped || autoMode) {
      autoMode = false;
      stopMotors("HEARTBEAT_LOST");
    }
  }

  if (motion == Motion::kForward &&
      (!sonarFresh() || distanceMm <= kEmergencyDistanceMm)) {
    autoMode = false;
    stopMotors(sonarFresh() ? "OBSTACLE" : "SONAR_LOST");
  }

  runAutoPilot();

  if (now - lastTelemetryAt >= 500) {
    lastTelemetryAt = now;
    String message = "DIST:";
    message += sonarFresh() ? String(distanceMm) : String("NA");
    message += ";MOTION:";
    message += motionName(motion);
    message += ";AUTO:";
    message += autoMode ? "1" : "0";
    notifyText(message);
  }
  delay(2);
}
