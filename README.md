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
Simulating all scenarios... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- ... 'reset' 40cyc
Simulating all scenarios... ━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━  xx% -:--:-- ... 'read_id' 100cyc
(snip)
Simulating all scenarios... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
All simulations completed successfully. output saved to </path/to/output>

# Specific scenario
uv run src/main.py sim --scenario reset
Simulating all scenarios... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- ... 'reset' 40cyc
Simulating all scenarios... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
All simulations completed successfully. output saved to E:\repos\nandio.pio\output
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
