import rich_click as click
from pathlib import Path
import logging
from rich.logging import RichHandler


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
@click.argument(
    "pio_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--output_path",
    required=True,
    type=click.Path(writable=True, path_type=Path),
    default="output",
)
def sim(
    pio_path: Path,
    output_path: Path,
):
    """Run the PIO simulation."""
    logging.debug(f"{pio_path=}, {output_path=}")


if __name__ == "__main__":
    cli()
