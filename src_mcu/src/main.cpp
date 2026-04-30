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
#endif

// When true, prints debug information to the serial stream
const bool DEBUG = true;

/*------------------------------------------------------------------------------
  INA228
------------------------------------------------------------------------------*/

const uint8_t INA228_ADDRESSES[] = {0x40, 0x41, 0x44, 0x45};
// const uint8_t INA228_ADDRESSES[] = {0x40};
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
  Serial port and char buffers
------------------------------------------------------------------------------*/

// Instantiate serial port listener for receiving ASCII commands
const uint32_t PERIOD_SC = 20;   // Period to listen for serial commands [ms]
const uint8_t CMD_BUF_LEN = 16;  // Length of the ASCII command buffer
char cmd_buf[CMD_BUF_LEN]{'\0'}; // The ASCII command buffer
DvG_StreamCommand sc(Serial, cmd_buf, CMD_BUF_LEN);

// General string buffer
const int BUFLEN = 1024;
char buf[BUFLEN];

/*------------------------------------------------------------------------------
  ESP32 related
------------------------------------------------------------------------------*/

#ifdef ESP32

/**
 * @brief Print the MAC address of the ESP mcu to the serial stream.
 */
void print_ESP_MAC_address() {
  uint8_t baseMac[6];
  esp_err_t ret = esp_wifi_get_mac(WIFI_IF_STA, baseMac);

  Serial.print("MAC address: ");
  if (ret == ESP_OK) {
    Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X\n", baseMac[0], baseMac[1],
                  baseMac[2], baseMac[3], baseMac[4], baseMac[5]);
  } else {
    Serial.println("Failed to read MAC address");
  }
}

/**
 * @brief Print the WiFi status of the ESP mcu to the serial stream.
 */
void print_WiFi_status() {
  Serial.print("  SSID: ");
  Serial.println(WiFi.SSID());

  Serial.print("  IP  : ");
  Serial.println(WiFi.localIP());

  Serial.print("  RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");
}

#endif

/*------------------------------------------------------------------------------
  setup
------------------------------------------------------------------------------*/

void setup() {
#if defined(_VARIANT_FEATHER_M4_) || defined(_VARIANT_ITSYBITSY_M4_)
  asm(".global _printf_float"); // Enables float support for `snprintf()`
#endif

  Serial.begin(115200);
  /*
  if (DEBUG) {
    while (!Serial) {
      delay(10);
    }
  }
  */

#ifdef ESP32
  // Establish WiFi connection
  WiFi.useStaticBuffers(true);
  WiFi.mode(WIFI_STA);

  if (DEBUG) {
    print_ESP_MAC_address();
    Serial.print("Connecting to WiFi: ");
    Serial.println(ssid);
  }

  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    if (DEBUG) {
      Serial.print(".");
    }
  }

  if (DEBUG) {
    Serial.println("\nConnected to WiFi");
    print_WiFi_status();
  }
#endif

  // Connect to INA228 sensors
  if (DEBUG) {
    Serial.println("Connecting to INA228 sensors:");
  }
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

    if (DEBUG) {
      Serial.print("  Success at address 0x");
      Serial.println(i2c_address, HEX);
    }
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
  char *strCmd;                   // Incoming serial command string
  static bool DAQ_running = true; // Continuously output readings?
  float V;                        // Bus voltage [V]
  float V_shunt;                  // Shunt voltage [mV]
  float I;                        // Current [mA]
  float R;                        // Calculated resistance [Ohm]
  float T_die;                    // Die temperature of INA228 chip ['C]

  /*----------------------------------------------------------------------------
    Process incoming serial commands every PERIOD_SC milliseconds
  ----------------------------------------------------------------------------*/
  static uint32_t tick_sc = now;

  if ((now - tick_sc) > PERIOD_SC) {
    tick_sc = now;

    if (sc.available()) {
      strCmd = sc.getCommand();

      if (strcmp(strCmd, "id?") == 0) {
        Serial.println("Arduino, INA228 thermistor logger");
        DAQ_running = false;

      } else if (strcmp(strCmd, "on") == 0) {
        DAQ_running = true;

      } else if (strcmp(strCmd, "off") == 0) {
        DAQ_running = false;

      } else {
        DAQ_running = !DAQ_running;
      }
    }
  }

  /*----------------------------------------------------------------------------
    Acquire data
  ----------------------------------------------------------------------------*/

  if (DAQ_running && ina228_sensors[0].conversionReady()) {
    snprintf(buf, BUFLEN, "%lu", now); // Timestamp [ms]

    for (auto &ina228 : ina228_sensors) {
      V = ina228.readBusVoltage();         // [V]
      V_shunt = ina228.readShuntVoltage(); // [mV]
      I = ina228.readCurrent();            // [mA]
      R = V / I * 1000.;                   // [Ohm]
      // T_die = ina228.readDieTemp();        // ['C]

      snprintf(buf + strlen(buf), BUFLEN - strlen(buf),
               "\t%.5f" // V_bus [V]
               "\t%.5f" // V_shunt [mV]
               "\t%.5f" // I [mA]
               "\t%.0f" // R [Ohm]
               //"\t%.1f 'C"  // T die
               ,
               V, V_shunt, I, R //, T_die
      );
    }

    Serial.println(buf);
  }
}