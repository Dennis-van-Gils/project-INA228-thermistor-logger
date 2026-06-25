#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main control program and graphical user interface for an Arduino programmed
as a Thermistor Logger. It will log and plot in real-time the resistance,
current and voltage values of each thermistor.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "07-05-2026"
__version__ = "1.0"
# pylint: disable=missing-function-docstring, unnecessary-lambda
# pylint: disable=multiple-statements

import os
import sys
from pathlib import Path

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Slot  # type: ignore

import psutil
import numpy as np
import pyqtgraph as pg
import qtawesome as qta

from dvg_debug_functions import tprint, dprint, ANSI
from dvg_pyqtgraph_threadsafe import (
    HistoryChartCurve,
    ThreadSafeCurve,
    LegendSelect,
    PlotManager,
)
from dvg_pyqt_filelogger import FileLogger
import dvg_pyqt_controls as controls
from dvg_ringbuffer import RingBuffer
from dvg_devices.Picotech_PT104_protocol_UDP import Picotech_PT104
from dvg_devices.Picotech_PT104_qdev import Picotech_PT104_qdev

from ThermistorLoggerArduino import (
    ThermistorLoggerSerial,
    ThermistorLoggerTelnet,
)
from ThermistorLoggerArduino_qdev import ThermistorLoggerArduino_qdev

# Ensure we can import sibling package `data` when running this script directly.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data.ThermistorData import (  # type: ignore
    ABS_ZERO_IN_DEG_C,
    SteinhartHartFitReport,
    steinhart_hart,
)

# Constants
CHART_CAPACITY = int(1e4)  # [number of points]

# Global flags
TRY_USING_OPENGL = True
USE_LARGER_TEXT = False

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

print(f"{qtpy.API_NAME:9s} {qtpy.QT_VERSION}")  # type: ignore
print(f"PyQtGraph {pg.__version__}")

if TRY_USING_OPENGL:
    try:
        import OpenGL.GL as gl  # pylint: disable=unused-import
        from OpenGL.version import __version__ as gl_version
    except Exception:  # pylint: disable=broad-except
        print("PyOpenGL  not found")
        print("To install: `conda install pyopengl` or `pip install pyopengl`")
    else:
        print(f"PyOpenGL  {gl_version}")
        pg.setConfigOptions(useOpenGL=True)
        pg.setConfigOptions(antialias=True)
        pg.setConfigOptions(enableExperimental=True)
else:
    print("PyOpenGL  disabled")

# Global pyqtgraph configuration
# pg.setConfigOptions(leftButtonPan=False)
pg.setConfigOption("foreground", "#EEE")

# ------------------------------------------------------------------------------
#   current_date_time_strings
# ------------------------------------------------------------------------------


def current_date_time_strings():
    cur_date_time = QtCore.QDateTime.currentDateTime()
    return (
        cur_date_time.toString("dd-MM-yyyy"),  # Date
        cur_date_time.toString("HH:mm:ss"),  # Time
    )


# ------------------------------------------------------------------------------
#   scan_fit_reports
# ------------------------------------------------------------------------------


def scan_fit_reports(
    folder: Path,
) -> dict[str, SteinhartHartFitReport]:
    """Load Steinhart-Hart fit reports keyed by sensor address."""
    reports_by_address: dict[str, SteinhartHartFitReport] = {}

    if not folder.is_dir():
        print(f"Fit reports folder not found: {folder}")
        return reports_by_address

    report_paths = sorted(folder.glob("SteinhartHartFitReport*.json"))
    if not report_paths:
        print(f"No fit reports found in: {folder}")
        return reports_by_address

    for report_path in report_paths:
        try:
            fit_report = SteinhartHartFitReport(report_path)
            sensor_address = fit_report.sensor_address.strip()
            if sensor_address:
                reports_by_address[sensor_address] = fit_report
                dprint(
                    "Loaded fit report "
                    f"{report_path.name} for sensor {sensor_address}",
                    ANSI.YELLOW,
                )
                print(fit_report)
        except Exception as err:  # pylint: disable=broad-except
            print(f"Could not load fit report {report_path.name}: {err}")

    return reports_by_address


