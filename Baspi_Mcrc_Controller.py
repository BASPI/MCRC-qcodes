# ------------------------------------------------------------------------------
# Multichannel Remote Controller - Controller (TCP/IPInstrument)
# v0.1.0
# Copyright (c) Basel Precision Instruments GmbH (2026)
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or any later version.
# ------------------------------------------------------------------------------
import socket
import threading
import re
from typing import Optional


class BaspiMcrcController:
    """
    Synchronous TCP controller for MCRC communication.
    Uses plain sockets - no external dependencies.
    """
    
    def __init__(self, host: str, port: int = 8766, timeout: float = 10.0,
                 coldstart: str = "KEEP", username: str = None, password: str = None):
        """
        Initialize and connect to the MCRC TCP server.
        
        Parameters
        ----------
        host : IP address or hostname of the Raspberry Pi
        port : TCP port (default 8766)
        timeout : Socket timeout in seconds
        coldstart : How to handle coldstart sync: "KEEP" (apply DB settings) or "DEFAULT" (reset hardware)
        username : Username for authentication (required for coldstart handling)
        password : Password for authentication (required for coldstart handling)
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._coldstart = coldstart.upper()
        self._username = username
        self._password = password
        
        if self._coldstart not in ("KEEP", "DEFAULT"):
            raise ValueError("coldstart must be 'KEEP' or 'DEFAULT'")
        
        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._buffer = ""
        
        self._connect()
    
    
    def _connect(self):
        """Establish TCP connection, handle greeting and optional auth/coldstart."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        self._socket.connect((self.host, self.port))
        self._buffer = ""
        
        try:
            greeting = self._recv_line()
            print(f"Server: {greeting.strip()}")
        except socket.timeout:
            pass
        
        if self._username and self._password:
            self._authenticate()
    
    def _authenticate(self):
        """Handle authentication and coldstart prompt."""
        print(f"Authenticating as '{self._username}'...")
        
        self._socket.sendall(f"AUTH {self._username} {self._password}\n".encode('utf-8'))
        response = self._recv_line()
        print(f"Auth response: {response.strip()}")
        
        if response.startswith("ERR"):
            raise ConnectionError(f"Authentication failed: {response}")
        
        # check for coldstart prompt in response
        if "Coldstart" in response:
            print(f"Coldstart detected, responding with: {self._coldstart}")
            self._socket.sendall((self._coldstart + '\n').encode('utf-8'))
            coldstart_response = self._recv_line()
            # show first 200 chars of response
            preview = coldstart_response[:200].replace('\n', ' ')
            print(f"Coldstart result: {preview}...")
        elif "OK AUTH" in response:
            print(f"Authenticated successfully (no coldstart needed)")
        else:
            print(f"Unexpected auth response: {response[:100]}")
    
    def close(self):
        """Close the connection."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
            self._buffer = ""
    
    def reconnect(self):
        """Close and reopen the connection."""
        self.close()
        self._connect()
    
    @property
    def is_connected(self) -> bool:
        """Check if socket is connected."""
        return self._socket is not None
    
    # low level communication ------------------------------------------------------------------------
    
    def _recv_line(self) -> str:
        """Read until newline, decode escaped newlines."""
        while '\n' not in self._buffer:
            chunk = self._socket.recv(4096).decode('utf-8', errors='replace')
            if not chunk:
                raise ConnectionError("Server closed connection")
            self._buffer += chunk
        
        line, self._buffer = self._buffer.split('\n', 1)
        
        return line.replace('\\n', '\n')
    
    def _send_command(self, cmd: str) -> str:
        """
        Send a command and return the response.
        Thread-safe with automatic reconnect on failure.
        """
        with self._lock:
            try:
                self._socket.sendall((cmd + '\n').encode('utf-8'))
                return self._recv_line()
            except (socket.error, ConnectionError, OSError) as exc:
                print(f"Connection lost ({exc}), reconnecting...")
                self.reconnect()
                self._socket.sendall((cmd + '\n').encode('utf-8'))
                return self._recv_line()
    
    def get_idn(self) -> dict:
        """
        Query device identification.
        """
        resp = self._send_command("IDN").strip()
        
        vendor = "Basel Precision Instruments AG (BASPI)"
        
        base = resp.split("(serial:")[0].strip() if "(serial:" in resp else resp
        
        model = base
        if model.startswith(vendor):
            model = model[len(vendor):].strip()
        
        serial = None
        firmware = None
        
        m = re.search(r"serial\s*:\s*([^,\)]+)", resp, re.I)
        if m:
            serial = m.group(1).strip()
        
        m = re.search(r"firmware\s*:\s*([^,\)]+)", resp, re.I)
        if m:
            firmware = m.group(1).strip()
        
        return {
            "vendor": vendor,
            "model": model,
            "serial": serial,
            "firmware": firmware,
        }
    
    # device status and configuration commands -------------------------------------------------------
    
    def get_status(self, dev_label: str) -> tuple[str, str, Optional[str], Optional[str]]:
        """
        Get current status of a device.
        """
        reply = self._send_command(f"STATUS {dev_label}")
        
        if "GAIN=" not in reply or "CUTOFF=" not in reply:
            raise RuntimeError(f"Unexpected STATUS reply: {reply!r}")
        
        try:
            right = reply.split("→", 1)[1]
        except IndexError:
            right = reply
        
        right = right.strip()
        parts = [p.strip().strip(",") for p in right.split()]
        
        gain_str = None
        cutoff_str = None
        overload_str = None
        comp_str = None
        
        for p in parts:
            up = p.upper()
            if up.startswith("GAIN="):
                gain_str = up.split("=", 1)[1]
            elif up.startswith("CUTOFF="):
                cutoff_str = up.split("=", 1)[1]
            elif up in ("OK", "OVERLOAD"):
                overload_str = up
            elif up.startswith("COMP="):
                comp_raw = up.split("=", 1)[1]
                if comp_raw == "ON":
                    comp_str = "COMPENSATED"
                elif comp_raw == "OFF":
                    comp_str = "OFFSET COMPENSATION"
                else:
                    comp_str = comp_raw
        
        return gain_str, cutoff_str, overload_str, comp_str
    
    def set_config(self, dev_label: str, gain: str, cutoff: str) -> str:
        """Set gain and cutoff for a device."""
        cmd = f"SET {dev_label} GAIN {gain} CUTOFF {cutoff}"
        reply = self._send_command(cmd)
        return reply
    
    def get_gain(self, dev_label: str) -> str:
        """Get current gain setting."""
        gain, _, _, _ = self.get_status(dev_label)
        return gain
    
    def get_cutoff(self, dev_label: str) -> str:
        """Get current cutoff setting."""
        _, cutoff, _, _ = self.get_status(dev_label)
        return cutoff
    
    def set_gain(self, dev_label: str, gain: str) -> None:
        """Set gain (preserving current cutoff)."""
        _, cutoff, _, _ = self.get_status(dev_label)
        self.set_config(dev_label, gain, cutoff)
    
    def set_cutoff(self, dev_label: str, cutoff: str) -> None:
        """Set cutoff (preserving current gain)."""
        gain, _, _, _ = self.get_status(dev_label)
        self.set_config(dev_label, gain, cutoff)
    
    # device management ----------------------------------------------------------------
    
    def get_num_addresses(self) -> int:
        """Get number of I2C addresses from device IDN."""
        idn = self.get_idn()
        model = idn.get("model", "")
        if "16 channel" in model:
            return 8
        elif "8 channel" in model:
            return 4
        raise ValueError(f"Could not determine channel count from model string: {repr(model)}")
    
    def add_device(self, dev_label: str, name: Optional[str] = None) -> str:
        """Add a device to the server database."""
        dev_label = dev_label.strip().upper()
        if name:
            cmd = f"ADD {dev_label} NAME {name}"
        else:
            cmd = f"ADD {dev_label}"
        return self._send_command(cmd)
    
    def remove_device(self, dev_label: str) -> str:
        """Remove a device from the server database."""
        return self._send_command(f"REMOVE {dev_label}")