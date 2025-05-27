# NANDIO.PIO

[![pytest with uv](https://github.com/wipeseals/nandio.pio/actions/workflows/test.yml/badge.svg)](https://github.com/wipeseals/nandio.pio/actions/workflows/test.yml)

Accelerating NAND Flash Communication using PIO (Programmable IO).

## Features

TODO

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
uv run src/main.py sim --all
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- ... 'reset' 40cyc
Simulating scenario... ━━━━━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  17% -:--:-- ... 'read_id' 100cyc
Simulating scenario... ━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━  33% 0:00:02 ... 'read' 300cyc
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━  50% 0:00:02 ... 'program' 300cyc
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━━━━━━━━━━  67% 0:00:02 ... 'erase' 200cyc
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━  83% 0:00:01 ... 'status_read' 30cyc
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
All simulations completed successfully. output saved to </path/to/output>

# Specific scenario
uv run src/main.py sim --scenario reset
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- ... 'reset' 40cyc
Simulating scenario... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
All simulations completed successfully. output saved to <path/to/output>
```

### assembly

To assemble the PIO program, you can use the `uv` command with the `assemble` option. This will compile the PIO assembly code into a binary format that can be used by the Raspberry Pi Pico.

```bash
uv run src/main.py assemble
PIO program assembled successfully: <path/to/output>
[9ca0, 7c90, 7c2c, 7c44, 9ca0, 1c88, 7c0a, 1c00, 1c8c, 750a, b542, 1d00, 1c91, 96a0, 760a, 1e4d, 1c00, 1c98, ac42, ac42, 5c08, 9c20, 1c52, 1c00, 1c9f, 94a0, 740a, 1c59, 1c00, dc00, 1c00, 3c8f]

```

### JISC-SSD Board (RP2040 + NAND Flash)

TODO

## References

- [[VOL-28]JISC-SSD(Jisaku In-Storage Computation SSD 学習ボード)](https://crane-elec.co.jp/products/vol-28/)
- [TC58NVG0S3HTA00 Datasheet](https://www.kioxia.com/content/dam/kioxia/newidr/productinfo/datasheet/201910/DST_TC58NVG0S3HTA00-TDE_EN_31435.pdf)
- [RP2040 Datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)
- [GitHub - crane-elec/rawnand_test](https://github.com/crane-elec/rawnand_test)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
