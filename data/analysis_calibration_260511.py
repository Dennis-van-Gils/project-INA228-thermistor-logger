#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "15-05-2026"

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

import ThermistorData as td

if 0:
    # Initial inspection to figure out what data to select for further analysis.
    # We are manually going to chop logs into smaller files that each contain
    # a single temperature ramp, going either up or down, or a constant
    # temperature section.
    data_1 = td.ThermistorData("calibration_260514/260514_154709.txt")
    fig_1 = data_1.quick_plot(save_to_disk=True)
    plt.show()

# Plot lay-out
linestyle_args = {
    "marker": ".",
    "linestyle": "none",
    "markersize": 8,
}
figure_args = {"figsize": (16, 10), "dpi": 90}

# ------------------------------------------------------------------------------
#   Read data from disk
# ------------------------------------------------------------------------------

data = [
    td.ThermistorData("calibration_260511/260511_151804_1_ramp_up.txt"),
    td.ThermistorData("calibration_260511/260512_185755_1_ramp_up.txt"),
    td.ThermistorData("calibration_260511/260512_185755_2_ramp_down.txt"),
    td.ThermistorData("calibration_260511/260512_185755_3_ramp_up.txt"),
]

if 0:
    for ramp in data:
        ramp.quick_plot(save_to_disk=True)
    plt.show()

# ------------------------------------------------------------------------------
#   Collect ensembles of resistance-temperature (R-T) data over all ramps per
#   thermistor
# ------------------------------------------------------------------------------

ensembles: list[td.RT_Ensemble] = []
"""List of RT_Ensemble objects, each ensemble belonging to a specific sensor
address, i.e. thermistor."""

figs: list[Figure] = []

for sensor_idx, sensor_address in enumerate(data[0].sensor_addresses):
    fig = plt.figure(**figure_args)
    ax = fig.add_subplot(2, 1, 1)
    fig.add_subplot(2, 1, 2)
    fig.suptitle(f"Sensor address: {sensor_address}")
    figs.append(fig)

    ensemble = td.RT_Ensemble(sensor_address=sensor_address)
    ensembles.append(ensemble)

    for ramp_idx, ramp in enumerate(data):
        sensor = ramp.sensors[sensor_idx]
        ensemble.append(
            R=sensor.R,
            T=ramp.PT104 - td.ABS_ZERO_IN_DEG_C,
            data_source=ramp.filepath,
        )

        ax.plot(
            ramp.PT104,
            sensor.R,
            color=td.COLOR_MAP[ramp_idx],
            label=ramp.filename,
            **linestyle_args,
        )

    ax.set_xlabel("T$_{PT100}$ (\u00b0C)")
    ax.set_ylabel("R (\u03a9)")
    ax.set_xlim(15, 40)
    ax.set_ylim(12500, 31000)
    ax.grid(True)
    fig.legend()

# ------------------------------------------------------------------------------
#   Fit Steinhart-Hart to each R-T ensemble and save the fit report to disk
# ------------------------------------------------------------------------------

fit_reports: list[td.SteinhartHartFitReport] = []

for sensor_idx, ensemble in enumerate(ensembles):
    (
        fit_report,
        fitted_temp_K,
        residuals_temp_K,
    ) = td.perform_steinhart_hart_fit(R=ensemble.R, T=ensemble.T)

    fit_report.sensor_address = ensemble.sensor_address
    fit_report.data_sources = ensemble.data_sources
    fit_report.save_file()
    fit_reports.append(fit_report)
    print(fit_report)

    fig = figs[sensor_idx]
    fig.suptitle(fit_report.suptitle())
    axs = fig.get_axes()

    # Plot fit into R-T figure
    ax = axs[0]
    ax.plot(
        fitted_temp_K + td.ABS_ZERO_IN_DEG_C,
        ensemble.R,
        "-",
        color="w",
        label="Steinhart-Hart fit",
    )
    fig.legend()

    # Plot residuals from fit per ramp
    ax = axs[1]
    for ramp_idx, ramp in enumerate(data):
        sensor = ramp.sensors[sensor_idx]
        fitted_temp_K = td.steinhart_hart(sensor.R, fit_report.coeffs)
        fitted_temp_C = fitted_temp_K + td.ABS_ZERO_IN_DEG_C

        ax.plot(
            sensor.R,
            fitted_temp_C - ramp.PT104,
            color=td.COLOR_MAP[ramp_idx],
            label=ramp.filename,
            **linestyle_args,
        )

    ax.set_xlabel("R (\u03a9)")
    ax.set_ylabel("residuals from fit (K)")
    ax.set_xlim(12500, 31000)
    ax.set_ylim(-0.35, 0.35)
    ax.grid(True)

plt.show()

if 0:  # Save figures to disk?
    for sensor_idx, fit_report in enumerate(fit_reports):
        fn_fig = (
            f"SteinhartHartFitReport_"
            f"{fit_report.sensor_address}_"
            f"{fit_report.date_of_report[:6]}"
        )

        # Save figure: Full range
        fig = figs[sensor_idx]
        fig.savefig(f"{fn_fig}.png", dpi=120)
        fig.savefig(f"{fn_fig}.pdf")
