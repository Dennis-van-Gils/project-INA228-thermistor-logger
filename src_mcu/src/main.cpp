/*
INA228 thermistor logger

Hardware
--------

Microcontroller:
  - Adafruit Feather M4 Express (ADA3857)

Sensors:
  - Adafruit INA228 (ADA5832): I2C 85V, 20-bit High or Low Side Power Monitor
    featuring Texas Instruments INA228

Thermistors:
  - Measurement Specialties (GA)G22K7MCD419
    Glass bead Ø0.38mm, 30 ms response time in liquids

https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger
Dennis van Gils, 21-04-2026
*/

// Background info on low vs high side sensing:
// https://www.allaboutcircuits.com/technical-articles/resistive-current-sensing-low-side-versus-high-side-sensing/

#include <Arduino.h>

#include "Adafruit_INA228.h"
#include "DvG_StreamCommand.h"

// INA228 current sensors: I2C addresses
// const uint8_t ina228_addresses[] = {0x40, 0x41, 0x44, 0x45};
const uint8_t ina228_addresses[] = {0x40};

// INA228 current sensors
const size_t N_sensors = sizeof(ina228_addresses) / sizeof(ina228_addresses[0]);
Adafruit_INA228 ina228_sensors[N_sensors];

/*------------------------------------------------------------------------------
  INA228 settings
------------------------------------------------------------------------------*/

// [Ohm] Shunt resistor internal to Adafruit INA228
const float INA228_R_SHUNT = 0.015;

// [A] Maximum expected current
const float INA228_MAX_CURRENT = 0.001;

// Shunt full scale ADC range. 0: +/-163.84 mV or 1: +/-40.96 mV.
const uint8_t INA228_ADC_RANGE = 1;

// [#] 1, 4, 16, 64, 128, 256, 512, 1024
const INA2XX_AveragingCount INA228_COUNT = INA228_COUNT_1024;

// Prevent resetting the INA228 chip on init?
const bool SKIP_RESET = true;

/*------------------------------------------------------------------------------
------------------------------------------------------------------------------*/

// Instantiate serial port listener for receiving ASCII commands
#define Ser Serial
const uint32_t PERIOD_SC = 20;   // [ms] Period to listen for serial commands
const uint8_t CMD_BUF_LEN = 16;  // Length of the ASCII command buffer
char cmd_buf[CMD_BUF_LEN]{'\0'}; // The ASCII command buffer
DvG_StreamCommand sc(Serial, cmd_buf, CMD_BUF_LEN);

// General string buffer
const int BUFLEN = 1024;
char buf[BUFLEN];

/*------------------------------------------------------------------------------
  Time keeping
------------------------------------------------------------------------------*/

void get_systick_timestamp(uint32_t *stamp_millis,
                           uint16_t *stamp_micros_part) {
  /* Adapted from:
  https://github.com/arduino/ArduinoCore-samd/blob/master/cores/arduino/delay.c

  Note:
    The millis counter will roll over after 49.7 days.
  */
  // clang-format off
  uint32_t ticks, ticks2;
  uint32_t pend, pend2;
  uint32_t count, count2;
  uint32_t _ulTickCount = millis();

  ticks2 = SysTick->VAL;
  pend2  = !!(SCB->ICSR & SCB_ICSR_PENDSTSET_Msk);
  count2 = _ulTickCount;

  do {
    ticks  = ticks2;
    pend   = pend2;
    count  = count2;
    ticks2 = SysTick->VAL;
    pend2  = !!(SCB->ICSR & SCB_ICSR_PENDSTSET_Msk);
    count2 = _ulTickCount;
  } while ((pend != pend2) || (count != count2) || (ticks < ticks2));

  (*stamp_millis) = count2;
  if (pend) {(*stamp_millis)++;}
  (*stamp_micros_part) =
    (((SysTick->LOAD - ticks) * (1048576 / (VARIANT_MCK / 1000000))) >> 20);
  // clang-format on
}

/*------------------------------------------------------------------------------
    setup
------------------------------------------------------------------------------*/

