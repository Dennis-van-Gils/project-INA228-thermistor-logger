#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "05-06-2026"

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

# ------------------------------------------------------------------------------
#   Read datas from disk
# ------------------------------------------------------------------------------

datas = [
    td.ThermistorData("260602_calibration/260602_174128_5_constant.txt"),
    td.ThermistorData("260604_calibration/260603_193804_5_constant.txt"),
]

fit_reports = [
    td.SteinhartHartFitReport(
        "260604_calibration/SteinhartHartFitReport_0x40_260605.json"
    ),
    td.SteinhartHartFitReport(
        "260604_calibration/SteinhartHartFitReport_0x41_260605.json"
    ),
    td.SteinhartHartFitReport(
        "260604_calibration/SteinhartHartFitReport_0x44_260605.json"
    ),
    td.SteinhartHartFitReport(
        "260604_calibration/SteinhartHartFitReport_0x45_260605.json"
    ),
]

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------

figs: list[Figure] = []

for sensor_idx, sensor_address in enumerate(datas[0].sensor_addresses):
    fig = plt.figure(**figure_args)
    ax1 = fig.add_subplot(2, 1, 1)
    ax2 = fig.add_subplot(2, 1, 2)
    fig.suptitle(f"Sensor address: {sensor_address}")
    figs.append(fig)

    for data_idx, data in enumerate(datas):
        sensor = data.sensors[sensor_idx]
        color = td.COLOR_MAP[data_idx]
        fit_report = fit_reports[sensor_idx]

        ax1.plot(
            data.PT104,
            sensor.R,
            color=color,
            label=data.filename,
            **linestyle_args,
        )

        fitted_temp_K = td.steinhart_hart(sensor.R, fit_report.coeffs)

        ax2.plot(
            sensor.T_die,
            fitted_temp_K + td.ABS_ZERO_IN_DEG_C,
            color=color,
            label=None,
            **linestyle_args,
        )

    ax1.set_xlabel(r"T$_\mathregular{PT100}$ " "(\u00b0C)")
    ax1.set_ylabel("R (\u03a9)")
    ax1.set_xlim(15.75, 16.25)
    # ax1.set_ylim(12500, 32500)
    ax1.grid(True)
    fig.legend()

    ax2.set_xlabel(r"T$_\mathregular{die}$ " "(\u00b0C)")
    ax2.set_ylabel(r"T$_\mathregular{fit}$ " "(\u00b0C)")
    ax2.set_xlim(24, 31)
    ax2.set_ylim(15.8, 16.2)
    ax2.grid(True)

plt.show()

if 1:  # Save figures to disk?
    for sensor_idx, sensor in enumerate(datas[0].sensors):
        fn_fig = f"260605_T_die_examination/T_die_dependence_{sensor.address}"
        fig = figs[sensor_idx]
        fig.savefig(f"{fn_fig}.png", dpi=120)
        fig.savefig(f"{fn_fig}.pdf")
