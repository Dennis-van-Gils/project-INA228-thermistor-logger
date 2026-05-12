#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provides base class TelnetServerDevice(), offering blocking I/O methods to
communicate with a telnet server device. Instances of this class will tie in
nicely with :class:`dvg_qdeviceio.QDeviceIO`.

These base classes are meant to be inherited into your own specific *Device*
class.

This module is a minimally functioning stub.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-INA228-thermistor-logger"
__date__ = "11-05-2026"
__version__ = "0.1.0"
# pylint: disable=broad-except

import sys
from typing import Union, Tuple

import telnetlib3

from dvg_debug_functions import dprint, ANSI, print_fancy_traceback as pft


class TelnetServerDevice:
    """This class provides blocking I/O methods for a telnet server device by
    wrapping the `telnetlib3 <https://telnetlib3.readthedocs.io/en/latest>`_
    library.

    Instances of this class will tie in nicely with
    :class:`dvg_qdeviceio.QDeviceIO`.

    Args:
        long_name (:obj:`str`, optional):
            Long display name of the device in a general sense. E.g.,
            `"Wemos ESP32-S3"`.

            Default: `"Telnet Server Device"`

        name (:obj:`str`, optional):
            Short display name for the device. E.g., `"ESP32"` or `"blinker"`.

            Default: `"Dev_1"`

    .. rubric:: Attributes:

    Attributes:
        long_name (:obj:`str`):
            Long display name of the device in a general sense. E.g,
            `""Wemos ESP32-S3"`.

        name (:obj:`str`):
            Short display name for the device. E.g., `"ESP32"` or `"blinker"`.

        telnet_settings (:obj:`dict`):
            Dictionary of keyword arguments to be passed directly to
            :class:`telnetlib3.sync.TelnetConnection` when calling method
            `connect()`.

            Default: `{"timeout": 4, "encoding": "utf8",}`

        conn (:class:`telnetlib3.sync.TelnetConnection` | :obj:`None`):
            Will be set to a :class:`telnetlib3.sync.TelnetConnection` instance
            when a connection has been established. Otherwise: :obj:`None`.

        is_alive (:obj:`bool`):
            Is the connection alive? I.e., Can we communicate?

    Methods:
        connect()

        close()

        readline()

        write()

        query()
    """

    def __init__(
        self,
        name="Dev_1",
        long_name="Telnet Server Device",
    ):
        self.long_name = long_name
        self.name = name

        # Default telnet settings
        self.telnet_settings = {
            "timeout": 4,
            "encoding": "utf8",
        }

        # Termination characters
        # https://telnetlib3.readthedocs.io/en/latest/guidebook.html#line-endings
        self._write_termination: str = "\r\n"

        self.conn: telnetlib3.sync.TelnetConnection = None  # type: ignore
        self.is_alive = False

    # --------------------------------------------------------------------------
    #   readline
    # --------------------------------------------------------------------------

    def readline(
        self,
        raises_on_timeout: bool = False,
    ) -> Tuple[bool, Union[str, bytes, None]]:
        """Listen to the telnet server for incoming data. This method is
        blocking and returns when a full line has been received or when the read
        timeout has expired.

        Args:
            raises_on_timeout (:obj:`bool`, optional):
                Should an exception be raised when a read timeout occurs?

                Default: :const:`False`

        Returns:
            :obj:`tuple`:
                success (:obj:`bool`):
                    True if successful, False otherwise.

                reply (:obj:`str` | :obj:`bytes`, :obj:`None`):
                    Reply received from the device. :obj:`None` if unsuccessful.
        """

        try:
            reply = self.conn.readline()
        except TimeoutError as err:
            if raises_on_timeout:
                raise err

            pft(err)
            return False, None
        except Exception as err:
            pft(err)
            return False, None

        try:
            reply = reply.strip()
        except Exception as err:
            pft(err)
            return False, None

        return True, reply

    # --------------------------------------------------------------------------
    #   write
    # --------------------------------------------------------------------------

    def write(self, msg: str) -> bool:
        """Send a message to the telnet server.

        Args:
            msg (:obj:`str`):
                ASCII string to be sent to the serial device.

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
            return False  # --> leaving

        try:
            self.conn.write(msg + self._write_termination)
        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        # Wait for the data to be sent completely
        self.conn.flush()

        return True

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(self, msg: str) -> Tuple[bool, Union[str, bytes, None]]:
        """Send a message to the telnet server and subsequently read the reply.

        Args:
            msg (:obj:`str`):
                ASCII string to be sent to the telnet server.

        Returns:
            :obj:`tuple`:
                success (:obj:`bool`):
                    True if successful, False otherwise.

                reply (:obj:`str` | :obj:`bytes` | :obj:`None`):
                    Reply received from the device. :obj:`None` if unsuccessful.
        """

        # Send query
        if not self.write(msg):
            return False, None  # --> leaving

        # Read reply
        success, reply = self.readline()

        return success, reply

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Close the telnet connection."""
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception as err:
                if ignore_exceptions:
                    pass
                else:
                    pft(err, 3)
                    sys.exit(0)

        self.is_alive = False

    # --------------------------------------------------------------------------
    #   connect
    # --------------------------------------------------------------------------

    def connect(self, host: str, port: int = 23, verbose: bool = True) -> bool:
        """Open a blocking telnet connection.

        Args:
            host (:obj:`str`):
                Remote server hostname or IP address.

            port (:obj:`int`):
                Remote server port.

                Default: :const:`23`

            verbose (:obj:`bool`, optional):
                Print a `"Connecting to: "`-message to the terminal?

                Default: :const:`True`

        Returns:
            True if successful, False otherwise.
        """

        def print_success(success_str: str):
            dprint(success_str, ANSI.GREEN)
            dprint((f"  --> {self.name}\n"), ANSI.GREEN)

        if verbose:
            _print_hrule(True)
            msg = f"  Connecting to: {self.long_name}"
            dprint(msg, ANSI.YELLOW)
            _print_hrule()

        print(f"  @ {host:<s}:{port} ", end="")
        try:
            # Open the telnet connection
            self.conn = telnetlib3.sync.TelnetConnection(
                host=host, port=port, **self.telnet_settings
            )
            self.conn.connect()
        except ConnectionError:
            print("Could not open telnet connection.")
            return False  # --> leaving
        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        print_success("Success!")
        self.is_alive = True
        return True  # --> leaving


def _print_hrule(leading_newline=False):
    dprint(("\n" if leading_newline else "") + "-" * 60, ANSI.YELLOW)
