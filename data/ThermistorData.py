#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data analysis tools for post-processing the log files created by the
Thermistor Logger control program.

Provides:
    * Classes
        `INA228_Sensor()`
        `ThermistorData()`
        `Ensemble()`

    * Methods
        `steinhart-hart()`
        `perform_steinhart_hart_fit()`

    * Constants
        `ABS_ZERO_DEG_C`
        `COLORMAP`
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "12-05-2026"
__version__ = "1.0"

import os
import sys
from pathlib import Path
from tkinter import filedialog
import re

import numpy as np
import numpy.typing as npt
from scipy.optimize import curve_fit
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# plt.style.use("default")
plt.style.use("dark_background")
plt.rcParams["grid.color"] = "gray"
plt.rcParams["font.size"] = 12
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 14

# ------------------------------------------------------------------------------
#   Constants
# ------------------------------------------------------------------------------

ABS_ZERO_IN_DEG_C = -273.15  # [K]

COLOR_MAP = [
    [1, 0.0392, 0.0392],
    [0.157, 0.980, 0.157],
    [0, 1, 1],
    [1, 0, 0.604],
    [1, 1, 1],
]
"""E.g., one color for each of the 4 sensor addresses, i.e. thermistors, plus
the color for the PT104 temperature curve."""


# ------------------------------------------------------------------------------
#   steinhart_hart
# ------------------------------------------------------------------------------


def steinhart_hart(
    R: float | npt.NDArray[np.float64],
    A: float | tuple[float, float, float] | npt.NDArray[np.float64],
    B: float = np.nan,
    C: float = np.nan,
) -> float | npt.NDArray[np.float64]:
    """Steinhart-Hart equation relating thermistor resistance `R [Ohm]` to
    temperature `T [K]`:

        T = 1 / [ A + B * ln(R) + C * (ln(R))^3 ],

    where `A`, `B` and `C` are the Steinhart-Hart coefficients.

    Returns:
        Temperature T [K]
    """
    if isinstance(A, (tuple, np.ndarray)):
        coeff_A = A[0]
        coeff_B = A[1]
        coeff_C = A[2]
    else:
        coeff_A = A
        coeff_B = B
        coeff_C = C

    lnR = np.log(R)
    return 1.0 / (coeff_A + coeff_B * lnR + coeff_C * lnR**3)


# ------------------------------------------------------------------------------
#   perform_steinhart_hart_fit
# ------------------------------------------------------------------------------


def perform_steinhart_hart_fit(
    R: npt.NDArray[np.float64],
    T: npt.NDArray[np.float64],
    initial_guess: tuple[float, float, float] = (1e-3, 2e-4, 1e-7),
) -> tuple[
    tuple[float, float, float],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    float,
]:
    """Perform a Steinhart-Hart fit to thermistor resistance `R [Ohm]` versus
    temperature `T [K]` data.

    Returns
    -------
        coeffs (tuple[float, float, float]):
            Steinhart-Hart coefficients (A, B, C).

        fitted_temp_K (np.ndarray[float]):
            Resulting temperature fit [K].

        residuals_temp_K (np.ndarray[float]):
            Temperature residuals from fit [K].

        rmse (float):
            Root-mean-square error of the temperature residuals [K].
    """
    params, _covariance = curve_fit(steinhart_hart, R, T, p0=initial_guess)
    coeffs = (params[0], params[1], params[2])

    # Compute fitted temperatures
    fitted_temp_K = np.asarray(steinhart_hart(R, coeffs))

    # Residuals
    residuals_temp_K = fitted_temp_K - T
    rmse = np.sqrt(np.mean(residuals_temp_K**2))

    return coeffs, fitted_temp_K, residuals_temp_K, rmse


# ------------------------------------------------------------------------------
#   INA228_Sensor
# ------------------------------------------------------------------------------


