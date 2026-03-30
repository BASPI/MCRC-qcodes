# Multichannel Remote Controller QCoDeS Driver

QCoDeS driver for the Basel Precision Instruments Multichannel Remote Controller (MCRC),
enabling remote operation of up to 8 BASPI amplifiers
(4× SP983 I/V Converters and 4× SP1004 Differential Amplifiers) over TCP.

Features include per-channel gain and cutoff control, real-time overload and
compensation monitoring, automatic reconnection, and dynamic channel management.

## Setup

Download `Baspi_Mcrc.py` and `Baspi_Mcrc_Controller.py` and copy them to your project folder. `examples.ipynb` gives some examples on how the driver can be used.

### Requirements

- Python 3.12 or higher
- QCoDeS (`pip install qcodes`)
- Network connection to the MCRC (default IP: `192.168.178.50`)

### Standalone CLI
A pre-built Windows executable (.exe) for controlling the Multichannel Remote Controller is available under [Releases](insert Link)

## Further Documentation

See https://www.baspi.ch/manuals for more information on the Multichannel Remote Controller.

See https://microsoft.github.io/Qcodes/ for more information about the QCoDeS framework.

If you have purchased a Multichannel Remote Controller, you have received documentation which includes the full command reference. Please be aware that the official documentation does not include any specific information on how to use the controller with the QCoDeS framework. However, since the QCoDeS driver allows for full control of the device and is mainly an interface, the general documentation is still useful.

## Contributing

If you found a bug or are having a serious issue, please use the GitHub issue tracker to report it.
