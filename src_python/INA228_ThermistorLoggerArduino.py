#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provides class `INA228_ThermistorLoggerArduino` to manage serial
communication with an Arduino programmed as an INA228 Thermistor Logger.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "07-05-2026"
__version__ = "1.0"
# pylint: disable=missing-function-docstring, too-many-instance-attributes
# pylint: disable=too-few-public-methods

import serial

from dvg_devices.Arduino_protocol_serial import Arduino
from dvg_debug_functions import print_fancy_traceback as pft
from dvg_ringbuffer import RingBuffer

# ------------------------------------------------------------------------------
#   INA228_ThermistorLoggerArduino
# ------------------------------------------------------------------------------


class INA228_ThermistorLoggerArduino(Arduino):
    """Manages serial communication with an Arduino programmed as an INA228
    Thermistor Logger."""

    class INA228_Sensor:
        """Container for the measurement values of a single INA228 sensor."""

        def __init__(self, capacity: int, address: str):
            self.capacity = capacity
            """Ring buffer capacity"""

            self.address = address
            """Sensor address as hex string"""

            self.time = RingBuffer(capacity)
            """Time stamp [s]"""

            self.V_bus = RingBuffer(capacity)
            """Bus voltage [V]"""

            self.V_shunt = RingBuffer(capacity)
            """Shunt voltage [V]"""

            self.I = RingBuffer(capacity)
            """Current [A]"""

            self.R = RingBuffer(capacity)
            """Derived resistance [Ohm]"""

            self.T_die = RingBuffer(capacity)
            """Die temperature ['C]"""

            self._ring_buffers = [
                self.time,
                self.V_bus,
                self.V_shunt,
                self.I,
                self.R,
                self.T_die,
            ]
            """List of all ring buffers in the class"""

        def clear(self):
            for rb in self._ring_buffers:
                rb.clear()

    class State:
        """Container for the measurement values of all INA228 sensors.

        Method `begin()` must be called to populate member `INA228_sensors`.
        """

        def __init__(self, capacity: int):
            self.capacity = capacity
            """Ring buffer capacity"""

            self.sensor_addresses: list[str] = []
            """List of INA228 sensor addresses connected to the Arduino"""

            self.N_sensors = 0
            """Number of INA228 sensors connected to the Arduino"""

            self.INA228_sensors: list[
                INA228_ThermistorLoggerArduino.INA228_Sensor
            ] = []
            """List of all INA228 sensors, each containing measurement values."""

        def clear(self):
            for ina228 in self.INA228_sensors:
                ina228.clear()

    def __init__(
        self,
        name="Ard",
        long_name="Arduino",
        connect_to_specific_ID="INA228 Thermistor Logger",
        ring_buffer_capacity: int = 1,
    ):
        super().__init__(
            name=name,
            long_name=long_name,
            connect_to_specific_ID=connect_to_specific_ID,
        )

        # Container for the measurement values of all INA228 sensors
        self.state = self.State(capacity=ring_buffer_capacity)

        # Increase the read timeout from 2 sec (default) to 4 sec
        self.serial_settings["timeout"] = 4

    def begin(self) -> bool:
        """Query the Arduino for the addresses of all connected INA228 sensors,
        and populate the `state.INA_sensors` member accordingly.

        This method must be called once after a connection has been made to
        the Arduino.

        Returns:
            True if successful, False otherwise.
        """
        if self.query_sensor_addresses():
            for address in self.state.sensor_addresses:
                self.state.INA228_sensors.append(
                    self.INA228_Sensor(
                        self.state.capacity,
                        address,
                    )
                )
            return True

        return False

    # --------------------------------------------------------------------------
    #   Arduino commands
    # --------------------------------------------------------------------------

    def query_sensor_addresses(self) -> bool:
        """Query the Arduino for the addresses of all connected INA228 sensors.
        The reply will get parsed and stored in members `state.sensor_addresses`
        and `state.N_sensors`.

        Returns:
            True if successful, False otherwise.
        """
        success, reply = self.query("addr?")

        if success and isinstance(reply, str):
            try:
                addresses = reply.strip("\n").split("\t")
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                # All successful
                self.state.sensor_addresses = addresses
                self.state.N_sensors = len(addresses)
                return True

        return False

    def turn_on(self) -> bool:
        """Send instruction to the Arduino to turn on its continuous data
        reporting of all INA228 sensor data over the serial/wifi stream.

        Returns:
            True if successful, False otherwise.
        """
        return self.write("on")

    def turn_off(self) -> bool:
        """Send instruction to the Arduino to turn off its continuous data
        reporting of all INA228 sensor data over the serial/wifi stream.

        Returns:
            True if successful, False otherwise.
        """
        return self.write("off")

    # --------------------------------------------------------------------------
    #   parse_readings
    # --------------------------------------------------------------------------

    def parse_readings(self, line: str) -> bool:
        """Parse the ASCII string `line` as received from the Arduino into
        separate variables and store these into the `state` ring buffers.

        Returns:
            True when successful, False otherwise.
        """
        parts = line.strip("\n").split("\t")
        N_FIELDS = 4

        try:
            for idx, sensor in enumerate(self.state.INA228_sensors):
                sensor.time.append(int(parts[0]) * 1e-3)
                sensor.V_bus.append(float(parts[idx * N_FIELDS + 1]))
                sensor.V_shunt.append(float(parts[idx * N_FIELDS + 2]) * 1e-3)
                sensor.I.append(float(parts[idx * N_FIELDS + 3]) * 1e-3)
                sensor.R.append(float(parts[idx * N_FIELDS + 4]))

        except IndexError:
            pft("Received an incorrect number of values from the Arduino.")
            return False
        except ValueError:
            pft("Failed to convert Arduino data into numeric values.")
            return False

        return True

    # --------------------------------------------------------------------------
    #   listen_to_Arduino
    # --------------------------------------------------------------------------

    def listen_to_Arduino(self) -> int:
        """Listen to the Arduino for new readings being broadcast over the
        serial port. The Arduino must have received the `turn_on()` command
        in order for it to send out these readings.

        This method is blocking until we received enough data to fill up the
        ring buffers with all new data, or until communication timed out.

        Returns:
            The number of newly appended data rows.
        """

        new_rows_count = 0
        while True:
            try:
                _success, line = self.readline(raises_on_timeout=True)
            except serial.SerialException:
                print("Communication timed out. ", end="")
                if new_rows_count == 0:
                    print("No new data was appended to the ring buffers.")
                else:
                    print("New data was appended to the ring buffers.")
                break

            if not isinstance(line, str):
                pft("Data received from the Arduino was not an ASCII string.")
                break

            if not self.parse_readings(line):
                break

            new_rows_count += 1
            if new_rows_count == self.state.capacity:
                break

        return new_rows_count
