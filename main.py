from mpy.driver import NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer
from sim.nandio_pio import LBA, NandConfig


def test_pio() -> None:
    nandio = NandIo()
    pio_commander = PioNandCommander(nandio)
    pio_commander.read_id(0)


def main() -> None:
    ftl = FlashTranslationLayer()

    def create_test_data(lba: LBA) -> bytearray:
        return bytearray([lba] * NandConfig.SECTOR_BYTES)

    for lba in range(0, 10):
        ftl.write_logical(lba, create_test_data(lba))
    for lba in reversed(range(0, 10)):
        read_data = ftl.read_logical(lba)
        print(f"LBA {lba} -> Read Data: {list(read_data)}")
        assert read_data is not None, f"Read data is None for LBA {lba}"


if __name__ == "__main__":
    test_pio()
    # main()
