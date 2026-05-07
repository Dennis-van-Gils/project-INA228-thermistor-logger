/**
 * @file    main.cpp
 * @author  Dennis van Gils (vangils.dennis@gmail.com)
 * @version https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger
 * @date    21-04-2026
 *
 * @brief   Firmware for the INA228 thermistor logger.
 *
 * Hardware
 * --------
 * Supported and tested microcontrollers:
 *   - Adafruit Feather M4 Express (ADA3857)
 *   - Adafruit ItsyBitsy M4 Express (ADA3800)
 *   - WEMOS LOLIN ESP32-S3 Mini
 *
 * Sensors:
 *   - Adafruit INA228 (ADA5832): I2C 85V, 20-bit High or Low Side Power Monitor
 *     featuring Texas Instruments INA228
 *     NOTE: Replaced the onboard shunt resistor of 0.015 Ohm with a 1.0 Ohm
 *           one.
 *
 * Thermistors:
 *   - Measurement Specialties (GA)G22K7MCD419
 *     Glass bead Ø0.38mm, 30 ms response time in liquids.
 *
 * How to compile
 * --------------
 * When using an ESP32 microcontroller within VSCode using the Arduino
 * framework, see the guide at:
 * https://github.com/pioarduino/platform-espressif32
 * NOTE: Currently only supports Espressif Arduino 3.3.8 and IDF v5.5.4
 *
 * @copyright MIT License. See the LICENSE file for details.
 */

#include <Arduino.h>

#include "Adafruit_INA228.h"
#include "DvG_StreamCommand.h"

#ifdef ESP32
#include "secrets.h"
#include <WiFi.h>
#include <esp_wifi.h>

WiFiServer server(23);
WiFiClient client;
#endif

#if defined(_VARIANT_FEATHER_M4_) || defined(_VARIANT_ITSYBITSY_M4_)
asm(".global _printf_float"); // Enables float support for `snprintf()`
#endif

/*------------------------------------------------------------------------------
  INA228
------------------------------------------------------------------------------*/

const uint8_t INA228_ADDRESSES[] = {0x40, 0x41, 0x44, 0x45};
const size_t N_SENSORS = sizeof(INA228_ADDRESSES) / sizeof(INA228_ADDRESSES[0]);
Adafruit_INA228 ina228_sensors[N_SENSORS];

// Shunt resistor value [Ohm]
const float INA228_SHUNT_RES = 1.0;

// Maximum expected current [A]
const float INA228_MAX_CURRENT = 0.0005;

// Shunt full scale ADC range: [0: ±163.84 mV, 1: ±40.96 mV]
const uint8_t INA228_ADC_RANGE = 1;

// Averaging count: 1, 4, 16, 64, 128, 256, 512, 1024
const INA2XX_AveragingCount INA228_AVERAGING_COUNT = INA228_COUNT_128;

// Conversion time: 50, 84, 150, 280, 540, 1052, 2074, 4120 [us]
const INA2XX_ConversionTime INA228_CONV_TIME_CURRENT = INA228_TIME_4120_us;
const INA2XX_ConversionTime INA228_CONV_TIME_VOLTAGE = INA228_TIME_4120_us;
const INA2XX_ConversionTime INA228_CONV_TIME_TEMP = INA228_TIME_4120_us;

// Prevent resetting the INA228 chip on init?
const bool SKIP_RESET = true;

/*------------------------------------------------------------------------------
  Char buffers and command listeners
------------------------------------------------------------------------------*/

const int BUF_LEN = 1024; // Length of the general string buffer
char buf[BUF_LEN];        // General string buffer

const uint8_t CMD_BUF_LEN = 16; // Length of the ASCII command buffer
const uint32_t PERIOD_SC = 20;  // Update period to listen for commands [ms]
char cmd_buf_serial[CMD_BUF_LEN]{'\0'}; // ASCII command buffer for Serial
// Serial port listener for receiving ASCII commands
DvG_StreamCommand sc_serial(Serial, cmd_buf_serial, CMD_BUF_LEN);

#ifdef ESP32
char cmd_buf_wifi[CMD_BUF_LEN]{'\0'}; // ASCII command buffer for WiFi client
// WiFi client listener for receiving ASCII commands
DvG_StreamCommand sc_wifi(client, cmd_buf_wifi, CMD_BUF_LEN);
#endif

/*------------------------------------------------------------------------------
  Helper functions
------------------------------------------------------------------------------*/

void println(const char *str) {
  Serial.println(str);
#ifdef ESP32
  if (client && client.connected()) {
    client.println(str);
  }
#endif
}

#ifdef ESP32
char *pretty_esp_wifi_mac_address() {
  uint8_t baseMac[6];
  esp_err_t ret = esp_wifi_get_mac(WIFI_IF_STA, baseMac);

  if (ret == ESP_OK) {
    snprintf(buf, BUF_LEN, "%02X:%02X:%02X:%02X:%02X:%02X", baseMac[0],
             baseMac[1], baseMac[2], baseMac[3], baseMac[4], baseMac[5]);
  } else {
    snprintf(buf, BUF_LEN, "00:00:00:00:00:00");
  }

  return buf;
}
#endif

/*------------------------------------------------------------------------------
  setup
------------------------------------------------------------------------------*/

