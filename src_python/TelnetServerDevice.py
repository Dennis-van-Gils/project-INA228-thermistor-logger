#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WORK IN PROGRESS. NOT FINISHED.

Provides base class TelnetServerDevice(), offering blocking I/O methods.
Instances of this class will tie in nicely with
:class:`dvg_qdeviceio.QDeviceIO`.

These base classes are meant to be inherited into your own specific *Device*
class.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/..."
__date__ = "11-05-2026"
__version__ = "0.1.0"
# pylint: disable=broad-except

import sys
import time
from typing import Union, Tuple

import telnetlib3

from dvg_debug_functions import dprint, ANSI, print_fancy_traceback as pft


class TelnetServerDevice:
    """This class provides blocking I/O methods for a TelnetServer device by
    wrapping the `telnetlib3 <https://telnetlib3.readthedocs.io/en/latest>`_
    library.

    The following functionality is offered:

    * TODO: mention `write()`, `query()`, `query_ascii_values()`,
      `readline()` and `close()`.

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
            :class:`telnetlib3.TelnetConnection` at initialization of the telnet
            client when trying to connect.

            Default: `{"baudrate": 9600, "timeout": 2, "write_timeout": 2}`

        telnet (:class:`telnetlib3.TelnetConnection` | :obj:`None`):
            Will be set to a :class:`telnetlib3.TelnetConnection` instance when
            a connection has been established. Otherwise: :obj:`None`.

        is_alive (:obj:`bool`):
            Is the connection alive? I.e., Can we communicate?
    """

    def __init__(
        self,
        name="Dev_1",
        long_name="Telnet Server Device",
    ):
        self.long_name = long_name
        self.name = name

        # Default telnet settings
        """
        self.telnet_settings = {
            "timeout": ...
            "connect_timeout": ...
            "encoding": ...
        }
        """

        # Termination characters, must always be of type `bytes`.
        # https://telnetlib3.readthedocs.io/en/latest/guidebook.html#line-endings
        self._read_termination: bytes = "\r\n".encode()
        self._write_termination: bytes = "\r\n".encode()

        self.telnet: telnetlib3.open_connection = None  # type: ignore
        self.is_alive = False

    # --------------------------------------------------------------------------
    #   readline
    # --------------------------------------------------------------------------

    def readline(
        self,
        raises_on_timeout: bool = False,
        returns_ascii: bool = True,
    ) -> Tuple[bool, Union[str, bytes, None]]:
        """Listen to the Arduino for incoming data. This method is blocking
        and returns when a full line has been received or when the serial read
        timeout has expired.

        Args:
            raises_on_timeout (:obj:`bool`, optional):
                Should an exception be raised when a read timeout occurs?

                Default: :const:`False`

            returns_ascii (:obj:`bool`, optional):
                When set to :const:`True` the device's reply will be returned as
                an ASCII string. Otherwise, it will return as bytes.

                Default: :const:`True`

        Returns:
            :obj:`tuple`:
                success (:obj:`bool`):
                    True if successful, False otherwise.

                reply (:obj:`str` | :obj:`bytes` | :obj:`None`):
                    Reply received from the device, either as ASCII string
                    (default) or as bytes when ``returns_ascii`` was set to
                    :const:`False`. :obj:`None` if unsuccessful.
        """

        try:
            reply = self.ser.readline()
        except serial.SerialException as err:
            # NOTE: The Serial library does not throw an exception when it
            # times out in `read`, only when it times out in `write`! We
            # will check for zero received bytes as indication for a read
            # timeout, later. See:
            # https://stackoverflow.com/questions/10978224/serialtimeoutexception-in-python-not-working-as-expected
            pft(err)
            return False, None
        except Exception as err:
            pft(err)
            return False, None

        if len(reply) == 0:
            if raises_on_timeout:
                raise serial.SerialException(
                    "Received 0 bytes. Read probably timed out."
                )
            else:
                pft("Received 0 bytes. Read probably timed out.")
                return False, None

        if returns_ascii:
            try:
                reply = reply.decode("utf8").strip()
            except Exception as err:
                pft(err)
                return False, None

        return True, reply

    # --------------------------------------------------------------------------
    #   write
    # --------------------------------------------------------------------------

    def write(
        self, msg: Union[str, bytes], raises_on_timeout: bool = False
    ) -> bool:
        """Send a message to the serial device.

        Args:
            msg (:obj:`str` | :obj:`bytes`):
                ASCII string or bytes to be sent to the serial device.

            raises_on_timeout (:obj:`bool`, optional):
                Should an exception be raised when a write timeout occurs?

                Default: :const:`False`

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
            return False  # --> leaving

        if isinstance(msg, str):
            msg = msg.encode()

        try:
            self.ser.write(bytes(msg) + self._write_termination)
        except (
            serial.SerialTimeoutException,
            serial.SerialException,
        ) as err:
            if raises_on_timeout:
                raise err  # --> leaving

            pft(err, 3)
            return False  # --> leaving
        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        return True

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(
        self,
        msg: Union[str, bytes],
        raises_on_timeout: bool = False,
        returns_ascii: bool = True,
    ) -> Tuple[bool, Union[str, bytes, None]]:
        """Send a message to the serial device and subsequently read the reply.

        Args:
            msg (:obj:`str` | :obj:`bytes`):
                ASCII string or bytes to be sent to the serial device.

            raises_on_timeout (:obj:`bool`, optional):
                Should an exception be raised when a write or read timeout
                occurs?

                Default: :const:`False`

            returns_ascii (:obj:`bool`, optional):
                When set to :const:`True` the device's reply will be returned as
                an ASCII string. Otherwise, it will return as bytes.

                TODO & NOTE: ASCII is a misnomer. The returned reply will be
                UTF-8 encoded, not ASCII. Need to fix the argument name somehow,
                without breaking code elsewhere.

                Default: :const:`True`

        Returns:
            :obj:`tuple`:
                success (:obj:`bool`):
                    True if successful, False otherwise.

                reply (:obj:`str` | :obj:`bytes` | :obj:`None`):
                    Reply received from the device, either as ASCII string
                    (default) or as bytes when ``returns_ascii`` was set to
                    :const:`False`. :obj:`None` if unsuccessful.
        """

        # Always ensure that a timeout exception is raised when coming from
        # :meth:`connect_at_port`.
        if self._force_query_to_raise_on_timeout:
            raises_on_timeout = True

        # Send query
        if not self.write(msg, raises_on_timeout=raises_on_timeout):
            return (False, None)  # --> leaving

        # Read reply
        try:
            if self._read_termination == b"":
                self.ser.flush()
                time.sleep(self._query_wait_time)
                reply = self.ser.read(self.ser.in_waiting)
            else:
                reply = self.ser.read_until(self._read_termination)
        except serial.SerialException as err:
            # Note: The Serial library does not throw an exception when it
            # times out in `read`, only when it times out in `write`! We
            # will check for zero received bytes as indication for a read
            # timeout, later. See:
            # https://stackoverflow.com/questions/10978224/serialtimeoutexception-in-python-not-working-as-expected
            pft(err, 3)
            return (False, None)  # --> leaving
        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        if len(reply) == 0:
            if raises_on_timeout:
                raise serial.SerialException(
                    "Received 0 bytes. Read probably timed out."
                )  # --> leaving

            pft("Received 0 bytes. Read probably timed out.", 3)
            return (False, None)  # --> leaving

        if returns_ascii:
            try:
                reply = reply.decode("utf8").strip()
            except UnicodeDecodeError as err:
                pft(err, 3)
                return (False, None)  # --> leaving
            except Exception as err:
                pft(err, 3)
                sys.exit(0)  # --> leaving

        return (True, reply)

    # --------------------------------------------------------------------------
    #   query_bytes
    # --------------------------------------------------------------------------

    def query_bytes(
        self,
        msg: bytes,
        N_bytes_to_read: int,
        raises_on_timeout: bool = False,
    ) -> Tuple[bool, Union[bytes, None]]:
        """Send a message as bytes to the serial device and subsequently read
        the reply. Will block until reaching ``N_bytes_to_read`` or a read
        timeout occurs.

        Args:
            msg (:obj:`bytes`):
                Bytes to be sent to the serial device.

            N_bytes_to_read (:obj:`int`):
                Number of bytes to read.

            raises_on_timeout (:obj:`bool`, optional):
                Should an exception be raised when a write or read timeout
                occurs?

                Default: :const:`False`

        Returns:
            :obj:`tuple`:
                success (:obj:`bool`):
                    True when ``N_bytes_to_read`` bytes are indeed read within
                    the timeout, False otherwise.

                reply (:obj:`bytes` | :obj:`None`):
                    Reply received from the device as bytes.

                    If ``success`` is False and 0 bytes got returned from the
                    device, then ``reply`` will be :obj:`None`.
                    If ``success`` is False because the read timed out and too
                    few bytes got returned, ``reply`` will contain the bytes
                    read so far.
        """

        # Always ensure that a timeout exception is raised when coming from
        # :meth:`connect_at_port`.
        if self._force_query_to_raise_on_timeout:
            raises_on_timeout = True

        # Send query
        if not self.write(msg, raises_on_timeout=raises_on_timeout):
            return (False, None)  # --> leaving

        # Read reply
        try:
            if N_bytes_to_read > 0:
                reply = self.ser.read(N_bytes_to_read)
            else:
                reply = b""
                self.ser.flush()
        except serial.SerialException as err:
            # Note: The Serial library does not throw an exception when it
            # times out in `read`, only when it times out in `write`! We
            # will check for zero received bytes as indication for a read
            # timeout, later. See:
            # https://stackoverflow.com/questions/10978224/serialtimeoutexception-in-python-not-working-as-expected
            pft(err, 3)
            return (False, None)  # --> leaving
        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        if (N_bytes_to_read > 0) and (len(reply) == 0):
            if raises_on_timeout:
                raise serial.SerialException(
                    "Received 0 bytes. Read probably timed out."
                )  # --> leaving

            pft("Received 0 bytes. Read probably timed out.", 3)
            return (False, None)  # --> leaving

        if N_bytes_to_read != len(reply):
            if raises_on_timeout:
                raise serial.SerialException(
                    "Received too few bytes. Read probably timed out."
                )  # --> leaving

            pft("Received too few bytes. Read probably timed out.", 3)
            return (False, reply)  # --> leaving

        return (True, reply)

    # --------------------------------------------------------------------------
    #   query_ascii_values
    # --------------------------------------------------------------------------

    def query_ascii_values(
        self,
        msg: str,
        delimiter="\t",
        raises_on_timeout: bool = False,
    ) -> Tuple[bool, list]:
        r"""Send a message to the serial device and subsequently read the reply.
        Expects a reply in the form of an ASCII string containing a list of
        numeric values, separated by a delimiter. These values will be parsed
        into a list and returned.

        Args:
            msg (:obj:`str`):
                ASCII string to be sent to the serial device.

            delimiter (:obj:`str`, optional):
                Delimiter used in the device's reply.

                Default: `"\\t"`

            raises_on_timeout (:obj:`bool`, optional):
                Should an exception be raised when a write or read timeout
                occurs?

                Default: :const:`False`

        Returns:
            :obj:`tuple`:
                success (:obj:`bool`):
                    True if successful, False otherwise.

                reply_list (:obj:`list`):
                    Reply received from the device and parsed into a list of
                    separate values. The list is empty if unsuccessful.
        """
        success, reply = self.query(
            msg, raises_on_timeout=raises_on_timeout, returns_ascii=True
        )

        if not success or not isinstance(reply, str):
            return (False, [])  # --> leaving

        try:
            # NOTE: `ast.literal_eval` chokes when it receives 'nan' so we ditch
            # it and just interpret everything as `float` instead.
            # reply_list = list(map(literal_eval, reply.split(delimiter)))
            reply_list = list(map(float, reply.split(delimiter)))

        except ValueError as err:
            pft(err, 3)
            return (False, [])  # --> leaving

        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        return (True, reply_list)

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Cancel all pending serial operations and close the serial port."""
        if self.ser is not None:
            try:
                self.ser.cancel_read()
            except Exception:
                pass
            try:
                self.ser.cancel_write()
            except Exception:
                pass

            try:
                self.ser.close()
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

    def connect(self, port: str, verbose: bool = True) -> bool:
        """Open the serial port at address ``port`` and try to establish a
        connection.

        Args:
            port (:obj:`str`):
                Serial port address to open.

            verbose (:obj:`bool`, optional):
                Print a `"Connecting to: "`-message to the terminal?

                Default: :const:`True`

        Returns:
            True if successful, False otherwise.
        """

        def print_success(success_str: str):
            dprint(success_str, ANSI.GREEN)
            dprint((" " * 16 + f"--> {self.name}\n"), ANSI.GREEN)

        if verbose:
            _print_hrule(True)
            if (
                self._ID_validation_query is None
                or self._valid_ID_specific is None
            ):
                msg = f"  Connecting to: {self.long_name}"
            else:
                msg = (
                    f"  Connecting to: {self.long_name} "
                    f"`{self._valid_ID_specific}`"
                )

            dprint(msg, ANSI.YELLOW)
            _print_hrule()

        print(f"  @ {port:<11s} ", end="")
        try:
            # Open the serial port
            self.ser = serial.Serial(port=port, **self.serial_settings)
        except serial.SerialException:
            print("Could not open port.")
            return False  # --> leaving
        except Exception as err:
            pft(err, 3)
            sys.exit(0)  # --> leaving

        if self._ID_validation_query is None:
            # Found any device
            print_success("Any Success!")
            self.is_alive = True
            return True  # --> leaving

        print("Wrong device.")
        self.close(ignore_exceptions=True)
        return False


def _print_hrule(leading_newline=False):
    dprint(("\n" if leading_newline else "") + "-" * 60, ANSI.YELLOW)
