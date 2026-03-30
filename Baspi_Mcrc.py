# ------------------------------------------------------------------------------
# Multichannel Remote Controller Driver (TCP version)
# v0.1.0
# Copyright (c) Basel Precision Instruments AG (2026)
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or any later version.
# ------------------------------------------------------------------------------
from Baspi_Mcrc_Controller import BaspiMcrcController
from qcodes.instrument import Instrument, InstrumentChannel, ChannelList
import qcodes.validators as validate
from functools import partial
from time import sleep
from typing import Optional


class BaspiMcrcChannel(InstrumentChannel):
    """
    Represents a logical channel (IV converter or Differential Amplifier)
    on the Multichannel Remote Controller.
    """

    def __init__(self, parent: "BaspiMcrc", name: str, address_index: int, role: str, controller: BaspiMcrcController):
        """
        Initialize a channel.
        
        Parameters:
            parent : Parent instrument
            name : Channel name (e.g., 'iv1', 'da2')
            address_index : Hardware address index (1-4)
            role : 'iv' for I/V Converter, 'da' for Differential Amplifier
            controller : Communication controller
        """
        super().__init__(parent, name)

        self._controller = controller
        self._addr = address_index
        self._role = role.lower()

        if self._role == "da":
            self._dev_label = f"DA{self._addr}"
            gain_vals = ("1E3", "1E2", "1E4")
            cutoff_vals = ("100", "300", "1K", "3K", "10K", "30K", "100K", "300K", "1M")
            unit = "V/V"
        elif self._role == "iv":
            self._dev_label = f"IV{self._addr}"
            gain_vals = ("1E5", "1E6", "1E7", "1E8", "1E9")
            cutoff_vals = ("30", "100", "300", "1K", "3K", "10K", "30K", "100K", "1M")
            unit = "V/A"
        else:
            raise ValueError("role must be 'da' or 'iv'")

        self._gain_vals = gain_vals
        self._cutoff_vals = cutoff_vals

        # GAIN parameter
        self.add_parameter(
            "gain",
            unit=unit,
            label=f"{self._dev_label} gain",
            get_cmd=partial(self._controller.get_gain, self._dev_label),
            set_cmd=partial(self._controller.set_gain, self._dev_label),
            vals=validate.Enum(*gain_vals),
        )

        # CUTOFF parameter
        self.add_parameter(
            "cutoff",
            unit="Hz",
            label=f"{self._dev_label} cutoff",
            get_cmd=partial(self._controller.get_cutoff, self._dev_label),
            set_cmd=partial(self._controller.set_cutoff, self._dev_label),
            vals=validate.Enum(*cutoff_vals),
        )

    def _ensure_registered(self) -> None:
        """Verify channel is still attached to parent instrument."""
        parent = getattr(self, "_parent", None)
        if parent is None:
            return

        if hasattr(parent, "all") and parent.all is not None:
            if self not in parent.all:
                raise RuntimeError(
                    f"Channel '{self._dev_label}' is not registered on "
                    f"instrument '{parent.name}'. "
                    "Please (re)add it with mcrc.add_channel(...)."
                )

    def get_status(self) -> tuple[str, str, Optional[str], Optional[str]]:
        """
        Get full status for this channel.
        """
        self._ensure_registered()
        return self._controller.get_status(self._dev_label)

    def configure(self, gain: str, cutoff: str) -> str:
        """
        Configure channel with specified gain and cutoff.
        
        Parameters:
            gain : Gain value (e.g., '1E7')
            cutoff : Cutoff frequency (e.g., '100K')
        """
        self._ensure_registered()
        return self._controller.set_config(self._dev_label, gain, cutoff)

    @classmethod
    def add_to_instrument(cls, parent: "BaspiMcrc", shorthand: str, display_name: Optional[str] = None) -> "BaspiMcrcChannel":
        """
        Create and attach a channel to the parent instrument.
        """
        text = shorthand.strip().lower()

        if text.startswith("iv"):
            role = "iv"
            index_str = text[2:]
        elif text.startswith("da"):
            role = "da"
            index_str = text[2:]
        else:
            raise ValueError(
                f"Invalid channel shorthand '{shorthand}'. Use e.g. 'iv1' or 'da3'."
            )

        if not index_str.isdigit():
            raise ValueError(
                f"Invalid channel shorthand '{shorthand}'. Index must be an integer."
            )

        pair_index = int(index_str)

        if pair_index < 1 or pair_index > parent.number_addresses:
            raise ValueError(
                f"Channel index must be between 1 and {parent.number_addresses}, "
                f"got {pair_index}."
            )

        name = f"{role}{pair_index}"

        # check if channel is fully registered (exists AND in ChannelList)
        if name in parent.submodules:
            existing_channel = parent.submodules[name]

            is_in_channellist = (
                hasattr(parent, "all") 
                and parent.all is not None 
                and existing_channel in parent.all
            )

            if is_in_channellist:
                # fully registered - just update server and return existing
                parent._controller.add_device(existing_channel._dev_label, name=display_name)
                return existing_channel
            

        # clean up any existing references before creating new channel

        if name in parent.submodules:
            del parent.submodules[name]

        if hasattr(parent, "all") and parent.all is not None:
            for ch in list(parent.all): 
                if getattr(ch, "name", None) == name:
                    parent.all.remove(ch)
                    break

        # create new channel
        channel = cls(parent=parent, name=name, address_index=pair_index, role=role, controller=parent._controller)

        parent.add_submodule(name, channel)
        parent.all.append(channel)

        # register on server and configure defaults
        try:
            default_gain = channel._gain_vals[0]
            default_cutoff = channel._cutoff_vals[0]

            parent._controller.add_device(channel._dev_label, name=display_name)
            channel.configure(default_gain, default_cutoff)
            label = f" ('{display_name}')" if display_name else ""
            print(f"Added channel '{channel._dev_label}'{label} — gain={default_gain}, cutoff={default_cutoff}.")
        except Exception as exc:
            print(
                f"Warning: failed to add/configure device "
                f"'{channel._dev_label}' on server: {exc}"
            )

        return channel


    @classmethod
    def remove_from_instrument(cls, parent: "BaspiMcrc", shorthand: str) -> None:
        """
        Remove a channel from the parent instrument.
        """
        text = shorthand.strip().lower()

        if text.startswith("iv"):
            role = "iv"
            index_str = text[2:]
        elif text.startswith("da"):
            role = "da"
            index_str = text[2:]
        else:
            raise ValueError(
                f"Invalid channel shorthand '{shorthand}'. Use e.g. 'iv1' or 'da3'."
            )

        if not index_str.isdigit():
            raise ValueError(
                f"Invalid channel shorthand '{shorthand}'. Index must be an integer."
            )

        pair_index = int(index_str)
        name = f"{role}{pair_index}"

        # check if channel exists
        if name not in parent.submodules:
            print(f"Channel '{name}' not present, nothing to remove.")
            return

        channel = parent.submodules[name]

        # remove from server DB
        try:
            dev_label = getattr(channel, "_dev_label", None)
            if dev_label is not None:
                print(f"Removing device '{dev_label}' on server...")
                reply = parent._controller.remove_device(dev_label)
                print(f"Server reply: {reply!r}")
        except Exception as exc:
            print(f"Warning: failed to remove device on server: {exc}")

        # remove from ChannelList
        if hasattr(parent, "all") and parent.all is not None:
            try:
                parent.all.remove(channel)
            except ValueError:
                pass

        # remove from submodules dict 
        if name in parent.submodules:
            del parent.submodules[name]

        print(f"Removed logical channel '{name}'.")


