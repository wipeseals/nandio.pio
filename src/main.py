from dataclasses import dataclass
from typing import List
import rich_click as click
from pathlib import Path
import logging
from rich.logging import RichHandler
from src.nandio_pio import PioCmdBuilder
from rich.progress import Progress

from src.simulator import Result, Simulator


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
    SimScenario("reset", PioCmdBuilder.seq_reset(cs=0), test_cycles=40),
    SimScenario("read_id", PioCmdBuilder.seq_read_id(cs=0), test_cycles=100),
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
        click.secho(
            "No scenarios selected. Use --all to run all scenarios or --scenario to specify one.",
            fg="red",
        )
        return

    with Progress() as progress:
        task = progress.add_task(
            "Simulating all scenarios...", total=len(target_scenarios)
        )
        for scenario in target_scenarios:
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
