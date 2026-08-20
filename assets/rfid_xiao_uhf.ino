/*
 * FL Toolkit — XIAO ESP32-C3 + M5Stack UHF RFID Unit (U107, JRD-4035)
 * -------------------------------------------------------------------
 * Continuously polls for UHF (EPC Gen2 / ISO 18000-6C) tags and reports each
 * read two ways over USB @ 115200 baud:
 *   1. a readable line for new tags (nice in the Arduino Serial Monitor), and
 *   2. one compact JSON line per read (consumed by the FL Toolkit
 *      "RFID Reader (UHF)" web page, which renders the live tag table).
 *
 * WIRING  (M5Stack Grove cable  ->  XIAO ESP32-C3)
 *   Black  (GND)          -> GND
 *   Red    (5V)           -> 5V   (USB passthrough — power the XIAO over USB-C)
 *   White  (unit TX, out) -> D7   (GPIO20, RX)
 *   Yellow (unit RX, in)  -> D6   (GPIO21, TX)
 * The unit is powered at 5 V but its UART is 3.3 V logic — no level shifter.
 * If you get no data, the single most likely fix is swapping white/yellow.
 *
 * SETUP (Arduino IDE): install the "esp32" (Espressif) boards package, select
 * "XIAO_ESP32C3", and make sure Tools -> "USB CDC On Boot" is Enabled (it is
 * by default for this board), then upload. No extra libraries needed.
 */

#include <Arduino.h>

#define UHF     Serial1
#define PIN_RX  D7        // GPIO20 <- unit TX (white)
#define PIN_TX  D6        // GPIO21 -> unit RX (yellow)

// JRD-4035 frames: BB | type | cmd | len(2, MSB first) | payload | checksum | 7E
// checksum = (type + cmd + len + payload bytes) & 0xFF
const uint8_t POLL_CMD[] = {0xBB, 0x00, 0x22, 0x00, 0x00, 0x22, 0x7E};  // single poll
// To change TX power (dBm x100, default 2000 = 20 dBm; max 2600 = 26 dBm), send
// e.g. 26 dBm: {0xBB, 0x00, 0xB6, 0x00, 0x02, 0x0A, 0x28, 0xEA, 0x7E}

const uint32_t POLL_INTERVAL_MS = 150;   // ~7 polls/second
const uint32_t NEW_TAG_GAP_MS   = 3000;  // readable line again after 3 s unseen

// ── tiny frame parser ──
enum { WAIT_HDR, WAIT_TYPE, WAIT_CMD, WAIT_LEN1, WAIT_LEN2, WAIT_PAYLOAD, WAIT_CSUM, WAIT_END };
uint8_t  st = WAIT_HDR, fType, fCmd, fCsum;
uint16_t fLen, fPos;
uint8_t  fBuf[64];

// ── recently-seen EPCs (for the readable "new tag" line only) ──
struct Seen { char epc[25]; uint32_t last; };
Seen seen[16];

// ── wiring self-check ──
bool     moduleSeen  = false;
uint32_t lastFrameMs = 0;

void printHexByte(uint8_t b) { if (b < 0x10) Serial.print('0'); Serial.print(b, HEX); }
void printHexStr(const uint8_t *buf, uint8_t len) { for (uint8_t i = 0; i < len; i++) printHexByte(buf[i]); }

bool isNewSighting(const char *epc) {
  uint32_t now = millis();
  int freeSlot = -1, oldest = 0;
  for (int i = 0; i < 16; i++) {
    if (seen[i].epc[0] == 0) { if (freeSlot < 0) freeSlot = i; continue; }
    if (strcmp(seen[i].epc, epc) == 0) {
      bool fresh = (now - seen[i].last) > NEW_TAG_GAP_MS;
      seen[i].last = now;
      return fresh;
    }
    if (seen[i].last < seen[oldest].last) oldest = i;
  }
  int slot = (freeSlot >= 0) ? freeSlot : oldest;
  strncpy(seen[slot].epc, epc, sizeof(seen[slot].epc) - 1);
  seen[slot].last = now;
  return true;
}

