# NANDIO.PIO

[![pytest](https://github.com/wipeseals/nandio.pio/actions/workflows/test.yml/badge.svg)](https://github.com/wipeseals/nandio.pio/actions/workflows/test.yml)
[![simulation](https://github.com/wipeseals/nandio.pio/actions/workflows/simulation.yml/badge.svg)](https://github.com/wipeseals/nandio.pio/actions/workflows/simulation.yml)

Accelerating NAND Flash Communication using PIO (Programmable IO).

## Features

- High-speed NAND flash communication using PIO and payload builder
- Simulation environment for verification
- async/await friendly API for MicroPython
- Supports Raspberry Pi Pico and JISC-SSD (Jisaku In-Storage Computation SSD) board

### Waveforms

![Logic Analyzer Waveforms](/misc/PioNandCommander-ProgramPage-Core125MHz-Pio125MHz.png)

### Online Simulation

<https://wipeseals.github.io/nandio.pio/>

### Performance

JISC-SSD board with RP2040 and NAND Flash (TC58NVG0S3HTA00) performance comparison.

#### CPU Clock: 125MHz, PIO Clock: 125MHz

```bash
MPY: soft reboot
CPU frequency: 125.0 MHz
# `Fw` commander results:
- Read ID time      : 3391 us
- Erase block time  : 4785 us
- Program page time : 8560594 us
- Read page time    : 3692423 us

# `Pio` commander results:
- Read ID time      : 3527 us
- Erase block time  : 6357 us
- Program page time : 21405 us
- Read page time    : 5491 us

MicroPython v1.25.0 on 2025-04-15; Raspberry Pi Pico with RP2040
Type "help()" for more information.
>>>
```

#### CPU Clock: 250MHz, PIO Clock: 125MHz

```bash
MPY: soft reboot
CPU frequency: 250.0 MHz
# `Fw` commander results:
- Read ID time      : 1771 us
- Erase block time  : 2353 us
- Program page time : 5421321 us
- Read page time    : 1845875 us

# `Pio` commander results:
- Read ID time      : 1735 us
- Erase block time  : 3733 us
- Program page time : 11197 us
- Read page time    : 3293 us

MicroPython v1.25.0 on 2025-04-15; Raspberry Pi Pico with RP2040
Type "help()" for more information.
```

## Installation

To install the project, you can use the `uv` tool, which is a Python package manager that simplifies the installation of Python projects with multiple dependencies.
You can install `uv` and the project dependencies using the following commands:

```bash
pip install uv
uv sync --all-extras --dev

# run unit tests
uv run pytest
```

## Usage

### Local Simulation

To simulate the NAND Flash communication, you can use the provided simulation script. This will run the simulation using the `uv` command.

```bash
# All scenarios
uv run sim/cli.py sim --all
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
Simulation completed for scenarios: reset, read_id, read, program, erase, status_read
All simulations completed successfully. output saved to </path/to/output>

# Specific scenario
uv run sim/cli.py sim --scenario reset
```

You can view the simulation results on GitHub Pages:  
<https://wipeseals.github.io/nandio.pio/>

### Assembly

To assemble the PIO program, you can use the `uv` command with the `asm` option. This will compile the PIO assembly code into a binary format that can be used by the Raspberry Pi Pico.

```bash
uv run sim/cli.py asm
PIO program assembled successfully!
Output binary saved to: </path/to/output/nandio.pio.bin>
```

### JISC-SSD Board (RP2040 + NAND Flash)

#### Install MicroPython

- Download the MicroPython UF2 file for RP2040 from the official Raspberry Pi Pico website and flash it to the board.
  - See [MicroPython - Raspberry Pi](https://www.raspberrypi.com/documentation/microcontrollers/micropython.html) for details.
  - The confirmed working version of MicroPython is `v1.24.1` (other versions may not work properly).

#### Run MicroPython scripts

- Transfer the project to the Raspberry Pi Pico and run.

##### Using vscode [MicroPico Extension](https://marketplace.visualstudio.com/items?itemName=paulober.pico-w-go)

Run the `MicroPico: Upload project to Pico` (`@command:micropico.upload`) command to upload the project to the Raspberry Pi Pico.

##### Using mpremote

```bash
uvx mpremote connect COM13 + fs --recursive --force cp main.py :/main.py + cp  nandio.py :/nandio.py + cp  sim/nandio_pio.py :/sim/nandio_pio.py  + cp  mpy/driver.py :/mpy/driver.py + fs ls + soft-reset + run main.py + repl
cp main.py :/main.py
cp sim/nandio_pio.py :/sim/nandio_pio.py
Up to date: /sim/nandio_pio.py
cp mpy/driver.py :/mpy/driver.py
ls :
         607 main.py
           0 mpy/
           0 sim/
(snip)
```

## References

- [[VOL-28]JISC-SSD(Jisaku In-Storage Computation SSD 学習ボード)](https://crane-elec.co.jp/products/vol-28/)
- [TC58NVG0S3HTA00 Datasheet](https://www.kioxia.com/content/dam/kioxia/newidr/productinfo/datasheet/201910/DST_TC58NVG0S3HTA00-TDE_EN_31435.pdf)
- [RP2040 Datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)
- [GitHub - crane-elec/rawnand_test](https://github.com/crane-elec/rawnand_test)
- [ゼロから学ぶ SSD：構造、動作、耐久性のポイント - キオクシア株式会社](https://www.kioxia.com/content/dam/kioxia/ja-jp/business/ssd/asset/SNIA-seminar-202502.pdf)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
