// AURA Dupont wire continuity tester.
// Safety rule: disconnect USB before inserting or removing the wire.
// Connect exactly one female-female jumper between GPIO25 (D25) and GPIO26 (D26).

constexpr int kDrivePin = 25;
constexpr int kSensePin = 26;
constexpr unsigned long kReportIntervalMs = 500;

bool lastConnected = false;
unsigned long lastReportAt = 0;

void setup() {
  Serial.begin(115200);

  // GPIO25 is held LOW. GPIO26 uses its weak internal pull-up.
  // A sound jumper joins the pins and pulls GPIO26 LOW without creating a
  // high-current path; an open/loose jumper leaves GPIO26 HIGH.
  pinMode(kDrivePin, OUTPUT);
  digitalWrite(kDrivePin, LOW);
  pinMode(kSensePin, INPUT_PULLUP);

  delay(250);
  Serial.println("AURA_WIRE_TESTER:READY");
  Serial.println("POWER_OFF_BEFORE_CHANGING_WIRE");
}

void loop() {
  const bool connected = digitalRead(kSensePin) == LOW;
  const unsigned long now = millis();

  if (connected != lastConnected || now - lastReportAt >= kReportIntervalMs) {
    Serial.println(connected ? "WIRE:GOOD" : "WIRE:OPEN");
    lastConnected = connected;
    lastReportAt = now;
  }

  delay(20);
}
