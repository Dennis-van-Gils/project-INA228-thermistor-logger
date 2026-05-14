#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "13-05-2026"

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

import ThermistorData as td

if 0:
    # Initial inspection to figure out what data to select for further analysis.
    # We are manually going to chop logs into smaller files that each contain
    # a single temperature ramp, going either up or down.
    data_1 = td.ThermistorData("calibration_260511/260511_151804.txt")
    data_2 = td.ThermistorData("calibration_260511/260512_185755.txt")
    fig_1 = data_1.quick_plot(save_to_disk=True)
    fig_2 = data_2.quick_plot(save_to_disk=True)
    plt.show()

# ------------------------------------------------------------------------------
#   Read data from disk
# ------------------------------------------------------------------------------

data = [
    td.ThermistorData("calibration_260511/260511_151804_ramp_1_up.txt"),
    td.ThermistorData("calibration_260511/260512_185755_ramp_1_up.txt"),
    td.ThermistorData("calibration_260511/260512_185755_ramp_2_down.txt"),
    td.ThermistorData("calibration_260511/260512_185755_ramp_3_up.txt"),
]

if 0:
    for ramp in data:
        ramp.quick_plot(save_to_disk=True)
    plt.show()

# ------------------------------------------------------------------------------
#   Ensemble collect all resistance-temperature (R-T) data over all ramps per
#   thermistor.
#
#   For each thermistor, plot all R-T ramps in their own plot.
# ------------------------------------------------------------------------------

ensembles: list[td.Ensemble] = []
"""List of Ensemble objects, each ensemble belonging to a specific sensor
address, i.e. thermistor."""

# Plot lay-out
linestyle = {
    "marker": ".",
    "linestyle": "none",
    "markersize": 8,
}
p = {"figsize": (16, 10), "dpi": 90}
figs: list[Figure] = []

for sensor_idx, sensor_address in enumerate(data[0].sensor_addresses):
    # Prepare plot
    fig = plt.figure(**p)
    fig.add_subplot(2, 1, 1)
    fig.add_subplot(2, 1, 2)
    figs.append(fig)

    # Collect ensembles
    ensemble = td.Ensemble(sensor_address)

    for ramp_idx, ramp in enumerate(data):
        sensor = ramp.sensors[sensor_idx]
        ensemble.append(
            R=sensor.R,
            T=ramp.PT104 - td.ABS_ZERO_IN_DEG_C,
        )

        axs = fig.get_axes()
        ax = axs[0]
        ax.plot(
            ramp.PT104,
            sensor.R,
            color=td.COLOR_MAP[ramp_idx],
            label=ramp.filename,
            **linestyle,
        )

    ax.set_xlabel("T$_{PT100}$ (\u00b0C)")
    ax.set_ylabel("R (\u03a9)")
    # ax.set_yscale("log")
    ax.set_xlim(15, 40)
    ax.set_ylim(12500, 31000)
    ax.grid(True)

    fig.suptitle(f"Thermistor {sensor_address}")
    fig.legend()

    ensembles.append(ensemble)

# ------------------------------------------------------------------------------
#   For each thermistor's R-T ensemble, fit a Steinhart-Hart equation.
# ------------------------------------------------------------------------------

for sensor_idx, ensemble in enumerate(ensembles):
    print(f"\nThermistor {ensemble.address}")
    print("-" * 18)

    coeffs, fitted_temp_K, residuals_temp_K, rmse = (
        td.perform_steinhart_hart_fit(
            R=ensemble.R,
            T=ensemble.T,
        )
    )

    print("Steinhart-Hart fit")
    print(f"  A = {coeffs[0]:.5e}")
    print(f"  B = {coeffs[1]:.5e}")
    print(f"  C = {coeffs[2]:.5e}")
    print(f"  RMSE: {rmse:.3f} K")

    # Plot fit into R-T figure
    fig = figs[sensor_idx]
    axs = fig.get_axes()
    ax = axs[0]
    ax.plot(
        fitted_temp_K + td.ABS_ZERO_IN_DEG_C,
        ensemble.R,
        "-",
        color="w",
        label="Steinhart-Hart fit",
    )
    fig.legend()
    fig.suptitle(
        f"Thermistor {ensemble.address}\n"
        f"{np.min(ensemble.R):.0f} \u03a9 \u2264 R \u2264 "
        f"{np.max(ensemble.R):.0f} \u03a9, "
        f"{np.min(ensemble.T + td.ABS_ZERO_IN_DEG_C):.1f} \u00b0C \u2264 T \u2264 "
        f"{np.max(ensemble.T + td.ABS_ZERO_IN_DEG_C):.1f} \u00b0C\n"
        f"fit: A={coeffs[0]:.5e}, B={coeffs[1]:.5e}, C={coeffs[2]:.5e}\n"
        f"RMSE: {rmse:.3f} K"
    )

    # Plot residuals from fit in T-R figure per ramp
    for ramp_idx, ramp in enumerate(data):
        sensor = ramp.sensors[sensor_idx]
        fitted_temp_K = td.steinhart_hart(sensor.R, coeffs)
        fitted_temp_C = fitted_temp_K + td.ABS_ZERO_IN_DEG_C

        ax = axs[1]
        ax.plot(
            sensor.R,
            fitted_temp_C - ramp.PT104,
            color=td.COLOR_MAP[ramp_idx],
            label=ramp.filename,
            **linestyle,
        )

    ax = axs[1]
    ax.set_xlabel("R (\u03a9)")
    ax.set_ylabel("residuals from fit (K)")
    ax.set_xlim(12500, 31000)
    ax.set_ylim(-0.35, 0.35)
    ax.grid(True)

plt.show()

# Save figures to disk
if 0:
    for sensor_idx, sensor in enumerate(data[0].sensors):
        fn_fig = f"calibration_260511 sensor {sensor.address}"
        fig = figs[sensor_idx]
        fig.savefig(f"{fn_fig}.png", dpi=120)
        fig.savefig(f"{fn_fig}.pdf")
