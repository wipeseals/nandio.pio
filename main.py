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
        await ftl.init_config()

    def create_test_data(lba: int) -> bytearray:
        return bytearray([lba & 0xFF] * 512)

    print("Writing and reading logical blocks...")
    await ftl.write_logical(0, create_test_data(0))
    await ftl.write_logical(1, create_test_data(1))

    print("Reading back logical blocks...")
    assert await ftl.read_logical(0) == create_test_data(0)
    assert await ftl.read_logical(1) == create_test_data(1)

    print("Flushing changes to NAND...")
    await ftl.flush()

    print("Reading back logical blocks after flush...")
    assert await ftl.read_logical(0) == create_test_data(0)
    assert await ftl.read_logical(1) == create_test_data(1)

    # ftl.save_config()
    # print(f"Config saved successfully. {ftl.config._data}")


if __name__ == "__main__":
    uasyncio.run(main())