# ------------------------------------------------------------------------------
#   resistance_to_temperature_K
# ------------------------------------------------------------------------------


def resistance_to_temperature_K(
    R: np.ndarray,
    fit_report: SteinhartHartFitReport,
    warned_addresses: set[str] | None = None,
    sample_time_s: float | None = None,
) -> np.ndarray:
    """Convert thermistor resistances ``R`` in Ohm to temperatures in Kelvin
    using the Steinhart-Hart fit coefficients from ``fit_report``.

    Return a `numpy.nan` temperature value for each value of ``R`` that is
    outside of the calibrated range. Issue a warning at the first occurrence of
    an out-of-calibration resistance value per thermistor.
    """
    temp_K = np.full_like(R, np.nan, dtype=float)
    finite_positive = np.isfinite(R) & (R > 0)
    valid = finite_positive.copy()

    valid_R_min, valid_R_max = fit_report.calibrated_range_R
    range_is_valid = (
        np.isfinite(valid_R_min)
        and np.isfinite(valid_R_max)
        and (valid_R_min <= valid_R_max)
    )
    if range_is_valid:
        valid &= (R >= valid_R_min) & (R <= valid_R_max)

        out_of_range = finite_positive & ~valid
        if np.any(out_of_range):
            sensor_address = fit_report.sensor_address or "<unknown>"
            should_warn = (
                warned_addresses is None
                or sensor_address not in warned_addresses
            )
            if should_warn:
                str_cur_date, str_cur_time = current_date_time_strings()
                sample_info = (
                    f", sample t={sample_time_s:.3f} s"
                    if sample_time_s is not None
                    else ""
                )
                dprint(
                    "Out-of-calibration resistance detected for "
                    f"sensor {sensor_address} at {str_cur_date} "
                    f"{str_cur_time}{sample_info}.",
                    ANSI.RED,
                )
                if warned_addresses is not None:
                    warned_addresses.add(sensor_address)

    if not np.any(valid):
        return temp_K

    temp_K[valid] = np.asarray(
        steinhart_hart(R[valid], fit_report.coeffs),
        dtype=float,
    )

    return temp_K


# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(
        self,
        qdev: ThermistorLoggerArduino_qdev,
        qdev_pt104: Picotech_PT104_qdev,
        qlog: FileLogger,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.qdev = qdev
        self.qdev.signal_DAQ_updated.connect(self.update_GUI)
        self.qdev_pt104 = qdev_pt104
        self.qlog = qlog
        self.sensors = self.qdev.dev.state.sensors  # Shorthand
        self.fit_reports_by_address = scan_fit_reports(
            Path(__file__).resolve().parent / "fit_reports"
        )
        self.warned_out_of_calibration_addresses: set[str] = set()
        self.calibrated_sensor_addresses = [
            sensor.address
            for sensor in self.sensors
            if sensor.address in self.fit_reports_by_address
        ]

        self.do_update_readings_GUI = True
        """Update the GUI elements corresponding to the Arduino readings, like
        textboxes and charts?"""

        self.setWindowTitle("Thermistor Logger")
        self.setGeometry(40, 60, 960, 660)
        self.setStyleSheet(controls.SS_TEXTBOX_READ_ONLY + controls.SS_GROUP)

        # -------------------------
        #   Top frame
        # -------------------------

        # Left box
        self.qlbl_update_counter = QtWid.QLabel("0")
        self.qlbl_DAQ_rate_1 = QtWid.QLabel("DAQ: nan blocks/s")
        self.qlbl_DAQ_rate_1.setStyleSheet("QLabel {min-width: 7em}")
        self.qlbl_DAQ_rate_2 = QtWid.QLabel("DAQ: nan Hz")
        self.qlbl_DAQ_rate_2.setStyleSheet("QLabel {min-width: 7em}")
        self.qlbl_recording_time = QtWid.QLabel()

        vbox_left = QtWid.QVBoxLayout()
        vbox_left.addWidget(self.qlbl_update_counter, stretch=0)
        vbox_left.addStretch(1)
        vbox_left.addWidget(self.qlbl_recording_time, stretch=0)
        vbox_left.addWidget(self.qlbl_DAQ_rate_1, stretch=0)
        vbox_left.addWidget(self.qlbl_DAQ_rate_2, stretch=0)

        # Middle box
        self.qlbl_title = QtWid.QLabel("Thermistor Logger")
        self.qlbl_title.setFont(
            QtGui.QFont(
                "Palatino",
                20 if USE_LARGER_TEXT else 14,
                weight=QtGui.QFont.Weight.Bold,
            )
        )
        self.qlbl_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.qlbl_cur_date_time = QtWid.QLabel("00-00-0000    00:00:00")
        self.qlbl_cur_date_time.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )

        self.qpbt_record = controls.create_Toggle_button(
            "Click to start recording to file", minimumHeight=40
        )
        self.qpbt_record.setMinimumWidth(400)
        # pylint: disable-next=E1101
        self.qpbt_record.clicked.connect(lambda state: qlog.record(state))

        self.qlbl_calibration_status = QtWid.QLabel()
        self.qlbl_calibration_status.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        self.qlbl_calibration_status.setWordWrap(True)
        if self.calibrated_sensor_addresses:
            self.qlbl_calibration_status.setText(
                "Calibration loaded for: "
                + ", ".join(self.calibrated_sensor_addresses)
            )
        else:
            self.qlbl_calibration_status.setText("Calibration loaded for: none")

        vbox_middle = QtWid.QVBoxLayout()
        vbox_middle.addWidget(self.qlbl_title)
        vbox_middle.addWidget(self.qlbl_cur_date_time)
        vbox_middle.addWidget(self.qpbt_record)
        vbox_middle.addWidget(self.qlbl_calibration_status)

        # Right box
        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "parent": self,
        }
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)  # pylint: disable=E1101
        self.qpbt_exit.setMinimumHeight(30)
        self.qlbl_GitHub = QtWid.QLabel(
            f'<a href="{__url__}">GitHub source</a>', **p
        )
        self.qlbl_GitHub.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.qlbl_GitHub.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.qlbl_GitHub.setOpenExternalLinks(True)

        vbox_right = QtWid.QVBoxLayout()
        vbox_right.setSpacing(4)
        vbox_right.addWidget(self.qpbt_exit, stretch=0)
        vbox_right.addStretch(1)
        vbox_right.addWidget(QtWid.QLabel(__author__, **p))
        vbox_right.addWidget(self.qlbl_GitHub)
        vbox_right.addWidget(QtWid.QLabel(f"v{__version__}", **p))

        # Round up top frame
        hbox_top = QtWid.QHBoxLayout()
        hbox_top.addLayout(vbox_left, stretch=0)
        hbox_top.addStretch(1)
        hbox_top.addLayout(vbox_middle, stretch=0)
        hbox_top.addStretch(1)
        hbox_top.addLayout(vbox_right, stretch=0)

        # -------------------------
        #   Bottom frame
        # -------------------------

        # GraphicsLayoutWidget
        self.gw = pg.GraphicsLayoutWidget()

        p = {
            "color": "#EEE",
            "font-size": "20pt" if USE_LARGER_TEXT else "10pt",
        }

        self.pi_R: pg.PlotItem = self.gw.addPlot(row=0, col=0)  # type: ignore
        """PlotItem `Resistance: R`"""
        self.pi_R.setLabel("left", text="R (\u03a9)", **p)
        self.pi_R.enableAutoRange(axis="y")  # type: ignore

        self.pi_T: pg.PlotItem = self.gw.addPlot(row=1, col=0)  # type: ignore
        """PlotItem `Temperature: T`"""
        self.pi_T.setLabel("left", text="T (\u00b0C)", **p)
        self.pi_T.enableAutoRange(axis="y")  # type: ignore

        self.pi_all = [self.pi_R, self.pi_T]
        """List of all PlotItems"""

        for plot_item in self.pi_all:
            plot_item.setClipToView(True)
            plot_item.showGrid(x=1, y=1)
            plot_item.setLabel("bottom", text="history (sec)", **p)

            if USE_LARGER_TEXT:
                font = QtGui.QFont()
                font.setPixelSize(26)
                plot_item.getAxis("bottom").setTickFont(font)
                plot_item.getAxis("bottom").setStyle(tickTextOffset=20)
                plot_item.getAxis("bottom").setHeight(90)
                plot_item.getAxis("left").setTickFont(font)
                plot_item.getAxis("left").setStyle(tickTextOffset=20)
                plot_item.getAxis("left").setWidth(120)

        # -------------------------
        #   Create history charts
        # -------------------------

        # fmt: off
        pen_width = 5
        pen_1 = pg.mkPen(color=[255,  10,  10], width=pen_width)
        pen_2 = pg.mkPen(color=[ 40, 250,  40], width=pen_width)
        pen_3 = pg.mkPen(color=[  0, 255, 255], width=pen_width)
        pen_4 = pg.mkPen(color=[254,   0, 154], width=pen_width)
        pen_5 = pg.mkPen(color=[255, 255, 255], width=pen_width)
        pens = [pen_1, pen_2, pen_3, pen_4, pen_5]
        # fmt: on

        self.tscurves_R: list[ThreadSafeCurve] = []
        """List of ThreadSafeCurves `Resistance: R [Ohm]`"""

        self.tscurves_T: list[ThreadSafeCurve] = []
        """List of ThreadSafeCurves `Temperature: T ['C]`"""

        self.tscurves_T_thermistors: list[ThreadSafeCurve | None] = []
        """Sub-set of ``tscurves_T``: Thermistor temperature ['C]. A list item
        with value ``None`` indicates a missing fit report."""

        for idx, sensor in enumerate(self.sensors):
            self.tscurves_R.append(
                HistoryChartCurve(
                    capacity=CHART_CAPACITY,
                    linked_curve=self.pi_R.plot(
                        pen=pens[idx],
                        name=f"Sensor {sensor.address}",
                    ),
                )
            )

            fit_report = self.fit_reports_by_address.get(sensor.address)
            if fit_report is None:
                self.tscurves_T_thermistors.append(None)
                continue

            temp_curve = HistoryChartCurve(
                capacity=CHART_CAPACITY,
                linked_curve=self.pi_T.plot(
                    pen=pens[idx],
                    name=f"Sensor {sensor.address}",
                ),
            )
            self.tscurves_T_thermistors.append(temp_curve)
            self.tscurves_T.append(temp_curve)

        self.tscurve_T_PT104 = HistoryChartCurve(
            capacity=CHART_CAPACITY,
            linked_curve=self.pi_T.plot(
                pen=pens[4],
                name="PT-104",
            ),
        )
        self.tscurves_T.append(self.tscurve_T_PT104)

        self.tscurves_all = self.tscurves_R + self.tscurves_T
        """List of all ThreadSafeCurves"""

        # -------------------------
        #   Legend
        # -------------------------

        legend_all = LegendSelect(
            linked_curves=self.tscurves_R + [self.tscurve_T_PT104]
        )
        legend_all.grid.setVerticalSpacing(0)
        self.qgrp_legend = QtWid.QGroupBox("Legend")
        self.qgrp_legend.setLayout(legend_all.grid)

        # -------------------------
        #   PlotManager
        # -------------------------

        self.plot_manager = PlotManager(parent=self)
        self.plot_manager.add_autorange_buttons(linked_plots=self.pi_all)
        self.plot_manager.add_preset_buttons(
            linked_plots=self.pi_all,
            linked_curves=self.tscurves_all,
            presets=[
                {
                    "button_label": "1:00",
                    "x_axis_label": "history (sec)",
                    "x_axis_divisor": 1,
                    "x_axis_range": (-60, 0),
                },
                {
                    "button_label": "5:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-5, 0),
                },
                {
                    "button_label": "10:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-10, 0),
                },
                {
                    "button_label": "30:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-30, 0),
                },
                {
                    "button_label": "60:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-60, 0),
                },
            ],
        )
        self.plot_manager.add_clear_button(linked_curves=self.tscurves_all)
        self.plot_manager.perform_preset(1)

        qgrp_history = QtWid.QGroupBox("History")
        qgrp_history.setLayout(self.plot_manager.grid)

        # -------------------------
        # -------------------------

        # 'Readings'
        p = {"readOnly": True, "maximumWidth": 112 if USE_LARGER_TEXT else 63}
        self.timestamp = QtWid.QLineEdit(**p)

        self.qlins_R: list[QtWid.QLineEdit] = []
        self.qlins_T: list[QtWid.QLineEdit] = []
        self.qlins_I: list[QtWid.QLineEdit] = []
        self.qlins_V: list[QtWid.QLineEdit] = []
        self.qlins_T_die: list[QtWid.QLineEdit] = []

        for sensor in self.sensors:
            self.qlins_R.append(QtWid.QLineEdit(**p))
            self.qlins_T.append(QtWid.QLineEdit(**p))
            self.qlins_I.append(QtWid.QLineEdit(**p))
            self.qlins_V.append(QtWid.QLineEdit(**p))
            self.qlins_T_die.append(QtWid.QLineEdit(**p))

        self.qpbt_running = controls.create_Toggle_button(
            "Running", checked=True
        )
        # pylint: disable-next=E1101
        self.qpbt_running.clicked.connect(
            lambda state: self.process_qpbt_running(state)
        )

        # fmt: off
        i = 0
        grid = QtWid.QGridLayout()
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.qpbt_running              , i, 0, 1, 3)
        grid.addWidget(
            QtWid.QLabel(
                "Time",
                alignment=(QtCore.Qt.AlignmentFlag.AlignRight |
                           QtCore.Qt.AlignmentFlag.AlignVCenter)
            )                                         , i, 3)
        grid.addWidget(self.timestamp                 , i, 4)
        grid.addWidget(QtWid.QLabel("sec")            , i, 5); i+=1
        grid.addWidget(QtWid.QLabel("")               , i, 0)
        grid.addWidget(QtWid.QLabel("R (\u03a9)")     , i, 1)
        grid.addWidget(QtWid.QLabel("T (\u00b0C)")    , i, 2)
        grid.addWidget(QtWid.QLabel("I (mA)")         , i, 3)
        grid.addWidget(QtWid.QLabel("V (V)")          , i, 4)
        grid.addWidget(QtWid.QLabel("T_die (\u00b0C)"), i, 5); i+=1

        for idx, sensor in enumerate(self.sensors):
            grid.addWidget(QtWid.QLabel(sensor.address), i, 0)
            grid.addWidget(self.qlins_R[idx]           , i, 1)
            grid.addWidget(self.qlins_T[idx]           , i, 2)
            grid.addWidget(self.qlins_I[idx]           , i, 3)
            grid.addWidget(self.qlins_V[idx]           , i, 4)
            grid.addWidget(self.qlins_T_die[idx]       , i, 5)
            i+=1
        # fmt: on

        qgrp_readings = QtWid.QGroupBox("Readings")
        qgrp_readings.setLayout(grid)

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(
            qgrp_history,
            stretch=0,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignLeft,
        )
        hbox.addWidget(
            self.qgrp_legend,
            stretch=0,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignLeft,
        )
        hbox.addStretch(1)

        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(qgrp_readings)
        vbox.addLayout(hbox, 0)
        vbox.addWidget(
            qdev_pt104.qgrp,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignLeft,
        )  # GUI Picotech PT-104
        vbox.addStretch(1)

        # Round up bottom frame
        hbox_bot = QtWid.QHBoxLayout()
        hbox_bot.addWidget(self.gw, 1)
        hbox_bot.addLayout(vbox, 0)

        # -------------------------
        #   Round up full window
        # -------------------------

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox_top, stretch=0)
        vbox.addSpacerItem(QtWid.QSpacerItem(0, 10))
        vbox.addLayout(hbox_bot, stretch=1)

    # --------------------------------------------------------------------------
    #   Handle controls
    # --------------------------------------------------------------------------

    def update_legend_visibility(self):
        """Legend initially only hides/shows the resistance curves. Make other
        curves follow this visibility."""
        for idx, tscurve_R in enumerate(self.tscurves_R):
            tscurve_T = self.tscurves_T_thermistors[idx]
            if tscurve_T is not None:
                tscurve_T.setVisible(tscurve_R.isVisible())

    @Slot(bool)
    def process_qpbt_running(self, state: bool):
        self.qpbt_running.setText("Running" if state else "Paused")
        self.do_update_readings_GUI = state

    @Slot()
    def update_GUI(self):
        str_cur_date, str_cur_time = current_date_time_strings()
        state = self.qdev.dev.state  # Shorthand

        self.qlbl_cur_date_time.setText(f"{str_cur_date}    {str_cur_time}")
        self.qlbl_update_counter.setText(f"{self.qdev.update_counter_DAQ}")
        self.qlbl_DAQ_rate_1.setText(
            f"DAQ: {self.qdev.obtained_DAQ_rate_Hz:.2f} blocks/s"
        )
        self.qlbl_DAQ_rate_2.setText(
            f"DAQ: {self.qdev.obtained_DAQ_rate_Hz * state.capacity:.1f} Hz"
        )
        self.qlbl_recording_time.setText(
            f"REC: {self.qlog.pretty_elapsed()}"
            if self.qlog.is_recording()
            else ""
        )

        self.update_legend_visibility()

        if (
            self.do_update_readings_GUI
            and state.N_sensors > 0
            and state.sensors[0].time.is_full
        ):
            self.timestamp.setText(f"{self.sensors[0].time[0]:.1f}")
            for idx, sensor in enumerate(self.sensors):
                mean_R = float(np.mean(sensor.R))
                self.qlins_R[idx].setText(f"{mean_R:.0f}")

                fit_report = self.fit_reports_by_address.get(sensor.address)
                if fit_report is None:
                    self.qlins_T[idx].setText("--")
                else:
                    temp_K = resistance_to_temperature_K(
                        np.asarray([mean_R]),
                        fit_report,
                        warned_addresses=self.warned_out_of_calibration_addresses,
                        sample_time_s=float(sensor.time[0]),
                    )[0]
                    self.qlins_T[idx].setText(
                        f"{temp_K + ABS_ZERO_IN_DEG_C:.3f}"
                    )

                self.qlins_I[idx].setText(f"{np.mean(sensor.I) * 1e3:.5f}")
                self.qlins_V[idx].setText(f"{np.mean(sensor.V_bus):.5f}")
                self.qlins_T_die[idx].setText(f"{np.mean(sensor.T_die):.1f}")

            if DEBUG:
                tprint("update_chart")

            for tscurve in self.tscurves_all:
                tscurve.update()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set priority of this process to maximum in the operating system
    print(f"PID: {os.getpid()}\n")
    try:
        proc = psutil.Process(os.getpid())
        if os.name == "nt":
            proc.nice(psutil.REALTIME_PRIORITY_CLASS)  # Windows
        else:
            proc.nice(-20)  # Other
    except Exception:  # pylint: disable=broad-except
        print("Warning: Could not set process to maximum priority.\n")

    # --------------------------------------------------------------------------
    #   Connect to Arduino
    # --------------------------------------------------------------------------

    # Wired
    ard = ThermistorLoggerSerial(ring_buffer_capacity=1)
    ard.auto_connect()

    # Wireless Utwente
    # ard = ThermistorLoggerTelnet(ring_buffer_capacity=1)
    # ard.connect(host="192.168.50.210", port=23)  # Utwente

    # Wireless Mikkers
    # ard = ThermistorLoggerTelnet(ring_buffer_capacity=1)
    # ard.connect(host="192.168.1.124", port=23)  # Mikkers

    if not ard.is_alive:
        print("\nCheck connection and try resetting the Arduino.")
        # print("Exiting...\n")
        # sys.exit(0)
    else:
        ard.begin()
        ard.turn_on()

    # --------------------------------------------------------------------------
    #   Connect to (optional) Picotech PT-104
    # --------------------------------------------------------------------------

    # fmt: off
    IP_ADDRESS    = "10.10.100.2"
    PORT          = 1234
    ENA_channels  = [1, 1, 1, 1]
    gain_channels = [1, 1, 1, 1]
    # fmt: on

    pt104 = Picotech_PT104(name="PT104")
    if pt104.connect(IP_ADDRESS, PORT):
        pt104.begin()
        pt104.start_conversion(ENA_channels, gain_channels)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------

    main_thread = QtCore.QThread.currentThread()
    if isinstance(main_thread, QtCore.QThread):
        main_thread.setObjectName("MAIN")  # For DEBUG info

    if qtpy.PYQT6 or qtpy.PYSIDE6:
        sys.argv += ["-platform", "windows:darkmode=0"]
    app = QtWid.QApplication(sys.argv)
    app.setWindowIcon(qta.icon("mdi6.resistor", color="black"))
    app.setStyle("Fusion")
    if USE_LARGER_TEXT:
        app.setFont(QtGui.QFont(QtWid.QApplication.font().family(), 16))

    # --------------------------------------------------------------------------
    #   Set up multithreaded communication with the Arduino
    # --------------------------------------------------------------------------

    def DAQ_function() -> bool:
        new_rows_count = ard.listen_to_device()

        if new_rows_count != ard.state.capacity:
            return False

        # Add readings to chart history
        time = ard.state.sensors[0].time
        for idx, sensor in enumerate(ard.state.sensors):
            window.tscurves_R[idx].extendData(time, sensor.R)

            fit_report = window.fit_reports_by_address.get(sensor.address)
            tscurve_T = window.tscurves_T_thermistors[idx]
            if fit_report is not None and tscurve_T is not None:
                temp_K = resistance_to_temperature_K(
                    np.asarray(sensor.R),
                    fit_report,
                    warned_addresses=window.warned_out_of_calibration_addresses,
                    sample_time_s=float(time[0]),
                )
                tscurve_T.extendData(time, temp_K + ABS_ZERO_IN_DEG_C)

        # NOTE: The PT-104 has a different DAQ rate than the thermistor
        # read-outs. As long as both are near similar time intervals, we can use
        # the following simplified scheme where we (wrongly) enforce identical
        # timestamps. This approach can fail when the ringbuffer capacity of the
        # thermistors is set to larger than 1 or when the DAQ rates are
        # differing by more than a factor of 2. In that case, a more elaborate
        # scheme using 'sample & hold' interpolation or data decimation is
        # necessary.
        window.tscurve_T_PT104.appendData(time[0], pt104.state.ch1_T)

        # Add readings to the log
        log.update()

        # Work-around for the jobs thread not getting fairly granted a mutex
        # lock on the device mutex `dev.mutex`. It can sometimes wait multiple
        # lock-unlock cycles of the DAQ thread, before the jobs thread is
        # granted a lock. The `QDeviceIO` library should actually be rewritten
        # slightly to make use of a locking queue in combination with a
        # `QWaitCondition` and `wakeAll()`. ChatGPT.
        QtCore.QThread.msleep(10)

        return True

    ard_qdev = ThermistorLoggerArduino_qdev(
        dev=ard,
        DAQ_function=DAQ_function,
        debug=DEBUG,
    )

    # --------------------------------------------------------------------------
    #   Set up multithreaded communication with the PT104
    # --------------------------------------------------------------------------

    pt104_qdev = Picotech_PT104_qdev(
        dev=pt104,
        DAQ_interval_ms=1000,
        debug=DEBUG,
    )
    pt104_qdev.start()

    # --------------------------------------------------------------------------
    #   File logger
    # --------------------------------------------------------------------------

    def write_header_to_log():
        log.write(f"Sensors: {ard.state.sensor_addresses}\n")
        log.write(
            "Die temperature enabled: "
            f"{int(ard.state.die_temperature_enabled)}\n"
        )
        log.write("Time [s]\tPT104 [\u00b0C]")
        for idx, _ in enumerate(ard.state.sensors):
            log.write(f"\tR_{idx} [\u03a9]\tI_{idx} [A]\tV_{idx} [V]")
            if ard.state.die_temperature_enabled:
                log.write(f"\tT_die_{idx} [\u00b0C]")
        log.write("\n")

        # Light up the trigger LED for 1 sec
        ard.write("trigger_led")

    def write_data_to_log():
        data = [ard.state.sensors[0].time]
        fmts = "%.3f"

        # NOTE: The PT-104 has a different DAQ rate than the thermistor
        # read-outs. As long as both are near similar time intervals, we can use
        # the following simplified scheme where we (wrongly) enforce identical
        # timestamps. This approach can fail when the ring buffer capacity of
        # the thermistors is set to larger than 1 or when the DAQ rates are
        # differing by more than a factor of 2. In that case, a more elaborate
        # scheme using 'sample & hold' interpolation or data decimation is
        # necessary.
        ring_buffer_T = RingBuffer(ard.state.capacity)
        ring_buffer_T.extend([pt104.state.ch1_T] * ard.state.capacity)
        data.append(ring_buffer_T)
        fmts += "\t%.3f"

        for sensor in ard.state.sensors:
            data.append(sensor.R)
            data.append(sensor.I)
            data.append(sensor.V_bus)
            fmts += "\t%.0f\t%.5e\t%.5f"

            if ard.state.die_temperature_enabled:
                data.append(sensor.T_die)
                fmts += "\t%.1f"

        np_data = np.column_stack(data)
        log.np_savetxt(np_data, fmts)

    log = FileLogger(
        write_header_function=write_header_to_log,
        write_data_function=write_data_to_log,
    )
    log.signal_recording_started.connect(
        lambda filepath: window.qpbt_record.setText(
            f"Recording to file: {filepath}"
        )
    )
    log.signal_recording_stopped.connect(
        lambda: window.qpbt_record.setText("Click to start recording to file")
    )

    # --------------------------------------------------------------------------
    #   Program termination routines
    # --------------------------------------------------------------------------

    @Slot()
    def notify_connection_lost():
        stop_running()

        window.qlbl_title.setText("! ! !    LOST CONNECTION    ! ! !")
        str_cur_date, str_cur_time = current_date_time_strings()
        str_msg = f"{str_cur_date} {str_cur_time}\nLost connection to Arduino."
        print(f"\nCRITICAL ERROR @ {str_msg}")
        reply = QtWid.QMessageBox.warning(
            window,
            "CRITICAL ERROR",
            str_msg,
            QtWid.QMessageBox.StandardButton.Ok,
        )

        if reply == QtWid.QMessageBox.StandardButton.Ok:
            pass  # Leave the GUI open for read-only inspection by the user

    def stop_running():
        app.processEvents()
        log.close()
        ard_qdev.quit()
        ard.turn_off()
        ard.close()

        if pt104.is_alive:
            pt104_qdev.quit()
            pt104.close()

    def about_to_quit():
        print("\nAbout to quit")
        stop_running()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow(qdev=ard_qdev, qdev_pt104=pt104_qdev, qlog=log)
    window.show()

    ard_qdev.signal_connection_lost.connect(notify_connection_lost)
    ard_qdev.start()
    ard_qdev.unpause_DAQ()

    app.aboutToQuit.connect(about_to_quit)  # pylint: disable=E1101
    sys.exit(app.exec())