void setup() {
  Serial.begin(115200);
  /*
  while (!Serial) {
    delay(10);
  }
  */

#ifdef ESP32
  /*----------------------------------------------------------------------------
  Establish WiFi connection
  ----------------------------------------------------------------------------*/

  Serial.print("MAC address: ");
  Serial.println(pretty_esp_wifi_mac_address());

  WiFi.useStaticBuffers(true);
  WiFi.mode(WIFI_STA);
  // WiFi.config(IPAddress(192, 168, 1, 123), IPAddress(192, 168, 1, 1),
  //             IPAddress(255, 255, 255, 0));

  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConnected to WiFi");
  Serial.print("  SSID: ");
  Serial.println(WiFi.SSID());
  Serial.print("  IP  : ");
  Serial.println(WiFi.localIP());
  Serial.print("  RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");

  server.begin();
#endif

  /*----------------------------------------------------------------------------
    Connect to INA228 sensors
  ----------------------------------------------------------------------------*/

  Serial.println("Connecting to INA228 sensors:");

  uint8_t i = 0;
  for (auto &ina228 : ina228_sensors) {
    uint8_t i2c_address = INA228_ADDRESSES[i];

    if (!ina228.begin(i2c_address, &Wire, SKIP_RESET)) {
      while (1) {
        Serial.print("Could not connect to INA228 sensor at address 0x");
        Serial.println(i2c_address, HEX);
        delay(2000);
      }
    }

    Serial.print("  Success at address 0x");
    Serial.println(i2c_address, HEX);
    i++;

    ina228.setMode(INA228_MODE_CONT_BUS_SHUNT);
    // ina228.setMode(INA228_MODE_CONT_TEMP_BUS_SHUNT);
    ina228.setShunt(INA228_SHUNT_RES, INA228_MAX_CURRENT);
    ina228.setADCRange(INA228_ADC_RANGE);
    ina228.setAveragingCount(INA228_AVERAGING_COUNT);
    ina228.setCurrentConversionTime(INA228_CONV_TIME_CURRENT);
    ina228.setVoltageConversionTime(INA228_CONV_TIME_VOLTAGE);
    ina228.setTemperatureConversionTime(INA228_CONV_TIME_TEMP);
  }
}

/*------------------------------------------------------------------------------
  loop
------------------------------------------------------------------------------*/

void loop() {
  uint32_t now = millis();        // Timestamp [ms]
  static uint32_t tick_sc = now;  // Last timestamp of command listener [ms]
  char *str_cmd;                  // Incoming command string
  bool cmd_pending = false;       // Command is pending to be processed?
  static bool DAQ_running = true; // Continuously output readings?

#ifdef ESP32
  if (server.hasClient()) {
    if (!client || !client.connected()) {
      client = server.accept();
      client.println("READY");
    } else {
      WiFiClient reject = server.accept();
      reject.stop();
    }
  }
#endif

  /*----------------------------------------------------------------------------
    Process incoming commands
  ----------------------------------------------------------------------------*/

  if ((now - tick_sc) > PERIOD_SC) {
    tick_sc = now;

    if (sc_serial.available()) {
      str_cmd = sc_serial.getCommand();
      cmd_pending = true;
    }

#ifdef ESP32
    if (client && client.connected() && sc_wifi.available()) {
      str_cmd = sc_wifi.getCommand();
      cmd_pending = true;
    }
#endif

    if (cmd_pending) {

      if (strcmp(str_cmd, "id?") == 0) {
        println("Arduino, INA228 thermistor logger");
        DAQ_running = false;

      } else if (strcmp(str_cmd, "addr?") == 0) {
        // Report the addresses of all INA228 sensors
        snprintf(buf, BUF_LEN, "\0");
        for (int i = 0; i < N_SENSORS; i++) {
          snprintf(buf + strlen(buf), BUF_LEN, "0x%02X", INA228_ADDRESSES[i]);
          if (i < N_SENSORS - 1) {
            snprintf(buf + strlen(buf), BUF_LEN, "\t");
          }
        }
        println(buf);
        DAQ_running = false;

      } else if (strcmp(str_cmd, "on") == 0) {
        DAQ_running = true;

      } else if (strcmp(str_cmd, "off") == 0) {
        DAQ_running = false;

      } else if (strcmp(str_cmd, "mac?") == 0) {
        DAQ_running = false;
#ifdef ESP32
        println(pretty_esp_wifi_mac_address());
#else
        println("00:00:00:00:00:00");
#endif

      } else if (strcmp(str_cmd, "ssid?") == 0) {
        DAQ_running = false;
#ifdef ESP32
        println(WiFi.SSID().c_str());
#else
        println("Not available");
#endif

      } else if (strcmp(str_cmd, "ip?") == 0) {
        DAQ_running = false;
#ifdef ESP32
        println(WiFi.localIP().toString().c_str());
#else
        println("0.0.0.0");
#endif

      } else if (strcmp(str_cmd, "rssi?") == 0) {
        DAQ_running = false;
#ifdef ESP32
        itoa(WiFi.RSSI(), buf, 10);
        println(buf);
#else
        println("0");
#endif
      }
    }
  }

  /*----------------------------------------------------------------------------
    Acquire data
  ----------------------------------------------------------------------------*/

  if (DAQ_running && ina228_sensors[0].conversionReady()) {
    snprintf(buf, BUF_LEN, "%lu", now); // Timestamp [ms]

    for (auto &ina228 : ina228_sensors) {
      float V_bus = ina228.readBusVoltage();     // [V]
      float V_shunt = ina228.readShuntVoltage(); // [mV]
      float I = ina228.readCurrent();            // [mA]
      float R = V_bus / I * 1000.;               // [Ohm]
      // float T_die = ina228.readDieTemp();        // ['C]

      snprintf(buf + strlen(buf), BUF_LEN - strlen(buf),
               "\t%.5f" // V_bus   [V]
               "\t%.5f" // V_shunt [mV]
               "\t%.5f" // I       [mA]
               "\t%.0f" // R       [Ohm]
               // "\t%.1f" // T die   ['C]
               ,
               V_bus, V_shunt, I, R //, T_die
      );
    }

    println(buf);
  }
}