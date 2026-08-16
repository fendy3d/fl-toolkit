/*
 * FL Toolkit — ESP32 + RC522 RFID reader
 * ---------------------------------------
 * Prints ONE JSON line per tapped card over USB serial @ 115200 baud.
 * For MIFARE Classic cards it also dumps every sector/block it can read
 * using the factory-default key FF FF FF FF FF FF (key A). Sectors that use
 * a different key come back as "auth":"denied" (expected — the card will not
 * reveal them without the right key).
 *
 * WIRING  (RC522  ->  ESP32 dev board)   ⚠ RC522 is 3.3 V — never wire it to 5 V
 *   SDA / SS  -> GPIO 5          SCK   -> GPIO 18
 *   MOSI      -> GPIO 23         MISO  -> GPIO 19
 *   RST       -> GPIO 22         3.3V  -> 3V3        GND -> GND
 *
 * SETUP (Arduino IDE)
 *   1. Boards Manager: install "esp32" (Espressif). Select your ESP32 board.
 *   2. Library Manager: install "MFRC522" by GithubCommunity (miguelbalboa).
 *   3. Upload this sketch. Serial Monitor @ 115200 to test (optional).
 *
 * The FL Toolkit "RFID Reader" web page connects to this over USB (Web Serial)
 * and displays each card — no drivers or internet needed.
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
    MFRC522::StatusCode rs = mfrc522.MIFARE_Read(blockAddr, buffer, &size);
    if (rs != MFRC522::STATUS_OK) {
      Serial.print(",\"data\":null}");
    } else {
      Serial.print(",\"data\":\"");
      printHex(buffer, 16);
      Serial.print("\"}");
    }
  }
  Serial.print("]}");
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
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial())   return;

  MFRC522::PICC_Type piccType = mfrc522.PICC_GetType(mfrc522.uid.sak);

  Serial.print("{\"event\":\"card\",\"uid\":\"");
  printHex(mfrc522.uid.uidByte, mfrc522.uid.size);
  Serial.print("\",\"uidLength\":");
  Serial.print(mfrc522.uid.size);
  Serial.print(",\"sak\":\"");
  if (mfrc522.uid.sak < 0x10) Serial.print('0');
  Serial.print(mfrc522.uid.sak, HEX);
  Serial.print("\",\"type\":\"");
  Serial.print(mfrc522.PICC_GetTypeName(piccType));
  Serial.print("\"");

  bool isClassic = (piccType == MFRC522::PICC_TYPE_MIFARE_MINI ||
                    piccType == MFRC522::PICC_TYPE_MIFARE_1K   ||
                    piccType == MFRC522::PICC_TYPE_MIFARE_4K);
  if (isClassic) {
    byte sectors = (piccType == MFRC522::PICC_TYPE_MIFARE_4K)   ? 40 :
                   (piccType == MFRC522::PICC_TYPE_MIFARE_MINI) ?  5 : 16;
    Serial.print(",\"sectors\":[");
    for (byte s = 0; s < sectors; s++) {
      if (s) Serial.print(',');
      dumpSector(s);
    }
    Serial.print("]");
  }

  Serial.println("}");

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}
