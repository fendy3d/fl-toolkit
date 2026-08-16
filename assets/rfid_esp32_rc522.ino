/*
 * FL Toolkit — ESP32 + RC522 RFID reader
 * ---------------------------------------
 * Identifies each tapped card and reports it two ways over USB @ 115200 baud:
 *   1. a readable summary block (nice to read in the Arduino Serial Monitor), and
 *   2. one compact JSON line (consumed by the FL Toolkit "RFID Reader" web page,
 *      which renders the full formatted view).
 *
 * Reports: standard, UID, ATQA, SAK, card type. For MIFARE Ultralight / NTAG21x
 * it also runs GET_VERSION (-> exact type, memory, vendor) and reads the first
 * pages to determine NDEF status. No memory/sector dump.
 *
 * WIRING  (RC522  ->  ESP32 dev board)   ⚠ RC522 is 3.3 V — never wire it to 5 V
 *   SDA / SS  -> GPIO 5          SCK   -> GPIO 18
 *   MOSI      -> GPIO 23         MISO  -> GPIO 19
 *   RST       -> GPIO 22         3.3V  -> 3V3        GND -> GND
 *
 * SETUP (Arduino IDE): install "esp32" (Espressif) boards + the "MFRC522" by
 * GithubCommunity library, select "ESP32 Dev Module", upload.
 */

#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN   5
#define RST_PIN  22

MFRC522 mfrc522(SS_PIN, RST_PIN);

void printByteHex(byte b)              { if (b < 0x10) Serial.print('0'); Serial.print(b, HEX); }
void printHex(byte *buf, byte len)     { for (byte i = 0; i < len; i++) printByteHex(buf[i]); }
void printHexColon(byte *buf, byte len){ for (byte i = 0; i < len; i++) { if (i) Serial.print(':'); printByteHex(buf[i]); } }
void printAtqa(word a)                 { printByteHex(a >> 8); printByteHex(a & 0xFF); }

// Ultralight / NTAG GET_VERSION (0x60) -> 8 bytes. Not all UL support it.
bool getVersion(byte *out8) {
  byte cmd[3];
  cmd[0] = 0x60;
  if (mfrc522.PCD_CalculateCRC(cmd, 1, &cmd[1]) != MFRC522::STATUS_OK) return false;
  byte back[12];
  byte backLen = sizeof(back), validBits = 0;
  if (mfrc522.PCD_TransceiveData(cmd, 3, back, &backLen, &validBits, 0, true) != MFRC522::STATUS_OK) return false;
  if (backLen < 8) return false;
  for (byte i = 0; i < 8; i++) out8[i] = back[i];
  return true;
}

// Read the first 8 pages (into 32 bytes) — enough for NDEF status. Returns count.
byte readFirstPages(byte *out32) {
  byte count = 0;
  for (byte p = 0; p < 8; p += 4) {
    byte buf[18];
    byte size = sizeof(buf);
    if (mfrc522.MIFARE_Read(p, buf, &size) != MFRC522::STATUS_OK) break;
    for (byte i = 0; i < 4; i++) { memcpy(out32 + (p + i) * 4, buf + i * 4, 4); count = p + i + 1; }
  }
  return count;
}

void printReadable(word atqa, MFRC522::PICC_Type t, byte *ver, bool haveVer) {
  Serial.println();
  Serial.println(F("============ Card ============"));
  Serial.println(F("Standard : ISO14443 Type A"));
  Serial.print  (F("UID      : ")); printHexColon(mfrc522.uid.uidByte, mfrc522.uid.size); Serial.println();
  Serial.print  (F("ATQA     : 0x")); printAtqa(atqa);
  Serial.print  (F("   SAK: 0x")); printByteHex(mfrc522.uid.sak); Serial.println();
  Serial.print  (F("Type     : ")); Serial.println(mfrc522.PICC_GetTypeName(t));
  if (haveVer) { Serial.print(F("Version  : ")); printHexColon(ver, 8); Serial.println(); }
  Serial.println(F("Formatted view: FL Toolkit -> RFID Reader"));
  Serial.println(F("============================="));
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { ; }
  SPI.begin();                       // ESP32 VSPI: SCK18, MISO19, MOSI23, SS5
  mfrc522.PCD_Init();
  delay(50);
  Serial.println("{\"event\":\"ready\",\"reader\":\"RC522\"}");
}

void loop() {
  // RequestA first (to capture ATQA), then Select (fills UID + SAK).
  byte atqaBuf[2];
  byte atqaLen = sizeof(atqaBuf);
  if (mfrc522.PICC_RequestA(atqaBuf, &atqaLen) != MFRC522::STATUS_OK) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  MFRC522::PICC_Type t = mfrc522.PICC_GetType(mfrc522.uid.sak);
  word atqa = (word)atqaBuf[1] << 8 | atqaBuf[0];

  bool isClassic = (t == MFRC522::PICC_TYPE_MIFARE_MINI ||
                    t == MFRC522::PICC_TYPE_MIFARE_1K   ||
                    t == MFRC522::PICC_TYPE_MIFARE_4K);
  bool isUL = (t == MFRC522::PICC_TYPE_MIFARE_UL);

  byte ver[8];  bool haveVer = false;
  byte pages[32]; byte nPages = 0;
  if (isUL) { haveVer = getVersion(ver); nPages = readFirstPages(pages); }

  // ── machine JSON line (for the web page) ──
  Serial.print("{\"event\":\"card\",\"std\":\"ISO14443 Type A\",\"uid\":\"");
  printHex(mfrc522.uid.uidByte, mfrc522.uid.size);
  Serial.print("\",\"uidLength\":");   Serial.print(mfrc522.uid.size);
  Serial.print(",\"atqa\":\"");        printAtqa(atqa);
  Serial.print("\",\"sak\":\"");       printByteHex(mfrc522.uid.sak);
  Serial.print("\",\"piccName\":\"");  Serial.print(mfrc522.PICC_GetTypeName(t));
  Serial.print("\",\"family\":\"");    Serial.print(isClassic ? "classic" : isUL ? "ultralight" : "other");
  Serial.print("\"");
  if (isUL) {
    Serial.print(",\"version\":\"");   if (haveVer) printHex(ver, 8);
    Serial.print("\",\"pages\":[");
    for (byte i = 0; i < nPages; i++) { if (i) Serial.print(','); Serial.print('"'); printHex(pages + i * 4, 4); Serial.print('"'); }
    Serial.print("]");
  }
  Serial.println("}");

  // ── readable summary (for the Serial Monitor) ──
  printReadable(atqa, t, ver, haveVer);

  mfrc522.PICC_HaltA();
}