class BaspiMcrc(Instrument):
    """
    QCoDeS driver for Basel Precision Instruments Multichannel Remote Controller.
    
    Communicates via TCP socket to the MCRC server running on a Raspberry Pi.
    
    Parameters
    ----------
    name : Instrument name
    host : IP address or hostname of the Raspberry Pi
    coldstart : How to handle coldstart: "KEEP" (apply DB settings) or "DEFAULT" (reset hardware)
    username : Username for authentication (if server requires it)
    password : Password for authentication (if server requires it)
    """

    def __init__(
        self,
        name: str,
        host: str,
        coldstart: str = "KEEP",
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs
    ):
        super().__init__(name, **kwargs)

        self._host = host
        self._port = 8766
        self._coldstart = coldstart
        self._username = username
        self._password = password

        self._controller = BaspiMcrcController(
            host=host,
            port=self._port,
            coldstart=coldstart,
            username=username,
            password=password,
        )

        self.number_addresses = self._controller.get_num_addresses()
        self.number_channels = self.number_addresses * 2

        if self.number_channels not in (8, 16):
            raise SystemError(
                "Physically available number of channels is not 8. "
                "Please check device."
            )

        all_channels: ChannelList[BaspiMcrcChannel] = ChannelList(
            self, "all_channels", BaspiMcrcChannel
        )
        self.add_submodule("all", all_channels)

        self.connect_message()
        print(f"Multichannel Remote Controller initialized (coldstart={coldstart})")
        print(
            f"{self.number_addresses} I2C addresses."
        )

    def get_idn(self) -> dict:
        """Return instrument identification."""
        return self._controller.get_idn()

    def ask_raw(self, cmd: str) -> str:
        """Send a query and return response."""
        cmd = cmd.strip()
        if cmd.upper() == "*IDN?":
            d = self._controller.get_idn()
            return (
                f"{d.get('vendor', '')}, {d.get('model', '')}, "
                f"{d.get('serial', '')}, {d.get('firmware', '')}"
            )
        return self._controller._send_command(cmd)

    def write_raw(self, cmd: str) -> None:
        """Send a command without expecting response."""
        self._controller._send_command(cmd)

    def close(self) -> None:
        """Close the connection."""
        try:
            if hasattr(self, "_controller") and self._controller is not None:
                print("Closing connection...")
                self._controller.close()
        except Exception as exc:
            print(f"Error while closing controller: {exc}")
        super().close()

    def reconnect(self, attempts: int = 10, wait_between_attempts: float = 5.0,) -> "BaspiMcrc":
        """
        Re-open the connection to the MCRC.
        """
        attempts = max(1, attempts)
        wait_between_attempts = max(0.0, wait_between_attempts)

        print(
            "Trying to reconnect to the Multichannel Remote Controller.\n"
            "Please ensure the MCRC server is running on the Raspberry Pi.\n"
        )

        last_exc: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                self._controller.reconnect()
                idn = self.get_idn()

                print(
                    f"Successfully reconnected to "
                    f"{idn.get('model', 'unknown')}, "
                    f"S/N {idn.get('serial', 'unknown')}, "
                    f"FW {idn.get('firmware', 'unknown')}."
                )
                return self

            except Exception as exc:
                last_exc = exc

                if attempt < attempts:
                    print(
                        f"Reconnect attempt {attempt}/{attempts} failed.\n"
                        f"Waiting {wait_between_attempts:.1f}s before next try...\n"
                    )
                    sleep(wait_between_attempts)
                else:
                    raise RuntimeError(
                        "All reconnect attempts failed.\n"
                        f"Host: {self._host}, Port: {self._port}"
                    ) from last_exc

        return self

    def add_channel(self, shorthand: str, name: Optional[str] = None) -> BaspiMcrcChannel:
        """
        Add a channel by shorthand.
        """
        return BaspiMcrcChannel.add_to_instrument(self, shorthand, display_name=name)

    def remove_channel(self, shorthand: str) -> None:
        """
        Remove a channel.
        """
        return BaspiMcrcChannel.remove_from_instrument(self, shorthand)