#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__date__ = "26-08-2026"

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

# ------------------------------------------------------------------------------
#   Read datas from disk
# ------------------------------------------------------------------------------

fit_reports = [
    td.SteinhartHartFitReport(
        "data/example_data/fit_reports/SteinhartHartFitReport_0x40_260605.json"
    ),
    td.SteinhartHartFitReport(
        "data/example_data/fit_reports/SteinhartHartFitReport_0x41_260605.json"
    ),
    td.SteinhartHartFitReport(
        "data/example_data/fit_reports/SteinhartHartFitReport_0x44_260605.json"
    ),
    td.SteinhartHartFitReport(
        "data/example_data/fit_reports/SteinhartHartFitReport_0x45_260605.json"
    ),
]

datas = [
    td.ThermistorData("data/example_data/260714_160136.txt", fit_reports),
    td.ThermistorData("data/example_data/260714_162010.txt", fit_reports),
]

# ------------------------------------------------------------------------------
#   Plot
# ------------------------------------------------------------------------------

figs: list[Figure] = []
for data in datas:
    fig = data.quick_plot_temperatures(save_to_disk=True)
    figs.append(fig)

plt.show()
