#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "07-08-2026"

import os

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

import ThermistorData as td

# Plot lay-out
# plt.style.use("default")
plt.style.use("dark_background")
plt.rcParams["grid.color"] = "gray"
plt.rcParams["font.size"] = 12
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 14
linestyle_args = {
    "marker": ".",
    "linestyle": "none",
    "markersize": 8,
}
figure_args = {"figsize": (16, 10), "dpi": 90}

# Set the current working folder to where this script resides
script_folder = os.path.abspath(os.path.dirname(__file__))
os.chdir(script_folder)

# Output folder for the calibration fit reports
fit_reports_folder = os.path.join(
    script_folder, "demo_calibration", "fit_reports"
)

# ------------------------------------------------------------------------------
#   Read datas from disk
# ------------------------------------------------------------------------------

datas = [
    td.ThermistorData("demo_calibration/260603_193804_1_ramp_up.txt"),
    td.ThermistorData("demo_calibration/260603_193804_2_ramp_down.txt"),
    td.ThermistorData("demo_calibration/260603_193804_3_ramp_up.txt"),
    td.ThermistorData("demo_calibration/260603_193804_4_ramp_down.txt"),
    td.ThermistorData("demo_calibration/260603_193804_5_constant.txt"),
]

# ------------------------------------------------------------------------------
#   Quickly plot the raw timeseries for initial inspection and save to disk
# ------------------------------------------------------------------------------

if 1:
    for data in datas:
        data.quick_plot(save_to_disk=True)
    plt.show()

# ------------------------------------------------------------------------------
#   Collect ensembles of resistance-temperature (R-T) data over all datas per
#   thermistor
# ------------------------------------------------------------------------------

ensembles: list[td.RT_Ensemble] = []
"""List of RT_Ensemble objects, each ensemble belonging to a specific sensor
address, i.e. thermistor."""

figs: list[Figure] = []

for sensor_idx, sensor_address in enumerate(datas[0].sensor_addresses):
    fig = plt.figure(**figure_args)
    ax = fig.add_subplot(2, 1, 1)
    fig.add_subplot(2, 1, 2)
    fig.suptitle(f"Sensor address: {sensor_address}")
    figs.append(fig)

    ensemble = td.RT_Ensemble(sensor_address=sensor_address)
    ensembles.append(ensemble)

    for data_idx, data in enumerate(datas):
        sensor = data.sensors[sensor_idx]
        ensemble.append(
            R=sensor.R,
            T=data.PT104 - td.ABS_ZERO_IN_DEG_C,
            data_source=data.filepath,
        )

        ax.plot(
            data.PT104,
            sensor.R,
            color=td.COLOR_MAP[data_idx],
            label=data.filename,
            **linestyle_args,
        )

    ax.set_xlabel(r"T$_\mathregular{PT100}$ " "(\u00b0C)")
    ax.set_ylabel("R (\u03a9)")
    ax.set_xlim(15, 40)
    ax.set_ylim(12500, 32500)
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
    fit_report.save_file(fit_reports_folder)
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

    # Plot residuals from fit per data
    ax = axs[1]
    for data_idx, data in enumerate(datas):
        sensor = data.sensors[sensor_idx]
        fitted_temp_K = td.steinhart_hart(sensor.R, fit_report.coeffs)
        fitted_temp_C = fitted_temp_K + td.ABS_ZERO_IN_DEG_C

        ax.plot(
            sensor.R,
            fitted_temp_C - data.PT104,
            color=td.COLOR_MAP[data_idx],
            label=data.filename,
            **linestyle_args,
        )

    ax.set_xlabel("R (\u03a9)")
    ax.set_ylabel("residuals from fit (K)")
    ax.set_xlim(12500, 32500)
    ax.set_ylim(-0.2, 0.2)
    ax.grid(True)

plt.show()

if 1:  # Save figures to disk?
    print("Saving figures to disk... ", end="")
    for sensor_idx, fit_report in enumerate(fit_reports):
        fn_fig = os.path.join(
            fit_reports_folder,
            (
                f"SteinhartHartFitReport_"
                f"{fit_report.sensor_address}_"
                f"{fit_report.date_of_report[:6]}"
            ),
        )

        # Save figure: Full range
        fig = figs[sensor_idx]
        fig.savefig(f"{fn_fig}.png", dpi=120)
        fig.savefig(f"{fn_fig}.pdf")

        # Save figure: Zoomed in to constant temperature section
        fn_fig += "_stability"

        # Round R to units of 50 Ohm
        R_min = np.floor(np.min(datas[4].sensors[sensor_idx].R) / 50) * 50
        R_max = np.ceil(np.max(datas[4].sensors[sensor_idx].R) / 50) * 50

        axs = fig.get_axes()
        axs[0].set_xlim(15.96, 16.12)
        axs[0].set_ylim(R_min, R_max)
        axs[1].set_xlim(R_min, R_max)
        axs[1].set_ylim(-0.2, 0.2)

        fig.savefig(f"{fn_fig}.png", dpi=120)
        fig.savefig(f"{fn_fig}.pdf")

    print("done.")
