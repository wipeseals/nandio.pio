import uasyncio

from mpy.driver import NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer


async def main() -> None:
    nandio = NandIo(keep_wp=False)
    commander = PioNandCommander(nandio)
    ftl = FlashTranslationLayer(nandio, commander)
    try:
        ftl.load_config()
        print(f"Config loaded successfully. {ftl.config._data}")
    except Exception as e:
        print(f"Failed to load config: {e}")
        await ftl.setup_initial()

    ftl.save_config()
    print(f"Config saved successfully. {ftl.config._data}")


if __name__ == "__main__":
    uasyncio.run(main())
