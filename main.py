from sim.nandio_pio import NandConfig
import uasyncio

from mpy.driver import FwNandCommander, NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer


def create_test_data(lba: int, length: int = NandConfig.SECTOR_BYTES) -> bytearray:
    return bytearray([(x + lba) & 0xFF for x in range(length)])


async def test_seq_wr(ftl: FlashTranslationLayer, num_lb: int | None = None) -> None:
    # 指定金ければ全域
    if num_lb is None:
        num_lb = ftl.report_capacity_lb()

    print(f"Starting sequential write test for {num_lb} logical blocks.")
    for lba in range(num_lb):
        print(f"Writing logical block {lba}...")
        data = create_test_data(lba)
        await ftl.write_logical(lba, data)
    print("Sequential write test completed.")

    await ftl.flush()

    print(f"Reading back {num_lb} logical blocks to verify...")
    for lba in range(num_lb):
        data = await ftl.read_logical(lba)
        expected_data = create_test_data(lba)
        assert data == expected_data, (
            f"Data mismatch at LBA {lba}: {data.hex()} != {expected_data.hex()}"
        )
    print("Data verification successful.")


async def test_sample(ftl: FlashTranslationLayer) -> None:
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


async def main() -> None:
    nandio = NandIo(keep_wp=False)
    commander = PioNandCommander(nandio)
    # commander = FwNandCommander(nandio)

    ftl = FlashTranslationLayer(nandio, commander)
    try:
        ftl.load_config()
        print(f"Config loaded successfully. {ftl.config._data}")
    except Exception as e:
        print(f"Failed to load config: {e}")
        await ftl.init_config()
    # reset NAND IC
    await ftl.setup_nandio()

    await test_sample(ftl)
    # await test_seq_wr(ftl, num_lb=ftl.report_capacity_lb())

    # ftl.save_config()
    ftl.save_config()
    print(f"config: {ftl.config._data}")


if __name__ == "__main__":
    uasyncio.run(main())
