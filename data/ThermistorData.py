#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tools for analysing the log files created by the Thermistor Logger control
program, and for creating and handling calibration fit reports.

Provides:
    * Constants
        `ABS_ZERO_DEG_C`
        `COLORMAP`

    * Methods
        `steinhart-hart()`
        `perform_steinhart_hart_fit()`

    * Classes
        `SteinhartHartFitReport()`
        `INA228_Sensor()`
        `ThermistorData()`
        `RT_Ensemble()`
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "12-05-2026"
__version__ = "1.0"

import os
import sys
import re
import json
from pathlib import Path
from tkinter import filedialog
from datetime import datetime

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy.optimize import curve_fit

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
    [0.969, 0.667, 0.118],
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
    SteinhartHartFitReport,
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Perform a Steinhart-Hart fit to thermistor resistance `R [Ohm]` versus
    temperature `T [K]` data.

    Returns
    -------
        fit_report (`SteinhartHartFitReport`):
            Report containing the fit results, like the coefficients (A, B, C),
            the calibrated temperature range and the rms error.

        fitted_temp_K (`np.ndarray[float]`):
            Resulting temperature fit [K] to the passed resistance data.

        residuals_temp_K (`np.ndarray[float]`):
            Temperature residuals from fit [K].
    """
    params, _covariance = curve_fit(steinhart_hart, R, T, p0=initial_guess)
    coeffs = (params[0], params[1], params[2])  # Convert array to tuple

    fitted_temp_K = np.asarray(steinhart_hart(R, coeffs))
    residuals_temp_K = fitted_temp_K - T

    fit_report = SteinhartHartFitReport()
    fit_report.coeffs = coeffs
    fit_report.rmse = np.sqrt(np.mean(residuals_temp_K**2))
    fit_report.calibrated_range_R = (np.min(R), np.max(R))
    fit_report.calibrated_range_T = (
        np.min(fitted_temp_K),
        np.max(fitted_temp_K),
    )

    return fit_report, fitted_temp_K, residuals_temp_K


# ------------------------------------------------------------------------------
#   SteinhartHartFitReport
# ------------------------------------------------------------------------------


class SteinhartHartFitReport:
    """TODO: Work in progress"""

    def __init__(self, filepath: Path | str | None = None):
        self.sensor_address: str = ""
        """Address of the INA228 sensor to which a thermistor is connected"""

        self.date_of_report: str = datetime.now().strftime("%y%m%d_%H%M%S")
        """Date of report generation as %y%m%d_%H%M%S, e.g. 260515_150500
        denoting year 2026, month 5, day 15, hour 15, minute 5, second 0."""

        self.data_sources: list[str] = []
        """List of filenames used as source for the fit"""

        self.calibrated_range_T: tuple[float, float] = (np.nan, np.nan)
        """Calibrated temperature range as (min, max) [K]"""

        self.calibrated_range_R: tuple[float, float] = (np.nan, np.nan)
        """Calibrated resistance range as (min, max) [Ohm]"""

        self.coeffs: tuple[float, float, float] = (np.nan, np.nan, np.nan)
        """Steinhart-Hart coefficients (A, B, C) resulting from the fit"""

        self.rmse: float = np.nan
        """Root-mean-square error of the temperature residuals to the fit [K]"""

        if filepath is not None:
            self.load_from_disk(filepath)

    def __str__(self):
        msg = (
            "-------------------------\n"
            "Steinhart-Hart fit report\n"
            f"Thermistor {self.sensor_address}\n"
            f"Date       {self.date_of_report}\n"
            "-------------------------\n"
            f"  {self.calibrated_range_T[0] + ABS_ZERO_IN_DEG_C:.1f} \u00b0C "
            "\u2264 T \u2264 "
            f"{self.calibrated_range_T[1] + ABS_ZERO_IN_DEG_C:.1f} \u00b0C\n"
            f"  {self.calibrated_range_T[0]:.1f} K "
            "\u2264 T \u2264 "
            f"{self.calibrated_range_T[1]:.1f} K\n"
            f"  {self.calibrated_range_R[0]:.0f} \u03a9 "
            "\u2264 R \u2264 "
            f"{self.calibrated_range_R[1]:.0f} \u03a9\n"
            f"  A = {self.coeffs[0]:.5e}\n"
            f"  B = {self.coeffs[1]:.5e}\n"
            f"  C = {self.coeffs[2]:.5e}\n"
            f"  RMSE: {self.rmse:.3f} K\n"
            "  Data sources:\n"
        )
        for data_source in self.data_sources:
            msg += f"    {data_source}\n"

        return msg

    def save_to_disk(self):
        filepath = Path(
            f"SteinhartHartFitReport_"
            f"{self.sensor_address}_"
            f"{self.date_of_report[:6]}.json"
        )

        payload = {
            "sensor_address": self.sensor_address,
            "date_of_report": self.date_of_report,
            "calibrated_range_T": list(self.calibrated_range_T),
            "calibrated_range_R": list(self.calibrated_range_R),
            "coeffs": list(self.coeffs),
            "rmse": self.rmse,
            "data_sources": self.data_sources,
        }

        with filepath.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        print(f"Saved fit report: {filepath}")

    def load_from_disk(self, filepath: Path | str | None = None):
        if filepath is None:
            filepath = filedialog.askopenfilename(
                filetypes=[("JSON Files", "*.json")],
                title="Open Steinhart-Hart fit report",
            )

        if filepath is None or filepath == "." or filepath == "":
            # User pressed cancel.
            return

        filepath = Path(filepath)
        if not filepath.is_file():
            raise IOError(f"File can not be found: {filepath}")

        with filepath.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        self.sensor_address = payload.get("sensor_address", "")
        self.date_of_report = payload.get("date_of_report", self.date_of_report)
        calibrated_range_T = payload.get("calibrated_range_T", [np.nan, np.nan])
        self.calibrated_range_T = (
            float(calibrated_range_T[0]),
            float(calibrated_range_T[1]),
        )
        calibrated_range_R = payload.get("calibrated_range_R", [np.nan, np.nan])
        self.calibrated_range_R = (
            float(calibrated_range_R[0]),
            float(calibrated_range_R[1]),
        )
        coeffs = payload.get("coeffs", [np.nan, np.nan, np.nan])
        self.coeffs = (float(coeffs[0]), float(coeffs[1]), float(coeffs[2]))
        self.rmse = float(payload.get("rmse", np.nan))
        self.data_sources = [str(x) for x in payload.get("data_sources", [])]

        print(f"Loaded fit report: {filepath}")

    def suptitle(self) -> str:
        """Return a formatted string containing the fit report, useful for
        passing on to a matplotlib figure title."""
        return (
            f"Thermistor {self.sensor_address}\n"
            f"{self.calibrated_range_R[0]:.0f} \u03a9 \u2264 R \u2264 "
            f"{self.calibrated_range_R[1]:.0f} \u03a9, "
            f"{self.calibrated_range_T[0] + ABS_ZERO_IN_DEG_C:.1f} "
            f"\u00b0C \u2264 T \u2264 "
            f"{self.calibrated_range_T[1] + ABS_ZERO_IN_DEG_C:.1f} "
            f"\u00b0C\n"
            f"fit: A={self.coeffs[0]:.5e}, "
            f"B={self.coeffs[1]:.5e}, "
            f"C={self.coeffs[2]:.5e}\n"
            f"RMSE: {self.rmse:.3f} K"
        )


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
            color=cm[-1],
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
#   RT_Ensemble
# ------------------------------------------------------------------------------


class RT_Ensemble:
    """Container for resistance `R [Ohm]` and temperature `T [K]` data to be
    collected and processed as an ensemble.

    NOTE: Temperature `T` is in units of Kelvin.

    Args:
        sensor_address (str):
            Sensor address to which this ensemble belongs to. Useful for
            naming the legend in a plot.
    """

    def __init__(self, sensor_address: str = ""):
        self.sensor_address = sensor_address
        """Sensor address to which this ensemble belongs to"""
        self.data_sources: list[str] = []
        """List of filenames used as source for the ensemble"""
        self.R: npt.NDArray[np.float64] = np.array([])
        """Resistance [Ohm]"""
        self.T: npt.NDArray[np.float64] = np.array([])
        """Temperature [K]"""

    def append(
        self,
        R: npt.NDArray[np.float64],
        T: npt.NDArray[np.float64],
        data_source: str = "",
    ):
        """Append resistance `R [Ohm]` and temperature `T [K]` data to the
        ensemble. The collected data gets automatically resorted in order of
        increasing temperature."""
        self.R = np.append(self.R, R)
        self.T = np.append(self.T, T)
        self.data_sources.append(data_source)

        sorted_idx = np.argsort(self.T)
        self.R = self.R[sorted_idx]
        self.T = self.T[sorted_idx]
