import array
import datetime
import json
import os
import adafruit_pioasm
from dataclasses import dataclass
from typing import List
import rich
import rich_click as click
from pathlib import Path
import logging
from rich.logging import RichHandler
from src.nandio_pio import PioCmdBuilder
from rich.progress import Progress

from src.simulator import Result, Simulator

console = rich.get_console()


@dataclass
class SimScenario:
    name: str
    payload: list[int]
    test_cycles: int = 100

    def execute(self, program_str: str) -> Result:
        return Simulator.execute(
            program_str=program_str,
            test_cycles=self.test_cycles,
            tx_fifo_entries=self.payload,
        )


SCENARIOS: List[SimScenario] = [
    SimScenario("reset", PioCmdBuilder.seq_reset(cs=0), test_cycles=100),
    SimScenario("read_id", PioCmdBuilder.seq_read_id(cs=0), test_cycles=100),
    SimScenario(
        "read",
        PioCmdBuilder.seq_read(
            cs=0, column_addr=0, page_addr=0, block_addr=1023, data_count=32
        ),
        test_cycles=300,
    ),
    SimScenario(
        "program",
        PioCmdBuilder.seq_program(
            cs=0,
            column_addr=0,
            page_addr=0,
            block_addr=1023,
            data=list(range(32)),
        ),
        test_cycles=300,
    ),
    SimScenario(
        "erase",
        PioCmdBuilder.seq_erase(cs=0, block_addr=1023),
        test_cycles=200,
    ),
    SimScenario("status_read", PioCmdBuilder.seq_status_read(cs=0), test_cycles=30),
]


@click.group()
@click.option(
    "--log_level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Set the logging level",
)
def cli(
    log_level: str,
):
    """A command-line interface for PIO simulation."""
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


@cli.command()
@click.option(
    "--pio_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    default="nandio.pio",
)
@click.option(
    "--bin_path",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--py_path",
    type=click.Path(exists=True, path_type=Path),
)
def asm(
    pio_path: Path,
    bin_path: Path | None = None,
    py_path: Path | None = None,
):
    """Assemble the PIO program."""
    if not pio_path.exists():
        console.print(f"[red]PIO file {pio_path} does not exist.[/red]")
        return
    if bin_path is None:
        bin_path = pio_path.with_suffix(".bin")
    if py_path is None:
        py_path = pio_path.with_suffix(".py")

    program_str = Path(pio_path).read_text(encoding="utf-8")
    opcodes: array.array = adafruit_pioasm.assemble(program_str)
    # save binary output
    py_str = f"# generated from {pio_path.name}. created_at={datetime.datetime.now()}\nimport array{os.linesep}PIO_OPCODES: array.array = {opcodes}"
    bin_path.write_bytes(opcodes.tobytes())
    py_path.write_text(py_str, encoding="utf-8")

    console.print(
        f"[green]PIO program assembled successfully: binary={bin_path.absolute()}, python={py_path.absolute()}[/green]"
    )
    console.print(f"```python{os.linesep}{py_str}{os.linesep}```")


@cli.command()
@click.option(
    "--pio_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    default="nandio.pio",
)
@click.option(
    "--output_path",
    required=True,
    type=click.Path(writable=True, path_type=Path),
    default="output",
)
@click.option(
    "--all",
    is_flag=True,
    help="Run all simulation scenarios",
)
@click.option(
    "--scenario",
    type=click.Choice([s.name for s in SCENARIOS]),
    help="Run a specific simulation scenario",
)
def sim(
    pio_path: Path,
    output_path: Path,
    all: bool = False,
    scenario: str | None = None,
):
    """Simulate all PioCmdBuilder sequences."""

    program_str = Path(pio_path).read_text(encoding="utf-8")
    target_scenarios = SCENARIOS if all else []
    if scenario:
        target_scenarios = [s for s in SCENARIOS if s.name == scenario]
    if not target_scenarios:
        console.print(
            "[red]No scenarios selected. Use --all to run all scenarios or --scenario to specify one.[/red]"
        )
        return

    with Progress() as progress:
        task = progress.add_task("Simulating scenario...", total=len(target_scenarios))
        for scenario in target_scenarios:
            logging.debug(f"Running scenario: {scenario}")
            ret: Result = Simulator.execute(
                program_str=program_str,
                test_cycles=scenario.test_cycles,
                tx_fifo_entries=scenario.payload,
            )
            output_dir = output_path / scenario.name
            output_dir.mkdir(parents=True, exist_ok=True)
            ret.save(output_dir)
            progress.advance(task)

    # simulation summary
    scenario_names: List[str] = [s.name for s in target_scenarios]
    (output_path / "summary.json").write_text(json.dumps(scenario_names, indent=4))
    console.print(f"Simulation completed for scenarios: {', '.join(scenario_names)}")
    console.print(
        f"All simulations completed successfully. output saved to {output_path.absolute()}"
    )


if __name__ == "__main__":
    cli()
