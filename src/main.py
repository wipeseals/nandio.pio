from dataclasses import dataclass
from typing import List
import rich_click as click
from pathlib import Path
import logging
from rich.logging import RichHandler
from src.nandio_pio import PioCmdBuilder
from rich.progress import Progress

from src.simulator import Result, Simulator


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
    pass


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
    "--cs",
    required=True,
    type=int,
    default=0,
)
def sim_all(
    pio_path: Path,
    output_path: Path,
    cs: int,
):
    """Simulate all PioCmdBuilder sequences."""

    @dataclass
    class SimScenario:
        name: str
        payload: list[int]
        test_cycles: int = 100

    program_str = Path(pio_path).read_text(encoding="utf-8")
    scenarios: List[SimScenario] = [
        SimScenario("reset", PioCmdBuilder.seq_reset(cs=cs), test_cycles=40),
        SimScenario("read_id", PioCmdBuilder.seq_read_id(cs=cs), test_cycles=100),
    ]

    with Progress() as progress:
        task = progress.add_task("Simulating all scenarios...", total=len(scenarios))
        for scenario in scenarios:
            ret: Result = Simulator.execute(
                program_str=program_str,
                test_cycles=scenario.test_cycles,
                tx_fifo_entries=scenario.payload,
            )
            output_dir = output_path / scenario.name
            output_dir.mkdir(parents=True, exist_ok=True)
            ret.save(output_dir)
            click.secho(f" ... '{scenario.name}' {scenario.test_cycles}cyc")
            progress.advance(task)
    click.secho(
        f"All simulations completed successfully. output saved to {output_path.absolute()}"
    )


if __name__ == "__main__":
    cli()
