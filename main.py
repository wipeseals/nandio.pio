from sim.nandio_pio import NandConfig
import uasyncio

from mpy.driver import FwNandCommander, NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer


def set_test_data(buf: bytearray, lba: int):
    for i in range(len(buf)):
        buf[i] = (lba + i) & 0xFF
    return buf


async def test_seq_wr(ftl: FlashTranslationLayer, num_lb: int | None = None) -> None:
    # 指定金ければ全域
    if num_lb is None:
        num_lb = ftl.report_capacity_lb()
    buf = bytearray(NandConfig.SECTOR_BYTES)

    print(f"Starting sequential write test for {num_lb} logical blocks.")
    for lba in range(num_lb):
        print(f"Writing logical block {lba}...")
        data = set_test_data(buf, lba)
        await ftl.write_logical(lba, buf)
    print("Sequential write test completed.")

    await ftl.flush()

    print(f"Reading back {num_lb} logical blocks to verify...")
    for lba in range(num_lb):
        data = await ftl.read_logical(lba)
        set_test_data(buf, lba)
        assert data == buf, f"Data mismatch at LBA {lba}: {data.hex()} != {buf.hex()}"
    print("Data verification successful.")


async def test_sample(ftl: FlashTranslationLayer) -> None:
    buf = bytearray(NandConfig.SECTOR_BYTES)
    print("Writing and reading logical blocks...")
    await ftl.write_logical(0, set_test_data(buf, 0))
    await ftl.write_logical(1, set_test_data(buf, 1))

    print("Reading back logical blocks...")
    assert await ftl.read_logical(0) == set_test_data(buf, 0)
    assert await ftl.read_logical(1) == set_test_data(buf, 1)

    print("Flushing changes to NAND...")
    await ftl.flush()

    print("Reading back logical blocks after flush...")
    assert await ftl.read_logical(0) == set_test_data(buf, 0)
    assert await ftl.read_logical(1) == set_test_data(buf, 1)


async def test_low_level(commander: FwNandCommander | PioNandCommander) -> None:
    print(await commander.reset(0))
    print(await commander.read_id(0))
    print(await commander.read_page(0, 0, 0, 0))
    print(await commander.erase_block(0, 0))
    print(await commander.read_page(0, 0, 0, 0))
    print(await commander.program_page(0, 0, 0, bytearray(range(2048))))
    print(await commander.read_page(0, 0, 0, 0))


async def main() -> None:
    nandio = NandIo(keep_wp=False)
    commander = PioNandCommander(nandio)
    # commander = FwNandCommander(nandio)

    await test_low_level(commander)

    # ftl = FlashTranslationLayer(nandio, commander)
    # try:
    #     ftl.load_config()
    #     print(f"Config loaded successfully. {ftl.config._data}")
    # except Exception as e:
    #     print(f"Failed to load config: {e}")
    #     await ftl.init_config()
    # # reset NAND IC
    # await ftl.setup_nandio()

    # await test_sample(ftl)
    # await test_seq_wr(ftl, num_lb=ftl.report_capacity_lb())

    # ftl.save_config()
    # ftl.save_config()
    # print(f"config: {ftl.config._data}")


if __name__ == "__main__":
    uasyncio.run(main())
