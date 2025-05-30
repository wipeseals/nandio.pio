import array
import datetime
import json
import os
import adafruit_pioasm
from dataclasses import dataclass
from typing import Callable, List
import rich
import rich_click as click
from pathlib import Path
import logging
from rich.logging import RichHandler
from sim.nandio_pio import PioCmdBuilder
from rich.progress import Progress
import zlib  # 追加

from sim.simulator import Result, Simulator

console = rich.get_console()


@dataclass
class SimScenario:
    name: str
    payload_f: Callable[[array.array], None]
    test_cycles: int = 100


SCENARIOS: List[SimScenario] = [
    SimScenario(
        "reset", lambda arr: PioCmdBuilder.seq_reset(arr=arr, cs=0), test_cycles=100
    ),
    SimScenario(
        "read_id", lambda arr: PioCmdBuilder.seq_read_id(arr=arr, cs=0), test_cycles=100
    ),
    SimScenario(
        "read",
        lambda arr: PioCmdBuilder.seq_read(
            arr=arr, cs=0, column_addr=0, page_addr=0, block_addr=1023, data_count=32
        ),
        test_cycles=300,
    ),
    SimScenario(
        "program",
        lambda arr: PioCmdBuilder.seq_program(
            arr=arr,
            cs=0,
            column_addr=0,
            page_addr=0,
            block_addr=1023,
            data=array.array("I", range(32)),  # dataもarray.arrayで渡す
        ),
        test_cycles=300,
    ),
    SimScenario(
        "erase",
        lambda arr: PioCmdBuilder.seq_erase(arr=arr, cs=0, block_addr=1023),
        test_cycles=200,
    ),
    SimScenario(
        "status_read",
        lambda arr: PioCmdBuilder.seq_status_read(arr=arr, cs=0),
        test_cycles=50,
    ),
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
def asm(
    pio_path: Path,
    bin_path: Path | None = None,
):
    """Assemble the PIO program."""
    if not pio_path.exists():
        console.print(f"[red]PIO file {pio_path} does not exist.[/red]")
        return
    if bin_path is None:
        bin_path = pio_path.with_suffix(".bin")

    program_str = Path(pio_path).read_text(encoding="utf-8")
    opcodes_arr: array.array = adafruit_pioasm.assemble(program_str)
    bin_path.write_bytes(opcodes_arr.tobytes())

    console.print(
        f"[green]PIO program assembled successfully![/green]\n"
        f"Output binary saved to: {bin_path.absolute()}"
    )


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
            # payload_fにarray.arrayを渡してtx_fifo_entriesを生成
            tx_fifo_entries = array.array("I")
            scenario.payload_f(tx_fifo_entries)
            ret: Result = Simulator.execute(
                program_str=program_str,
                test_cycles=scenario.test_cycles,
                tx_fifo_entries=tx_fifo_entries,
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
