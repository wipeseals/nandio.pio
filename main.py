from sim.nandio_pio import NandConfig
import utime
import uasyncio

from mpy.driver import FwNandCommander, NandIo, PioNandCommander


async def test_erase_program(
    commander: FwNandCommander | PioNandCommander,
    src_data: bytearray,
) -> bytearray:
    await commander.erase_block(0, 0)
    await commander.program_page(
        0,
        0,
        0,
        src_data,
    )
    dst_data = await commander.read_page(0, 0, 0, 0)
    assert dst_data is not None, "Read data is None"
    return dst_data


async def test_erase_program_fw(src_data: bytearray) -> bytearray:
    commander = FwNandCommander(NandIo(keep_wp=False))
    return await test_erase_program(commander, src_data)


async def test_erase_program_pio(src_data: bytearray) -> bytearray:
    commander = PioNandCommander(NandIo(keep_wp=False))
    return await test_erase_program(commander, src_data)


async def main() -> None:
    src_data = bytearray([x & 0xFF for x in range(NandConfig.PAGE_ALL_BYTES)])

    start_ms = utime.ticks_ms()
    dst_data_pio = await test_erase_program_pio(src_data)
    elapsed_ms_pio = utime.ticks_diff(utime.ticks_ms(), start_ms)
    print(f"PIO erase/program time: {elapsed_ms_pio} ms")

    start_ms = utime.ticks_ms()
    dst_data_fw = await test_erase_program_fw(src_data)
    elapsed_ms_fw = utime.ticks_diff(utime.ticks_ms(), start_ms)
    print(f"FW commander erase/program time: {elapsed_ms_fw} ms")

    assert dst_data_pio == dst_data_fw, (
        f"Data mismatch between PIO and FW commander.\npio:{dst_data_pio.hex()}\nfw :{dst_data_fw.hex()}"
    )


if __name__ == "__main__":
    uasyncio.run(main())
