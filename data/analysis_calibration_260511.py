#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "13-05-2026"

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import numpy.typing as npt
from scipy.optimize import curve_fit

from ThermistorData import ThermistorData, INA228_Sensor

ABS_ZERO_DEG_C = 273.15  # [K]

if 0:
    # Initial inspection
    fn_1 = "calibration_260511/260511_151804.txt"
    fn_2 = "calibration_260511/260512_185755.txt"
    data_1 = ThermistorData(fn_1)
    data_2 = ThermistorData(fn_2)
    fig_1 = data_1.quick_plot()
    fig_2 = data_2.quick_plot()
    plt.show()

# ------------------------------------------------------------------------------
#   Read data from disk
# ------------------------------------------------------------------------------

fn_ramp_1 = "calibration_260511/260511_151804_ramp_1_up.txt"
fn_ramp_2 = "calibration_260511/260512_185755_ramp_1_up.txt"
fn_ramp_3 = "calibration_260511/260512_185755_ramp_2_down.txt"
fn_ramp_4 = "calibration_260511/260512_185755_ramp_3_up.txt"

filenames = [fn_ramp_1, fn_ramp_2, fn_ramp_3, fn_ramp_4]
data: list[ThermistorData] = []

for filename in filenames:
    data.append(ThermistorData(filename))

if 0:
    for ramp in data:
        ramp.quick_plot()
    plt.show()

# ------------------------------------------------------------------------------
#   For each separate thermistor, plot all resistance-temperature (R-T) ramps in
#   their own plot.
#
#   Also, ensemble collect all R-T data over all ramps per thermistor.
# ------------------------------------------------------------------------------


# Ensemble data
class Ensemble:
    def __init__(self, address: str = ""):
        self.address = address
        self.R: npt.NDArray[np.float64] = np.array([])
        """Resistance [Ohm]"""
        self.T: npt.NDArray[np.float64] = np.array([])
        """Temperature [K]"""


ensembles: list[Ensemble] = []

# Plot lay-out
cm = [
    [1, 0.0392, 0.0392],
    [0.157, 0.980, 0.157],
    [0, 1, 1],
    [1, 0, 0.604],
    [1, 1, 1],
]  # Color map
linestyle = {
    "marker": ".",
    "linestyle": "none",
    "markersize": 8,
}
p = {"figsize": (16, 10), "dpi": 90}
figs: list[Figure] = []

for sensor_idx, sensor_address in enumerate(data[0].sensor_addresses):
    # Collect ensembles
    ensemble = Ensemble(sensor_address)

    # Plot
    fig = plt.figure(**p)
    figs.append(fig)

    ax = fig.add_subplot(1, 1, 1)
    for ramp_idx, ramp in enumerate(data):
        sensor = ramp.sensors[sensor_idx]
        ensemble.R = np.append(ensemble.R, sensor.R)
        ensemble.T = np.append(ensemble.T, ramp.PT104 + ABS_ZERO_DEG_C)

        ax.plot(
            ramp.PT104,
            sensor.R,
            color=cm[ramp_idx],
            label=ramp.filename,
            **linestyle,
        )

    ax.set_xlabel("PT104 (\u00b0C)")
    ax.set_ylabel("R (\u03a9)")
    ax.set_xlim(15, 40)
    ax.set_ylim(12500, 32500)
    ax.grid(True)

    fig.suptitle(f"Thermistor: {sensor_address}")
    fig.legend()

    ensembles.append(ensemble)

# ------------------------------------------------------------------------------
#   For each thermistor's R-T ensemble, fit a Steinhart-Hart equation.
# ------------------------------------------------------------------------------


def steinhart_hart(
    R: npt.NDArray[np.float64],
    coeff_A: float,
    coeff_B: float,
    coeff_C: float,
) -> npt.NDArray[np.float64]:
    """Steinhart-Hart equation for thermistor resistance-temperature curves.

    R      : Resistance [Ohm]
    A, B, C: Steinhart-Hart coefficients
    Returns: Temperature [K]
    """
    lnR = np.log(R)
    return 1.0 / (coeff_A + coeff_B * lnR + coeff_C * lnR**3)


# First order the ensemble data by monotonically increasing temperature to
# prevent plotting artifacts.
for ensemble in ensembles:
    sorted_idx = np.argsort(ensemble.T)
    ensemble.T = ensemble.T[sorted_idx]
    ensemble.R = ensemble.R[sorted_idx]

# Fit Steinhart-Hart equation
for sensor_idx, ensemble in enumerate(ensembles):
    print(f"\nThermistor: {ensemble.address}")
    print("-------------------")

    # Initial parameter guess
    initial_guess = [1e-3, 2e-4, 1e-7]

    # Fit coefficients
    params, covariance = curve_fit(
        steinhart_hart, ensemble.R, ensemble.T, p0=initial_guess
    )
    A, B, C = params

    # Compute fitted temperatures
    fitted_temp_K = steinhart_hart(ensemble.R, A, B, C)
    fitted_temp_C = fitted_temp_K - ABS_ZERO_DEG_C

    # Residuals
    residuals = fitted_temp_K - ensemble.T
    rmse = np.sqrt(np.mean(residuals**2))

    print("Steinhart-Hart fit:")
    print(f"  A = {A:.4e}")
    print(f"  B = {B:.4e}")
    print(f"  C = {C:.4e}")
    print(f"\n  RMSE: {rmse:.4f} K")

    # Plot
    fig = figs[sensor_idx]
    axs = fig.get_axes()
    ax = axs[0]
    ax.plot(
        fitted_temp_C,
        ensemble.R,
        "-",
        color="w",
        label="Steinhart-Hart fit",
    )
    ax.set_yscale("log")
    fig.legend()

plt.show()
