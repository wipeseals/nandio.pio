import uasyncio
import utime

from mpy.driver import FwNandCommander, NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer
from sim.nandio_pio import (
    LBA,
    NandConfig,
)


async def main() -> None:
    nandio = NandIo(keep_wp=False)
    commander = PioNandCommander(nandio)

    ret = await commander.program_page(
        chip_index=0, block=0, page=0, data=bytearray(range(128))
    )
    print(f"Program page result: {ret}")


if __name__ == "__main__":
    uasyncio.run(main())