void setup() {
  asm(".global _printf_float"); // Enables float support for `snprintf()`

  Ser.begin(115200);
  /*
  while (!Ser) { // Wait until serial port is opened
    delay(10);
  }
  */

  uint8_t i = 0;
  for (auto &ina228 : ina228_sensors) {
    uint8_t i2c_address = ina228_addresses[i];

    if (!ina228.begin(i2c_address, &Wire, SKIP_RESET)) {
      Ser.print("Couldn't find INA228 chip at address 0x");
      Ser.println(i2c_address, HEX);
      while (1) {
      }
    }
    // Ser.print("Found INA228 chip at address 0x");
    // Ser.println(i2c_address, HEX);
    i++;

    ina228.setMode(INA228_MODE_CONT_BUS_SHUNT);
    ina228.setShunt(INA228_R_SHUNT, INA228_MAX_CURRENT);
    ina228.setADCRange(INA228_ADC_RANGE);
    ina228.setAveragingCount(INA228_COUNT);

    // [us] 50, 84, 150, 280, 540, 1052, 2074, 4120
    ina228.setCurrentConversionTime(INA228_TIME_4120_us);
    ina228.setVoltageConversionTime(INA228_TIME_4120_us);
    ina228.setTemperatureConversionTime(INA228_TIME_4120_us);

    // Report settings to terminal
    /*
    Ser.print("ADC range      : ");
    Ser.println(ina228.getADCRange());
    Ser.print("Mode           : ");
    Ser.println(ina228.getMode());
    Ser.print("Averaging count: ");
    Ser.println(ina228.getAveragingCount());
    Ser.print("Current     conversion time: ");
    Ser.println(ina228.getCurrentConversionTime());
    Ser.print("Voltage     conversion time: ");
    Ser.println(ina228.getVoltageConversionTime());
    Ser.print("Temperature conversion time: ");
    Ser.println(ina228.getTemperatureConversionTime());
    Ser.println();
    */
  }
}

/*------------------------------------------------------------------------------
    loop
------------------------------------------------------------------------------*/

void loop() {
  char *strCmd; // Incoming serial command string
  static bool DAQ_running = true;
  float I; // [mA] Current
  float V; // [mV] Bus voltage
  // float E; // [J]  Energy
  float V_shunt; // [mV] Shunt voltage
  // float P;       // [mW] Power
  // float T_die;   // ['C] Die temperature

  // Time keeping
  uint32_t millis_copy = millis();
  uint16_t micros_part;

  /*----------------------------------------------------------------------------
    Process incoming serial commands every PERIOD_SC milliseconds
  ----------------------------------------------------------------------------*/
  static uint32_t tick_sc = millis_copy;

  if ((millis_copy - tick_sc) > PERIOD_SC) {
    tick_sc = millis_copy;
    if (sc.available()) {
      strCmd = sc.getCommand();

      if (strcmp(strCmd, "id?") == 0) {
        Ser.println("Arduino, INA228 thermistor logger");
        DAQ_running = false;

      } else if (strcmp(strCmd, "r") == 0) {
        for (auto &ina228 : ina228_sensors) {
          ina228.resetAccumulators();
        }

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
    get_systick_timestamp(&millis_copy, &micros_part);

    snprintf(buf, BUFLEN,
             "%lu\t" // Timestamp millis [ms]
             "%u",   // Timestamp micros part [us]
             millis_copy, micros_part);

    for (auto &ina228 : ina228_sensors) {
      I = ina228.readCurrent();
      V = ina228.readBusVoltage();
      // E = ina228.readEnergy();
      V_shunt = ina228.readShuntVoltage();
      // P = ina228.readPower();
      // P = I * V / 1e3;
      // T_die = ina228.readDieTemp();

      snprintf(buf + strlen(buf), BUFLEN - strlen(buf),
               "\t"
               "%.6f\t" // V bus
               "%.7f\t" // V shunt
               "%.4f\t" // I
               "%.1f",  // R
               V, V_shunt, I, V / I * 1000.);
    }

    Ser.println(buf);
  }
}