class INA228_Sensor:
    """Container for the timeseries data of a single INA228 sensor to which a
    thermistor is connected."""

    def __init__(self):
        self.address: str = ""
        """Sensor address as hex string"""

        self.time: npt.NDArray[np.float64] = np.array([])
        """Time [s]"""

        self.R: npt.NDArray[np.float64] = np.array([])
        """Resistance timeseries [Ohm]"""

        self.I: npt.NDArray[np.float64] = np.array([])
        """Current timeseries [I]"""

        self.V: npt.NDArray[np.float64] = np.array([])
        """Voltage timeseries [V]"""

        self.T_die: npt.NDArray[np.float64] = np.array([])
        """Die temperature timeseries of the INA228 chip ['C]"""


# ------------------------------------------------------------------------------
#   ThermistorData
# ------------------------------------------------------------------------------


class ThermistorData:
    """Manages the data as logged to file by the Thermistor Logger control
    program. Contains the timeseries data of all thermistors in member
    `sensors`, and contains the timeseries data of the optional Picotech
    PT-104 temperature probe in member `PT104`.

    Args:
        filepath (`pathlib.Path` | `str` | `None`, optional):
            Path to the log file to open. Opens a file browser when omitted.

    Main attributes:
        sensor_addresses (`list[str]`):
            List of INA228 sensor addresses connected to the Arduino.

        N_sensors (int):
            Number of INA228 sensors connected to the Arduino.

        sensors (`list[INA228_Sensor]`):
            List of all INA228 sensors, each containing timeseries data.

        time (`numpy.ndarray[float])`):
            Time stamp [s].

        PT104 (`numpy.ndarray[float])`):
            Temperature timeseries ['C] as logged by the optional Picotech
            PT-104 probe ['C]. This is a PT100 logger with 0.001 K resolution
            and 0.015 K accuracy.

    Methods:
        read_file()

        quick_plot()
    """

    def __init__(self, filepath: Path | str | None = None):
        self.filepath: str = ""
        """Full file path"""

        self.filename: str = ""
        """Filename without extension"""

        self.header: list[str] = []
        """Header lines"""

        self.sensor_addresses: list[str] = []
        """List of INA228 sensor addresses connected to the Arduino"""

        self.N_sensors: int = 0
        """Number of INA228 sensors/thermistors connected to the Arduino"""

        self.sensors: list[INA228_Sensor] = []
        """List of all INA228 sensors, each containing timeseries data."""

        self.time: npt.NDArray[np.float64] = np.array([])
        """Time [s]"""

        self.PT104: npt.NDArray[np.float64] = np.array([])
        """Temperature timeseries ['C] as logged by the optional Picotech PT-104
        probe ['C]. This is a PT100 logger with 0.001 K resolution and 0.015 K
        accuracy."""

        self.read_file(filepath=filepath)

    # --------------------------------------------------------------------------
    #   read_file
    # --------------------------------------------------------------------------

    def read_file(self, filepath: Path | str | None = None):
        """Read in a log file acquired by the Thermistor Logger control program.

        Args:
            filepath (`pathlib.Path` | `str` | `None`, optional):
                Path to the log file to open. Opens a file browser when omitted.
        """
        if filepath == "" or filepath is None:
            filepath = filedialog.askopenfilename(
                filetypes=[("Text Files", "*.txt")],
                title="Open thermistor log file",
            )
            if filepath is None or filepath == "." or filepath == "":
                # User pressed cancel.
                sys.exit(0)

        if isinstance(filepath, str):
            filepath = Path(filepath)

        if not filepath.is_file():
            raise IOError(f"File can not be found: {filepath}")

        self.filepath = f"{filepath}"
        self.filename = filepath.stem

        with filepath.open(encoding="utf-8") as f:
            # The first two lines are expected to be the header
            try:
                self.header.append(f.readline().strip())
                self.header.append(f.readline().strip())
            except UnicodeDecodeError as e:
                raise TypeError("Unexpected file format.") from e

        # Parse line 1 of the header
        # Expecting: "Sensors: ['0x40', '0x41', '0x44', '0x45']"
        self.sensor_addresses = re.findall(r"0x[0-9A-Fa-f]+", self.header[0])
        self.N_sensors = len(self.sensor_addresses)

        # The remaining lines are expected to contain tab-delimited data values
        try:
            raw_data = np.loadtxt(filepath, skiprows=2, delimiter="\t")
        except ValueError as e:
            raise ValueError("Unexpected file format.") from e

        try:
            self.time = raw_data[:, 0]
            self.PT104 = raw_data[:, 1]
        except IndexError as e:
            raise IndexError("Wrong number of data columns in file.") from e

        # Offset time to always start at 0
        self.time -= self.time[0]

        try:
            N_FIELDS = 3
            for idx, sensor_address in enumerate(self.sensor_addresses):
                sensor = INA228_Sensor()
                sensor.address = sensor_address
                sensor.time = self.time
                sensor.R = raw_data[:, idx * N_FIELDS + 2]
                sensor.I = raw_data[:, idx * N_FIELDS + 3]
                sensor.V = raw_data[:, idx * N_FIELDS + 4]

                self.sensors.append(sensor)
        except IndexError as e:
            raise IndexError("Wrong number of data columns in file.") from e

    # --------------------------------------------------------------------------
    #   quick_plot
    # --------------------------------------------------------------------------

    def quick_plot(self, save_to_disk: bool = False) -> Figure:
        """Plot the timeseries of the thermistors for quick inspection and
        optionally save the plot as image to disk."""

        fig = plt.figure(figsize=(16, 10), dpi=90)
        ax1 = fig.add_subplot(2, 1, 1)
        ax2 = fig.add_subplot(2, 1, 2, sharex=ax1)
        cm = COLOR_MAP
        marker = "-"

        extrema_R = [np.nan, np.nan]
        for idx, sensor in enumerate(self.sensors):
            extrema_R = [
                np.nanmin([extrema_R[0], np.min(sensor.R)]),
                np.nanmax([extrema_R[1], np.max(sensor.R)]),
            ]
            ax1.plot(
                sensor.time,
                sensor.R,
                marker,
                color=cm[idx],
                label=sensor.address,
            )
        ax1.set_xlabel("Time (s)")
        ax1.set_ylabel("R (\u03a9)")
        ax1.grid(True)

        marker = "-"
        ax2.plot(
            self.time,
            self.PT104,
            marker,
            color=cm[4],
            label="PT104",
        )
        ax2.set_xlabel("Time (s)")
        ax2.set_ylabel("T (\u00b0C)")
        ax2.grid(True)

        fig.legend()
        fig.suptitle(
            f"{self.filename}\n\n"
            f"{extrema_R[0]:.0f} \u03a9 \u2264 R \u2264 "
            f"{extrema_R[1]:.0f} \u03a9\n"
            f"{np.min(self.PT104):.1f} \u00b0C \u2264 T \u2264 "
            f"{np.max(self.PT104):.1f} \u00b0C"
        )

        if save_to_disk:
            file_parts = os.path.splitext(self.filepath)
            fig.savefig(f"{file_parts[0]}.png", dpi=120)
            fig.savefig(f"{file_parts[0]}.pdf")

        return fig


# ------------------------------------------------------------------------------
#   Ensemble
# ------------------------------------------------------------------------------


class Ensemble:
    """Container for resistance `R [Ohm]` and temperature `T [K]` data to be
    collected and processed as an ensemble.

    NOTE: Temperature `T` is in units of Kelvin.

    Args:
        address (str):
            Sensor address to which this ensemble belongs to. Useful for
            naming the legend in a plot.
    """

    def __init__(self, address: str = ""):
        self.address = address
        """Sensor address to which this ensemble belongs to."""
        self.R: npt.NDArray[np.float64] = np.array([])
        """Resistance [Ohm]"""
        self.T: npt.NDArray[np.float64] = np.array([])
        """Temperature [K]"""

    def append(self, R: npt.NDArray[np.float64], T: npt.NDArray[np.float64]):
        """Append resistance `R [Ohm]` and temperature `T [K]` data to the
        ensemble. The collected data gets automatically resorted in order of
        increasing temperature."""
        self.R = np.append(self.R, R)
        self.T = np.append(self.T, T)

        sorted_idx = np.argsort(self.T)
        self.R = self.R[sorted_idx]
        self.T = self.T[sorted_idx]