// Notice frame 0x22: payload = RSSI(1) + PC(2) + EPC(n) + CRC(2)
void handleTag(const uint8_t *p, uint16_t len) {
  if (len < 6) return;
  int8_t   rssi   = (int8_t)p[0];
  uint16_t epcLen = len - 5;

  char epcHex[49] = {0};
  for (uint16_t i = 0; i < epcLen && i < 24; i++) sprintf(epcHex + i * 2, "%02X", p[3 + i]);

  // ── machine JSON line (for the web page) ──
  Serial.print("{\"event\":\"tag\",\"epc\":\"");  Serial.print(epcHex);
  Serial.print("\",\"pc\":\"");                    printHexByte(p[1]); printHexByte(p[2]);
  Serial.print("\",\"rssi\":");                    Serial.print(rssi);
  Serial.print(",\"crc\":\"");                     printHexByte(p[len - 2]); printHexByte(p[len - 1]);
  Serial.println("\"}");

  // ── readable line, only when the tag (re)enters range ──
  if (isNewSighting(epcHex)) {
    Serial.print(F("# Tag  EPC: ")); Serial.print(epcHex);
    Serial.print(F("  RSSI: "));     Serial.print(rssi); Serial.println(F(" dBm"));
  }
}

void feedParser(uint8_t b) {
  switch (st) {
    case WAIT_HDR:  if (b == 0xBB) st = WAIT_TYPE; break;
    case WAIT_TYPE: fType = b; fCsum = b; st = WAIT_CMD; break;
    case WAIT_CMD:  fCmd  = b; fCsum += b; st = WAIT_LEN1; break;
    case WAIT_LEN1: fLen  = (uint16_t)b << 8; fCsum += b; st = WAIT_LEN2; break;
    case WAIT_LEN2:
      fLen |= b; fCsum += b; fPos = 0;
      if (fLen > sizeof(fBuf)) { st = WAIT_HDR; break; }   // oversized -> resync
      st = fLen ? WAIT_PAYLOAD : WAIT_CSUM;
      break;
    case WAIT_PAYLOAD:
      fBuf[fPos++] = b; fCsum += b;
      if (fPos == fLen) st = WAIT_CSUM;
      break;
    case WAIT_CSUM: st = (b == fCsum) ? WAIT_END : WAIT_HDR; break;
    case WAIT_END:
      if (b == 0x7E) {
        if (!moduleSeen) {
          moduleSeen = true;
          Serial.println(F("# UHF module OK — wiring good, responding to polls"));
        }
        lastFrameMs = millis();
        if (fType == 0x02 && fCmd == 0x22) handleTag(fBuf, fLen);
        // fType 0x01 / fCmd 0xFF = "no tag" error frame — expected, counts as alive.
      }
      st = WAIT_HDR;
      break;
  }
}

void setup() {
  Serial.begin(115200);
  UHF.begin(115200, SERIAL_8N1, PIN_RX, PIN_TX);
  delay(300);                                    // module boot
  Serial.println("{\"event\":\"ready\",\"reader\":\"JRD-4035\"}");
  Serial.println(F("# UHF reader ready — polling for tags"));
}

void loop() {
  static uint32_t lastPoll = 0, lastWarn = 0;
  if (millis() - lastPoll >= POLL_INTERVAL_MS) {
    lastPoll = millis();
    UHF.write(POLL_CMD, sizeof(POLL_CMD));
  }
  while (UHF.available()) feedParser(UHF.read());

  // Wiring self-check: the module answers every poll (even with no tag near),
  // so 5 s of silence means it never got the poll or we can't hear the reply.
  if (millis() - lastFrameMs > 5000 && millis() - lastWarn > 5000) {
    lastWarn = millis();
    Serial.println(F("# NO RESPONSE from UHF module — check wiring: "
                     "red->5V, black->GND, and try swapping white/yellow"));
  }
}
