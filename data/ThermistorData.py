#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tools to analyse Thermistor Logger files, and to create and handle
calibration fit reports.

This module provides:

- Data containers for log files and fit reports.
- Steinhart-Hart model and fitting helpers.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "12-05-2026"
__version__ = "1.0"

import os
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
    """Evaluate the Steinhart-Hart temperature equation.

    The equation relates thermistor resistance ``R`` to temperature ``T`` in
    Kelvin:

    ``T = 1 / (A + B * ln(R) + C * ln(R)^3)``.

    Parameters
    ----------
    R : float or numpy.ndarray of float64
        Thermistor resistance in Ohm.
    A : float or tuple[float, float, float] or numpy.ndarray of float64
        Either coefficient ``A`` or a sequence ``(A, B, C)``.
    B : float, default numpy.nan
        Coefficient ``B``. Ignored when ``A`` is passed as a 3-element
        sequence.
    C : float, default numpy.nan
        Coefficient ``C``. Ignored when ``A`` is passed as a 3-element
        sequence.

    Returns
    -------
    float or numpy.ndarray of float64
        Temperature in Kelvin.
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
    """Fit Steinhart-Hart coefficients to resistance-temperature data.

    Parameters
    ----------
    R : numpy.ndarray of float64
        Thermistor resistance values in Ohm.
    T : numpy.ndarray of float64
        Reference temperatures in Kelvin.
    initial_guess : tuple[float, float, float], default (1e-3, 2e-4, 1e-7)
        Initial guess for coefficients ``(A, B, C)``.

    Returns
    -------
    fit_report : SteinhartHartFitReport
        Fit report containing coefficients, calibrated ranges, RMSE, and
        metadata placeholders.
    fitted_temp_K : numpy.ndarray of float64
        Modeled temperatures in Kelvin evaluated at input ``R``.
    residuals_temp_K : numpy.ndarray of float64
        Fit residuals in Kelvin, defined as ``fitted_temp_K - T``.
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
    """Container for Steinhart-Hart fit metadata and coefficients.

    Parameters
    ----------
    filepath : pathlib.Path or str or None, optional
        Path to an existing JSON fit report to load. If omitted, an empty
        report instance is created.

    Attributes
    ----------
    sensor_address : str
        INA228 sensor address for the thermistor.
    date_of_report : str
        Report timestamp formatted as ``%y%m%d_%H%M%S``, e.g. 260515_150500
        denoting year 2026, month 5, day 15, hour 15, minute 5, second 0.
    data_sources : list of str
        Source filenames used for the fit.
    calibrated_range_T : tuple[float, float]
        Calibrated temperature range ``(min, max)`` in Kelvin.
    calibrated_range_R : tuple[float, float]
        Calibrated resistance range ``(min, max)`` in Ohm.
    coeffs : tuple[float, float, float]
        Fitted Steinhart-Hart coefficients ``(A, B, C)``.
    rmse : float
        Root-mean-square residual error in Kelvin.
    """

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
            self.read_file(filepath)

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

    def save_file(self):
        """Write the fit report to a JSON file.

        Notes
        -----
        The output filename is formatted as
        ``SteinhartHartFitReport_{sensor_address}_{date}.json`` where ``date``
        uses the first 6 characters of ``date_of_report``.
        """
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

    def read_file(self, filepath: Path | str | None = None):
        """Read fit report fields from a JSON file.

        Parameters
        ----------
        filepath : pathlib.Path or str or None, optional
            Path to the report file. If omitted, a file dialog is shown.
        """
        if filepath == "" or filepath is None:
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

        with filepath.open(encoding="utf-8") as f:
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
        """Build a multi-line summary string for figure titles.

        Returns
        -------
        str
            Formatted fit summary with calibrated ranges, coefficients, and
            RMSE.
        """
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
    """Container for timeseries data from one INA228 thermistor channel to which
    a thermistor is connected.

    Attributes
    ----------
    address : str
        Sensor address represented as a hexadecimal string.
    time : numpy.ndarray of float64
        Time values in seconds.
    R : numpy.ndarray of float64
        Resistance values in Ohm.
    I : numpy.ndarray of float64
        Current values in Ampere.
    V : numpy.ndarray of float64
        Voltage values in Volt.
    T_die : numpy.ndarray of float64
        INA228 die temperature values in degree Celsius.
    """

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
    ``sensors``, and contains the timeseries data of the optional Picotech
    PT-104 temperature probe in member ``PT104``.

    Parameters
    ----------
    filepath : pathlib.Path or str or None, optional
        Path to a logger text file. If omitted, a file dialog is shown.

    Attributes
    ----------
    filepath : str
        Full path to the loaded file.
    filename : str
        Filename stem of the loaded file.
    header : list of str
        Header lines read from the file.
    sensor_addresses : list of str
        INA228 sensor addresses found in the header.
    N_sensors : int
        Number of INA228 sensors represented in the data.
    sensors : list of INA228_Sensor
        Per-sensor containers. Each container holds timeseries data from one
        INA228 sensor to which a thermistor is connected.
    time : numpy.ndarray of float64
        Common time vector in seconds, shifted to start at zero.
    PT104 : numpy.ndarray of float64
        PT-104 reference temperatures in degree Celsius.
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
        """Load in a log file acquired by the Thermistor Logger control program
        into this instance.

        Parameters
        ----------
        filepath : pathlib.Path or str or None, optional
            Path to the log file. If omitted, a file dialog is shown.

        Raises
        ------
        IOError
            If the provided file does not exist.
        TypeError
            If file decoding fails due to unexpected text encoding.
        ValueError
            If numeric parsing fails because the file format is invalid.
        IndexError
            If required data columns are missing.
        """
        if filepath == "" or filepath is None:
            filepath = filedialog.askopenfilename(
                filetypes=[("Text Files", "*.txt")],
                title="Open thermistor log file",
            )
            if filepath is None or filepath == "." or filepath == "":
                # User pressed cancel.
                return

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
        """Create a quick timeseries plot of the thermistor resistances and
        reference temperature.

        Parameters
        ----------
        save_to_disk : bool, default False
            If ``True``, save the plot as PNG and PDF files next to the loaded
            data file.

        Returns
        -------
        matplotlib.figure.Figure
            The created matplotlib figure.
        """

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
    """Container for resistance ``R`` and temperature ``T`` data to be
    collected and processed as an ensemble.

    Notes
    -----
    Temperature values are stored in Kelvin.

    Parameters
    ----------
    sensor_address : str, default ""
        Sensor address associated with this ensemble.

    Attributes
    ----------
    sensor_address : str
        Sensor address associated with this ensemble.
    data_sources : list of str
        Filenames from which appended data originated.
    R : numpy.ndarray of float64
        Resistance values in Ohm.
    T : numpy.ndarray of float64
        Temperature values in Kelvin.
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
        """Append resistance-temperature data and sort by temperature.

        Parameters
        ----------
        R : numpy.ndarray of float64
            Resistance values in Ohm.
        T : numpy.ndarray of float64
            Temperature values in Kelvin.
        data_source : str, default ""
            Optional filename or label for the appended data.
        """
        self.R = np.append(self.R, R)
        self.T = np.append(self.T, T)
        self.data_sources.append(data_source)

        sorted_idx = np.argsort(self.T)
        self.R = self.R[sorted_idx]
        self.T = self.T[sorted_idx]
