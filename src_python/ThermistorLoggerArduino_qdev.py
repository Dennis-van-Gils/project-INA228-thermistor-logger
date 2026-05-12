#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for an Arduino programmed as a Thermistor Logger.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "07-05-2026"
__version__ = "1.0"
# pylint: disable=missing-docstring

from typing import Callable

from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from ThermistorLoggerArduino import ThermistorLoggerBase


class ThermistorLoggerArduino_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    an Arduino programmed as a Thermistor Logger."""

    def __init__(
        self,
        dev: ThermistorLoggerBase,
        DAQ_function: Callable[[], bool],
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: ThermistorLoggerBase  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_TRIGGER.CONTINUOUS,
            DAQ_function=DAQ_function,
            critical_not_alive_count=3,
            debug=debug,
        )
        self.create_worker_jobs(debug=debug)

    # --------------------------------------------------------------------------
    #   Arduino communication functions
    # --------------------------------------------------------------------------

    def turn_on(self):
        """Send instruction to the Arduino to turn on its continuous data
        reporting of all thermistor data over the transport backend (serial or
        telnet).
        """
        self.send(self.dev.turn_on)

    def turn_off(self):
        """Send instruction to the Arduino to turn off its continuous data
        reporting of all thermistor data over the transport backend (serial or
        telnet).
        """
        self.send(self.dev.turn_off)
