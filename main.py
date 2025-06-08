import uasyncio

from mpy.driver import NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer


async def main() -> None:
    nandio = NandIo(keep_wp=False)
    commander = PioNandCommander(nandio)
    ftl = FlashTranslationLayer(nandio, commander)
    await ftl.setup()

    print(f"badblocks[0]{ftl.blockmng.badblock_bitmaps[0]:x}")


if __name__ == "__main__":
    uasyncio.run(main())
