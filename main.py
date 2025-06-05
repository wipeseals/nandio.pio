import uasyncio
import utime

from mpy.driver import FwNandCommander, NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer
from sim.nandio_pio import (
    LBA,
    NandConfig,
)


async def main() -> None:
    nandio = NandIo()
    fw_commander = FwNandCommander(nandio)
    commander = PioNandCommander(nandio)
    commanders = [commander, fw_commander]
    for commander in commanders:  # commander: FwNandCommander | PioNandCommander
        start_time = utime.ticks_ms()
        print(f"Testing {commander.__class__.__name__}...")

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Initializing..."
        )
        id = await commander.read_id(0)
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Read ID: {id}"
        )

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Reading Status..."
        )
        data = await commander.read_page(chip_index=0, block=0, page=0, col=0)
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Read Page Data: {list(data)}"
        )

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Reading Status..."
        )
        status = await commander.read_status(chip_index=0)
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Read Status: {status:02x}"
        )

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Erasing Block 0..."
        )
        is_erased = await commander.erase_block(chip_index=0, block=0)
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Erase Block Result: {'Success' if is_erased else 'Failure'}"
        )

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Reading Page 0..."
        )
        data = await commander.read_page(chip_index=0, block=0, page=0, col=0)
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Read Page Data: {list(data)}"
        )

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Programming Page 0..."
        )
        is_programmed = await commander.program_page(
            chip_index=0,
            block=0,
            page=0,
            data=bytearray([x & 0xFF for x in range(NandConfig.PAGE_ALL_BYTES)]),
            col=0,
        )
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Program Page Result: {'Success' if is_programmed else 'Failure'}"
        )

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Reading Page 0 again..."
        )
        data = await commander.read_page(chip_index=0, block=0, page=0, col=0)
        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] Read Page Data: {list(data)}"
        )

        # ftl = FlashTranslationLayer(nandio, commander)
        # await ftl.init(is_initial=False)

        # def create_test_data(lba: LBA) -> bytearray:
        #     return bytearray([lba] * NandConfig.SECTOR_BYTES)

        # for lba in range(0, 10):
        #     await ftl.write_logical(lba, create_test_data(lba))
        # for lba in reversed(range(0, 10)):
        #     read_data = await ftl.read_logical(lba)
        #     print(f"LBA {lba} -> Read Data: {list(read_data)}")
        #     assert read_data is not None, f"Read data is None for LBA {lba}"

        print(
            f"[{utime.ticks_diff(utime.ticks_ms(), start_time)}ms][{commander.__class__.__name__}] finish."
        )


if __name__ == "__main__":
    uasyncio.run(main())
