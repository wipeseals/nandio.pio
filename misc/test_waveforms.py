import uasyncio

from mpy.driver import FwNandCommander, NandIo, PioNandCommander
from sim.nandio_pio import NandConfig


async def test_waveforms(commander: FwNandCommander | PioNandCommander) -> None:
    while True:
        print(f"Testing {commander.__class__.__name__}...")
        ret = await commander.program_page(
            chip_index=0,
            block=0xA5,
            page=0x5A,
            data=bytearray([x & 0xFF for x in range(NandConfig.PAGE_ALL_BYTES)]),
            col=0,
        )
        print(f"done: {ret}")
        await uasyncio.sleep(3)


# Use "MicroPico: Run current file on Pico"
if __name__ == "__main__":
    commander: FwNandCommander | PioNandCommander = PioNandCommander(
        NandIo(keep_wp=False),
        max_freq=100_000_000,
    )
    uasyncio.run(test_waveforms(commander))
