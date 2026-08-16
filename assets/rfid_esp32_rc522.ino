/*
 * FL Toolkit — ESP32 + RC522 RFID reader
 * ---------------------------------------
 * Prints ONE JSON line per tapped card over USB serial @ 115200 baud.
 *
 *  • MIFARE Classic (Mini/1K/4K) -> full sector/block dump with the factory
 *    default key FF FF FF FF FF FF (key A). Sectors on another key -> "denied".
 *  • MIFARE Ultralight / NTAG21x -> ATQA, SAK, GET_VERSION, and a full page
 *    dump. The web page turns this into type (e.g. NTAG215), manufacturer,
 *    memory size, NDEF status, and the Get-Version breakdown.
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
MFRC522::MIFARE_Key key;

void printHex(byte *buffer, byte len) {
  for (byte i = 0; i < len; i++) {
    if (buffer[i] < 0x10) Serial.print('0');
    Serial.print(buffer[i], HEX);
  }
}

// ── MIFARE Classic: one sector as JSON ──────────────────────────────────────
void dumpSector(byte sector) {
  byte firstBlock, nBlocks;
  if (sector < 32) { nBlocks = 4;  firstBlock = sector * 4; }
  else             { nBlocks = 16; firstBlock = 128 + (sector - 32) * 16; }
  byte trailer = firstBlock + nBlocks - 1;

  Serial.print("{\"sector\":");
  Serial.print(sector);

  MFRC522::StatusCode status = mfrc522.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, trailer, &key, &(mfrc522.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.print(",\"auth\":\"denied\",\"blocks\":[]}");
    return;
  }
  Serial.print(",\"auth\":\"ok\",\"blocks\":[");
  for (byte b = 0; b < nBlocks; b++) {
    byte blockAddr = firstBlock + b;
    byte buffer[18];
    byte size = sizeof(buffer);
    if (b) Serial.print(',');
    Serial.print("{\"block\":");
    Serial.print(blockAddr);
    Serial.print(",\"trailer\":");
    Serial.print(blockAddr == trailer ? "true" : "false");
    if (mfrc522.MIFARE_Read(blockAddr, buffer, &size) != MFRC522::STATUS_OK) {
      Serial.print(",\"data\":null}");
    } else {
      Serial.print(",\"data\":\"");
      printHex(buffer, 16);
      Serial.print("\"}");
    }
  }
  Serial.print("]}");
}

// ── Ultralight / NTAG: GET_VERSION (0x60) -> 8 bytes ────────────────────────
bool getVersion(byte *out8) {
  byte cmd[3];
  cmd[0] = 0x60;
  if (mfrc522.PCD_CalculateCRC(cmd, 1, &cmd[1]) != MFRC522::STATUS_OK) return false;
  byte back[12];
  byte backLen = sizeof(back);
  byte validBits = 0;
  MFRC522::StatusCode s = mfrc522.PCD_TransceiveData(cmd, 3, back, &backLen, &validBits, 0, true);
  if (s != MFRC522::STATUS_OK || backLen < 8) return false;   // some UL don't support it
  for (byte i = 0; i < 8; i++) out8[i] = back[i];
  return true;
}

// How many pages to dump, from the GET_VERSION storage-size byte.
byte pageCount(bool haveVer, byte storage) {
  if (!haveVer) return 16;          // classic MIFARE Ultralight
  switch (storage) {
    case 0x0F: return 45;           // NTAG213
    case 0x11: return 135;          // NTAG215
    case 0x13: return 231;          // NTAG216
    case 0x0B: return 20;           // UL EV1 (MF0UL11)
    case 0x0E: return 41;           // UL EV1 (MF0UL21)
    default:   return 16;
  }
}

void dumpUltralight() {
  byte ver[8];
  bool haveVer = getVersion(ver);

  Serial.print(",\"family\":\"ultralight\",\"version\":\"");
  if (haveVer) printHex(ver, 8);
  Serial.print("\",\"pages\":[");

  byte pages = pageCount(haveVer, haveVer ? ver[6] : 0);
  bool first = true;
  for (byte p = 0; p < pages; p += 4) {
    byte buffer[18];
    byte size = sizeof(buffer);
    if (mfrc522.MIFARE_Read(p, buffer, &size) != MFRC522::STATUS_OK) break;
    for (byte i = 0; i < 4 && (p + i) < pages; i++) {
      if (!first) Serial.print(',');
      first = false;
      Serial.print('"');
      printHex(&buffer[i * 4], 4);
      Serial.print('"');
    }
  }
  Serial.print("]");
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { ; }
  SPI.begin();                       // ESP32 VSPI: SCK18, MISO19, MOSI23, SS5
  mfrc522.PCD_Init();
  delay(50);
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;   // factory default key
  Serial.println("{\"event\":\"ready\",\"reader\":\"RC522\"}");
}

void loop() {
  // RequestA first so we can capture ATQA, then Select to get UID + SAK.
  byte atqaBuf[2];
  byte atqaLen = sizeof(atqaBuf);
  if (mfrc522.PICC_RequestA(atqaBuf, &atqaLen) != MFRC522::STATUS_OK) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  MFRC522::PICC_Type piccType = mfrc522.PICC_GetType(mfrc522.uid.sak);
  word atqa = (word)atqaBuf[1] << 8 | atqaBuf[0];

  Serial.print("{\"event\":\"card\",\"std\":\"ISO14443 Type A\",\"uid\":\"");
  printHex(mfrc522.uid.uidByte, mfrc522.uid.size);
  Serial.print("\",\"uidLength\":");
  Serial.print(mfrc522.uid.size);
  Serial.print(",\"atqa\":\"");
  if (atqa < 0x1000) Serial.print('0');
  if (atqa < 0x0100) Serial.print('0');
  if (atqa < 0x0010) Serial.print('0');
  Serial.print(atqa, HEX);
  Serial.print("\",\"sak\":\"");
  if (mfrc522.uid.sak < 0x10) Serial.print('0');
  Serial.print(mfrc522.uid.sak, HEX);
  Serial.print("\",\"piccName\":\"");
  Serial.print(mfrc522.PICC_GetTypeName(piccType));
  Serial.print("\"");

  if (piccType == MFRC522::PICC_TYPE_MIFARE_MINI ||
      piccType == MFRC522::PICC_TYPE_MIFARE_1K   ||
      piccType == MFRC522::PICC_TYPE_MIFARE_4K) {
    byte sectors = (piccType == MFRC522::PICC_TYPE_MIFARE_4K)   ? 40 :
                   (piccType == MFRC522::PICC_TYPE_MIFARE_MINI) ?  5 : 16;
    Serial.print(",\"family\":\"classic\",\"sectors\":[");
    for (byte s = 0; s < sectors; s++) { if (s) Serial.print(','); dumpSector(s); }
    Serial.print("]");
  } else if (piccType == MFRC522::PICC_TYPE_MIFARE_UL) {
    dumpUltralight();
  } else {
    Serial.print(",\"family\":\"other\"");
  }

  Serial.println("}");

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}
