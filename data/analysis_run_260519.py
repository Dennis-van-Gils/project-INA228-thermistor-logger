#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "20-05-2026"

import matplotlib.pyplot as plt

import ThermistorData as td

# Plot lay-out
plt.style.use("default")
# plt.style.use("dark_background")
# plt.rcParams["grid.color"] = "gray"
plt.rcParams["font.size"] = 12
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 14
linestyle_args = {
    "linestyle": "-",
    "linewidth": 3,
    "marker": "none",
    "markersize": 8,
}
figure_args = {"figsize": (16, 10), "dpi": 90}

# Load calibration fit reports
fit_report_0x40 = td.SteinhartHartFitReport(
    "run_260519/SteinhartHartFitReport_0x40_260515.json"
)
fit_report_0x41 = td.SteinhartHartFitReport(
    "run_260519/SteinhartHartFitReport_0x41_260515.json"
)
fit_report_0x44 = td.SteinhartHartFitReport(
    "run_260519/SteinhartHartFitReport_0x44_260515.json"
)

# Load data
data = td.ThermistorData("run_260519/260519_224424.txt")

# Plot
fig = plt.figure(**figure_args)
ax0 = fig.add_subplot(2, 1, 1)
ax1 = fig.add_subplot(2, 1, 2)
fig.suptitle(data.filename)

for sensor_idx, sensor in enumerate(data.sensors):

    fit_report = td.SteinhartHartFitReport()
    if sensor.address == "0x40":
        fit_report = fit_report_0x40
    elif sensor.address == "0x41":
        fit_report = fit_report_0x41
    elif sensor.address == "0x44":
        fit_report = fit_report_0x44
    elif sensor.address == "0x45":
        continue  # Broken sensor: ignore

    temp_K = td.steinhart_hart(sensor.R, fit_report.coeffs)

    ax0.plot(
        sensor.time,
        sensor.R,
        label=sensor.address,
        **linestyle_args,
    )
    ax1.plot(
        sensor.time,
        temp_K + td.ABS_ZERO_IN_DEG_C,
        label=sensor.address,
        **linestyle_args,
    )

ax0.set_xlabel("time (sec)")
ax0.set_ylabel("R (\u03a9)")
ax0.legend()

ax1.set_xlabel("time (sec)")
ax1.set_ylabel("T (\u00b0C)")
ax1.legend()

plt.show()

if 1:
    fig.savefig(f"{data.filename}.png", dpi=120)
    fig.savefig(f"{data.filename}.pdf")

    ax0.set_xlim(8000, 10500)
    ax0.set_ylim(25000, 27000)
    ax1.set_xlim(8000, 10500)
    ax1.set_ylim(20.5, 20.9)

    fig.savefig(f"{data.filename} zoom.png", dpi=120)
    fig.savefig(f"{data.filename} zoom.pdf")
