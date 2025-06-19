import machine
import utime
import uasyncio

from sim.nandio_pio import NandConfig
from mpy.driver import FwNandCommander, NandIo, PioNandCommander


async def test_erase_program(
    commander: FwNandCommander | PioNandCommander,
    src_data: bytearray,
) -> tuple[bytearray, int, int, int, int]:
    # 各時刻を控えながら実行
    checkpoint0_ms = utime.ticks_us()
    await commander.read_id(0)
    checkpoint1_ms = utime.ticks_us()
    await commander.erase_block(0, 0)
    checkpoint2_ms = utime.ticks_us()
    await commander.program_page(
        0,
        0,
        0,
        src_data,
    )
    checkpoint3_ms = utime.ticks_us()
    dst_data = await commander.read_page(0, 0, 0, 0)
    checkpoint4_ms = utime.ticks_us()
    assert dst_data is not None, "Read data is None"

    # 時間集計
    read_id_us = utime.ticks_diff(checkpoint1_ms, checkpoint0_ms)
    erase_block_us = utime.ticks_diff(checkpoint2_ms, checkpoint1_ms)
    program_page_us = utime.ticks_diff(checkpoint3_ms, checkpoint2_ms)
    read_page_us = utime.ticks_diff(checkpoint4_ms, checkpoint3_ms)
    return dst_data, read_id_us, erase_block_us, program_page_us, read_page_us


async def main() -> None:
    # Uncomment the line below to set the CPU frequency to 250 MHz for testing or performance tuning.
    # machine.freq(250_000_000)
    print(f"CPU frequency: {machine.freq() * 1e-6} MHz")

    src_data = bytearray([x & 0xFF for x in range(NandConfig.PAGE_ALL_BYTES)])
    nandio = NandIo()
    targets = [
        ("Fw", FwNandCommander(nandio)),
        ("Pio", PioNandCommander(nandio)),
    ]

    for name, commander in targets:
        (
            dst_data,
            read_id_us,
            erase_block_us,
            program_page_us,
            read_page_us,
        ) = await test_erase_program(
            commander,
            src_data,
        )
        print(
            f"# `{name}` commander results:\n"
            f"- Read ID time      : {read_id_us} us\n"
            f"- Erase block time  : {erase_block_us} us\n"
            f"- Program page time : {program_page_us} us\n"
            f"- Read page time    : {read_page_us} us\n"
        )

        assert dst_data == src_data, (
            f"{name} commander: Data mismatch after program\n got: {dst_data.hex()}\nexpected: {src_data.hex()}"
        )


if __name__ == "__main__":
    uasyncio.run(main())
