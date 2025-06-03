# NANDIO.PIO

[![pytest](https://github.com/wipeseals/nandio.pio/actions/workflows/test.yml/badge.svg)](https://github.com/wipeseals/nandio.pio/actions/workflows/test.yml)
[![simulation](https://github.com/wipeseals/nandio.pio/actions/workflows/simulation.yml/badge.svg)](https://github.com/wipeseals/nandio.pio/actions/workflows/simulation.yml)

Accelerating NAND Flash Communication using PIO (Programmable IO).

## Features

- High-speed NAND flash communication using PIO
- PIO simulation environment for verification
- Supports JISC-SSD (Jisaku In-Storage Computation SSD) board
- Unit tests and CI for quality assurance

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

### Simulation

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

### assembly

To assemble the PIO program, you can use the `uv` command with the `asm` option. This will compile the PIO assembly code into a binary format that can be used by the Raspberry Pi Pico.

```bash
uv run sim/cli.py asm
PIO program assembled successfully: binary=</path/to/nandio.bin>, python=</path/to/nandio.py>
import array
PIO_OPCODES: array.array = array('H', [40096, 31888, 31788, 31812, 40096, 7304, 31754, 7168, 7308, 29962, 46402, 7424, 7313, 38560, 30218, 7757, 7168, 7320, 44098, 44098, 23560, 39968, 7250, 7168, 7327, 38048, 29706, 7257, 7168, 56320, 7168, 15503])
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
uvx mpremote connect COM13 + fs --recursive --force cp main.py :/main.py + cp  nandio.py :/nandio.py + cp  sim/nandio_pio.py :/sim/nandio_pio.py  + cp  mpy/driver.py :/mpy/driver.py + cp mpy/ftl.py :/mpy/ftl.py + fs ls + soft-reset + run main.py + repl
cp main.py :/main.py
cp nandio.py :/nandio.py
Up to date: /nandio.py
cp sim/nandio_pio.py :/sim/nandio_pio.py
Up to date: /sim/nandio_pio.py
cp mpy/driver.py :/mpy/driver.py
cp mpy/ftl.py :/mpy/ftl.py
ls :
         607 main.py
           0 mpy/
         578 nand_block_allocator.json
         332 nandio.py
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
