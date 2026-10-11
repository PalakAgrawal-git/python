/*
 * ============================================================================
 *  Heatwave Sensor Station  -  Arduino Uno
 *  "Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning"
 * ============================================================================
 *  What it does
 *    - Reads temperature + humidity every 2 seconds
 *    - Shows temperature, humidity and alert level on a 16x2 LCD
 *    - Lights a green / yellow / red LED for Normal / Heat Wave / Severe
 *    - Beeps a piezo buzzer ONLY on a Severe Heat Wave
 *    - A push button (hardware interrupt on D2) silences the buzzer
 *    - Prints one CSV line per reading to the Serial Monitor:
 *          millis,temperature,humidity        e.g.  12000,41.5,32.0
 *
 *  Sensor choice (see USE_DHT22 below)
 *    1 = DHT22 on D7 (real hardware, or if your Tinkercad offers DHT22 + library)
 *    0 = TMP36 on A0 + potentiometer on A1 for humidity. Uses only parts that
 *        every Tinkercad account has, so it is the safe fallback.
 *
 *  Alert rule on the Arduino (simplified IMD criteria, same as the dashboard)
 *    The station does not know the daily maximum, so each reading is compared
 *    with thresholds built from the station type and the local normal maximum:
 *      Heat Wave   : T >= max(station threshold, normal + 4.5)  or  T >= 45
 *      Severe      : T >= max(station threshold, normal + 6.5)  or  T >= 47
 * ============================================================================
 */

#include <LiquidCrystal.h>

// ------------------------- user settings ------------------------------------
#define USE_DHT22        1      // 1 = DHT22 sensor, 0 = TMP36 + potentiometer

// Station type: 40 = plains, 37 = coastal, 30 = hilly (degrees C)
const float STATION_THRESHOLD_C = 40.0;
// Normal (climatological) maximum temperature for your place and month
const float NORMAL_MAX_C        = 39.0;

const unsigned long SAMPLE_INTERVAL_MS = 2000;  // DHT22 cannot be read faster
// ----------------------------------------------------------------------------

#if USE_DHT22
  #include <DHT.h>                // "DHT sensor library" by Adafruit
  #define DHT_PIN   7
  DHT dht(DHT_PIN, DHT22);
#else
  #define TMP36_PIN A0            // TMP36 output
  #define POT_PIN   A1            // potentiometer wiper = fake humidity
#endif

// ------------------------- pin assignments ----------------------------------
const int PIN_MUTE_BTN = 2;       // D2 = INT0, hardware interrupt pin
const int PIN_LED_GREEN  = 3;
const int PIN_LED_YELLOW = 4;
const int PIN_LED_RED    = 5;
const int PIN_BUZZER     = 6;

//                RS  E  D4  D5 D6 D7
LiquidCrystal lcd(12, 11, 10, 9, 8, 13);

// ------------------------- alert levels -------------------------------------
const int LEVEL_NORMAL = 0;
const int LEVEL_HEAT   = 1;
const int LEVEL_SEVERE = 2;

float heatWaveTemp;               // computed once in setup()
float severeTemp;

int currentLevel = LEVEL_NORMAL;
unsigned long lastSampleMs = 0;

// ------------------------- buzzer / interrupt state -------------------------
// 'volatile' because the ISR changes it behind the back of loop()
volatile bool buzzerMuted = false;
volatile unsigned long lastPressMs = 0;

unsigned long lastBeepToggleMs = 0;
bool beepOn = false;

// Interrupt Service Routine: runs the instant the button is pressed.
// Keep it tiny: set a flag and return. Includes a 200 ms debounce.
void onMutePressed() {
  unsigned long now = millis();
  if (now - lastPressMs > 200) {
    buzzerMuted = true;
    lastPressMs = now;
  }
}

// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(9600);             // must match the baud rate in the dashboard

  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_MUTE_BTN, INPUT_PULLUP);          // pressed = LOW, no resistor needed
  attachInterrupt(digitalPinToInterrupt(PIN_MUTE_BTN), onMutePressed, FALLING);

  lcd.begin(16, 2);
  lcd.print("Heatwave Station");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");

#if USE_DHT22
  dht.begin();
#endif

  // Build the two thresholds from the settings above
  heatWaveTemp = min(max(STATION_THRESHOLD_C, NORMAL_MAX_C + 4.5), 45.0);
  severeTemp   = min(max(STATION_THRESHOLD_C, NORMAL_MAX_C + 6.5), 47.0);

  // CSV header. The Python parser skips this line automatically.
  Serial.println("millis,temperature,humidity");
}

// ----------------------------------------------------------------------------
// Read the sensor. Returns false if the reading failed.
bool readSensor(float &tempC, float &hum) {
#if USE_DHT22
  hum   = dht.readHumidity();
  tempC = dht.readTemperature();              // degrees Celsius
  return !(isnan(hum) || isnan(tempC));
#else
  // TMP36: 0.5 V at 0 C, 10 mV per degree C
  float volts = analogRead(TMP36_PIN) * 5.0 / 1024.0;
  tempC = (volts - 0.5) * 100.0;
  hum   = map(analogRead(POT_PIN), 0, 1023, 10, 95);   // 10..95 %
  return true;
#endif
}

int classify(float t) {
  if (t >= severeTemp)   return LEVEL_SEVERE;
  if (t >= heatWaveTemp) return LEVEL_HEAT;
  return LEVEL_NORMAL;
}

// LEDs: exactly one lit
void showLeds(int level) {
  digitalWrite(PIN_LED_GREEN,  level == LEVEL_NORMAL);
  digitalWrite(PIN_LED_YELLOW, level == LEVEL_HEAT);
  digitalWrite(PIN_LED_RED,    level == LEVEL_SEVERE);
}

// LCD:  line 1 "T:41.5C H:32%"   line 2 "Alert: HEATWAVE"
void showLcd(float t, float h, int level) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("T:");  lcd.print(t, 1);
  lcd.print("C H:"); lcd.print((int)(h + 0.5)); lcd.print("%");
  lcd.setCursor(0, 1);
  lcd.print("Alert: ");
  if (level == LEVEL_SEVERE)    lcd.print("SEVERE");
  else if (level == LEVEL_HEAT) lcd.print("HEATWAVE");
  else                          lcd.print("NORMAL");
}

// Non-blocking beeping (250 ms on / 250 ms off) - only on SEVERE and not muted
void updateBuzzer() {
  bool shouldSound = (currentLevel == LEVEL_SEVERE) && !buzzerMuted;
  if (!shouldSound) {
    noTone(PIN_BUZZER);
    beepOn = false;
    return;
  }
  unsigned long now = millis();
  if (now - lastBeepToggleMs >= 250) {
    lastBeepToggleMs = now;
    beepOn = !beepOn;
    if (beepOn) tone(PIN_BUZZER, 2000);
    else        noTone(PIN_BUZZER);
  }
}

// ----------------------------------------------------------------------------
void loop() {
  unsigned long now = millis();

  // Sample every SAMPLE_INTERVAL_MS without blocking (no delay()), so the
  // buzzer pattern and the button stay responsive.
  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;

    float t, h;
    if (readSensor(t, h)) {
      currentLevel = classify(t);
      if (currentLevel != LEVEL_SEVERE) {
        buzzerMuted = false;      // re-arm the buzzer for the next severe event
      }
      showLeds(currentLevel);
      showLcd(t, h, currentLevel);

      // One CSV line per reading: millis,temperature,humidity
      Serial.print(now);  Serial.print(',');
      Serial.print(t, 1); Serial.print(',');
      Serial.println(h, 1);
    } else {
      // Failed read: tell the LCD, but print nothing to Serial so the
      // CSV stream stays clean.
      lcd.clear();
      lcd.print("Sensor error");
    }
  }

  updateBuzzer();
}
