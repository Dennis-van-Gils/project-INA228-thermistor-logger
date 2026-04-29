/*
INA228 thermistor logger


Hardware
--------
Supported microcontrollers:
  - Adafruit Feather M4 Express (ADA3857)
  - Adafruit ItsyBitsy M4 Express (ADA3800)
  - WEMOS LOLIN ESP32-S3 Mini

Sensors:
  - Adafruit INA228 (ADA5832): I2C 85V, 20-bit High or Low Side Power Monitor
    featuring Texas Instruments INA228

Thermistors:
  - Measurement Specialties (GA)G22K7MCD419
    Glass bead Ø0.38mm, 30 ms response time in liquids


How to compile
--------------
When using ESP32-S3 within VSCode using the Arduino framework, see the guide at:
https://github.com/pioarduino/platform-espressif32
NOTE: Currently only supports Espressif Arduino 3.3.8 and IDF v5.5.4


https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger
Dennis van Gils, 21-04-2026
*/

#include <Arduino.h>

#include "Adafruit_INA228.h"
#include "DvG_StreamCommand.h"

// When true, waits for a serial connection and prints the INA228 connection
// status to the serial stream.
const bool VERBOSE = false;

/*------------------------------------------------------------------------------
  INA228
------------------------------------------------------------------------------*/

// const uint8_t INA228_ADDRESSES[] = {0x40, 0x41, 0x44, 0x45};
const uint8_t INA228_ADDRESSES[] = {0x40};
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
------------------------------------------------------------------------------*/

// Instantiate serial port listener for receiving ASCII commands
#define Ser Serial
const uint32_t PERIOD_SC = 20;   // Period to listen for serial commands [ms]
const uint8_t CMD_BUF_LEN = 16;  // Length of the ASCII command buffer
char cmd_buf[CMD_BUF_LEN]{'\0'}; // The ASCII command buffer
DvG_StreamCommand sc(Ser, cmd_buf, CMD_BUF_LEN);

// General string buffer
const int BUFLEN = 1024;
char buf[BUFLEN];

/*------------------------------------------------------------------------------
  setup
------------------------------------------------------------------------------*/

void setup() {
#if defined(_VARIANT_FEATHER_M4_) || defined(_VARIANT_ITSYBITSY_M4_)
  asm(".global _printf_float"); // Enables float support for `snprintf()`
#endif

  Ser.begin(115200);
  if (VERBOSE) {
    while (!Ser) {
      delay(10);
    }
  }

  uint8_t i = 0;
  for (auto &ina228 : ina228_sensors) {
    uint8_t i2c_address = INA228_ADDRESSES[i];

    if (!ina228.begin(i2c_address, &Wire, SKIP_RESET)) {
      Ser.print("Could not find INA228 chip at address 0x");
      Ser.println(i2c_address, HEX);
      while (1) {
      }
    }

    if (VERBOSE) {
      Ser.print("Found INA228 chip at address 0x");
      Ser.println(i2c_address, HEX);
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
  float I;                        // Current [mA]
  float V;                        // Bus voltage [mV]
  float V_shunt;                  // Shunt voltage [mV]
  float T_die;                    // Die temperature ['C]

  /*----------------------------------------------------------------------------
    Process incoming serial commands every PERIOD_SC milliseconds
  ----------------------------------------------------------------------------*/
  static uint32_t tick_sc = now;

  if ((now - tick_sc) > PERIOD_SC) {
    tick_sc = now;

    if (sc.available()) {
      strCmd = sc.getCommand();

      if (strcmp(strCmd, "id?") == 0) {
        Ser.println("Arduino, INA228 thermistor logger");
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
      I = ina228.readCurrent();            // [mA]
      V = ina228.readBusVoltage();         // [V]
      V_shunt = ina228.readShuntVoltage(); // [mV]
      // T_die = ina228.readDieTemp();        // ['C]

      snprintf(buf + strlen(buf), BUFLEN - strlen(buf),
               "\t%.4f V"   // V bus
               "\t%.4f mV"  // V shunt
               "\t%.4f mA"  // I
               "\t%.1f Ohm" // R
               //"\t%.1f 'C"  // T die
               ,
               V, V_shunt, I, V / I * 1000. //, T_die
      );
    }

    Ser.println(buf);
  }
}