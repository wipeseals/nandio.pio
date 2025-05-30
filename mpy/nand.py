import sys
import json
import math

# Physical Block Address
PBA = int
# chip id type
CHIP = int
# block id type
BLOCK = int
# page type
PAGE = int
# sector type
SECTOR = int
# column type
COLUMN = int
# block bitmap type
BLOCK_BITMAP = int


############################################################################
# NAND Flash Definitions for TC58NVG0S3HTA00
############################################################################
class NandCmd:
    READ_ID = 0x90
    READ_1ST = 0x00
    READ_2ND = 0x30
    ERASE_1ST = 0x60
    ERASE_2ND = 0xD0
    STATUS_READ = 0x70
    PROGRAM_1ST = 0x80
    PROGRAM_2ND = 0x10


class NandStatus:
    PROGRAM_ERASE_FAIL = 0x01
    CACHE_PROGRAM_FAIL = 0x02
    PAGE_BUFFER_READY = 0x20
    DATA_CACHE_READY = 0x40
    WRITE_PROTECT_DISABLE = 0x80


class NandConfig:
    """
    NAND Flash Configuration for JISC-SSD TC58NVG0S3HTA00
    note: 動作中に別NANDに切り替えることはないのでinstanceを撒かない
          現時点ではJISC-SSD以外のターゲットは想定していないのでdataclassのような動的な値決めのクラスとしては機能しない
    """

    # JISC-SSD TC58NVG0S3HTA00 x 2
    MAX_CS = 2
    # ID Read Command for TC58NVG0S3HTA00
    READ_ID_EXPECT = bytearray([0x98, 0xF1, 0x80, 0x15, 0x72])
    # data area
    PAGE_USABLE_BYTES = 2048
    # spare area
    PAGE_SPARE_BYTES = 128
    # 2048byte(main) + 128byte(redundancy or other uses)
    PAGE_ALL_BYTES = PAGE_USABLE_BYTES + PAGE_SPARE_BYTES
    # number of pages per block
    PAGES_PER_BLOCK = 64
    # number of blocks per CS
    BLOCKS_PER_CS = 1024
    # sector size
    SECTOR_BYTES = 512
    # number of sectors per page (2048byte / 512byte = 4)
    SECTOR_PER_PAGE = PAGE_USABLE_BYTES // SECTOR_BYTES

    # sector bits (log2(4) = 2)
    SECTOR_BITS = math.ceil(math.log2(SECTOR_PER_PAGE))
    # page bits (log2(64) = 6)
    PAGE_BITS = math.ceil(math.log2(PAGES_PER_BLOCK))
    # block bits (log2(1024) = 10)
    BLOCK_BITS = math.ceil(math.log2(BLOCKS_PER_CS))
    # cs bits (log2(2) = 1)
    CS_BITS = math.ceil(math.log2(MAX_CS))
    # total bits
    TOTAL_BITS = SECTOR_BITS + PAGE_BITS + BLOCK_BITS + CS_BITS

    # sector mask (2^2 - 1 = 0x3)
    SECTOR_MASK = (1 << SECTOR_BITS) - 1
    # page mask (2^6 - 1 = 0x3F)
    PAGE_MASK = (1 << PAGE_BITS) - 1
    # block mask (2^10 - 1 = 0x3FF)
    BLOCK_MASK = (1 << BLOCK_BITS) - 1
    # cs mask (2^1 - 1 = 0x1)
    CS_MASK = (1 << CS_BITS) - 1

    @staticmethod
    def decode_phys_addr(addr: PBA) -> tuple[CHIP, BLOCK, PAGE, SECTOR]:
        """Decode NAND Flash Address
        | chip[0] | block[9:0] | page[5:0] | sector[1:0] |
        """
        sector = addr & NandConfig.SECTOR_MASK
        addr >>= NandConfig.SECTOR_BITS
        page = addr & NandConfig.PAGE_MASK
        addr >>= NandConfig.PAGE_BITS
        block = addr & NandConfig.BLOCK_MASK
        addr >>= NandConfig.BLOCK_BITS
        chip = addr & NandConfig.CS_MASK
        addr >>= NandConfig.CS_BITS
        return chip, block, page, sector

    @staticmethod
    def encode_phys_addr(chip: CHIP, block: BLOCK, page: PAGE, sector: SECTOR) -> PBA:
        """Encode NAND Flash Address
        | chip[0] | block[9:0] | page[5:0] | sector[1:0] |
        """
        addr = chip & NandConfig.CS_MASK
        addr <<= NandConfig.BLOCK_BITS
        addr |= block & NandConfig.BLOCK_MASK
        addr <<= NandConfig.PAGE_BITS
        addr |= page & NandConfig.PAGE_MASK
        addr <<= NandConfig.SECTOR_BITS
        addr |= sector & NandConfig.SECTOR_MASK
        return addr

    @staticmethod
    def create_nand_addr(block: BLOCK, page: PAGE, col: COLUMN) -> bytearray:
        """Create NAND Flash Address

        | cycle# | Data                  |
        |--------|-----------------------|
        | 0      | COL[7:0]              |
        | 1      | COL[15:8]             |
        | 2      | BLOCK[1:0], PAGE[5:0] |
        | 3      | BLOCK[10:2]           |
        """
        addr = bytearray()
        addr.append(col & 0xFF)
        addr.append((col >> 8) & 0xFF)
        addr.append(((block & 0x3) << 6) | (page & 0x3F))
        addr.append((block >> 2) & 0xFF)
        return addr

    @staticmethod
    def create_block_addr(block: BLOCK) -> bytearray:
        """Create NAND Flash Block Address

        | cycle | Data      |
        |-------|-----------|
        | 0     | BLOCK[7:0]|
        | 1     | BLOCK[15:8]|
        """
        addr = bytearray()
        addr.append(block & 0xFF)
        addr.append((block >> 8) & 0xFF)
        return addr


############################################################################
# RP2040 Driver or Simulator
############################################################################

sim_platforms = ["linux", "windows", "webassembly", "qemu"]
if sys.platform in sim_platforms:
    # Simulator
    import mpy.driver_sim as d_sim
else:
    # RP2040 Driver
    import mpy.driver_rp2 as d_rp2


def get_driver(
    keep_wp: bool = True,
) -> tuple[d_sim.NandIo | d_rp2.NandIo, d_sim.NandCommander | d_rp2.NandCommander]:
    is_sim = sys.platform in sim_platforms
    if is_sim:
        nandio = d_sim.NandIo(keep_wp=keep_wp)
        nandcmd = d_sim.NandCommander(nandio=nandio)
        return nandio, nandcmd
    else:
        nandio = d_rp2.NandIo(keep_wp=keep_wp)
        nandcmd = d_rp2.NandCommander(nandio=nandio, timeout_ms=1000)
        return nandio, nandcmd


class NandBlockManager:
    def __init__(
        self,
        nandcmd: d_sim.NandCommander | d_rp2.NandCommander,
        # initialized values
        is_initial: bool = False,
        num_chip: CHIP = 0,
        initial_badblock_bitmaps: list[int] | None = None,
    ) -> None:
        self._nandcmd = nandcmd

        if not is_initial:
            try:
                self.load()
            except OSError as e:
                is_initial = True

        if is_initial:
            self.num_chip: CHIP = num_chip
            self.badblock_bitmaps = (
                initial_badblock_bitmaps if initial_badblock_bitmaps else []
            )
            self.init()
            # save initialized values
            self.save()

    def save(self, filepath: str = "nand_block_allocator.json") -> None:
        json_str = json.dumps(
            {
                "num_chip": self.num_chip,
                "badblock_bitmaps": self.badblock_bitmaps,
                "allocated_bitmaps": self.allocated_bitmaps,
            }
        )
        try:
            f = open(filepath, "w")
            f.write(json_str)
            f.close()
            trace(f"BLKMNG\t{self.save.__name__}\t{filepath}\t{json_str}")
        except OSError as e:
            raise e

    def load(self, filepath: str = "nand_block_allocator.json") -> None:
        try:
            f = open(filepath, "r")
            json_text = f.read()
            data = json.loads(json_text)
            self.num_chip = data["num_chip"]
            self.badblock_bitmaps = data["badblock_bitmaps"]
            self.allocated_bitmaps = data["allocated_bitmaps"]
            f.close()
        except OSError as e:
            raise e

    ########################################################
    # Wrapper functions
    ########################################################
    def _check_chip_num(
        self,
        check_num_chip: CHIP = 2,
        expect_id: bytearray = NandConfig.READ_ID_EXPECT,
    ) -> int:
        num_chip = 0
        for chip_index in range(check_num_chip):
            id = self._nandcmd.read_id(chip_index=chip_index)
            is_ok = id == expect_id
            if not is_ok:
                return num_chip
            num_chip += 1
        return num_chip

    def _check_allbadblocks(
        self, chip_index: CHIP, num_blocks: int = NandConfig.BLOCKS_PER_CS
    ) -> int | None:
        badblock_bitmap = 0
        for block in range(num_blocks):
            data = self._nandcmd.read_page(
                chip_index=chip_index, block=block, page=0, col=0, num_bytes=1
            )
            # Read Exception
            if data is None:
                return None
            # Check Bad Block
            is_bad = data[0] != 0xFF
            if is_bad:
                badblock_bitmap |= 1 << block
        return badblock_bitmap

    ########################################################
    # Application functions
    ########################################################
    def init(self) -> None:
        # cs
        if self.num_chip == 0:
            self.num_chip = self._check_chip_num()
        if self.num_chip == 0:
            raise ValueError("No Active CS")

        # badblock
        if self.badblock_bitmaps is None:
            self.badblock_bitmaps = []
        for chip_index in range(self.num_chip):
            # 片方のCSだけ初期値未設定ケースがあるので追加してからチェックした値をセット
            if chip_index < len(self.badblock_bitmaps):
                # 既に設定済
                pass
            else:
                self.badblock_bitmaps.append(0)
                bitmaps = self._check_allbadblocks(chip_index=chip_index)
                if bitmaps is None:
                    raise ValueError("BadBlock Check Error")
                else:
                    self.badblock_bitmaps[chip_index] = bitmaps
        # allocated bitmap
        self.allocated_bitmaps = [0] * self.num_chip
        # badblock部分は確保済としてマーク
        for chip_index in range(self.num_chip):
            self.allocated_bitmaps[chip_index] = self.badblock_bitmaps[chip_index]

    def _pick_free(self) -> tuple[CHIP | None, BLOCK | None]:
        # 先頭から空きを探す
        for chip_index in range(self.num_chip):
            for block in range(NandConfig.BLOCKS_PER_CS):
                # free & not badblock
                if (self.allocated_bitmaps[chip_index] & (1 << block)) == 0 and (
                    self.badblock_bitmaps[chip_index] & (1 << block)
                ) == 0:
                    return chip_index, block
        return None, None

    def _mark_alloc(self, chip_index: CHIP, block: BLOCK) -> None:
        if (self.allocated_bitmaps[chip_index] & (1 << block)) != 0:
            raise ValueError("Block Already Allocated")

        self.allocated_bitmaps[chip_index] |= 1 << block

    def _mark_free(self, chip_index: CHIP, block: BLOCK) -> None:
        if (self.allocated_bitmaps[chip_index] & (1 << block)) == 0:
            raise ValueError("Block Already Free")

        self.allocated_bitmaps[chip_index] &= ~(1 << block)

    def _mark_bad(self, chip_index: CHIP, block: BLOCK) -> None:
        self.badblock_bitmaps[chip_index] |= 1 << block

    def alloc(self) -> tuple[CHIP, BLOCK]:
        while True:
            cs, block = self._pick_free()
            if block is None or cs is None:
                raise ValueError("No Free Block")
            else:
                # Erase OKのものを採用。だめならやり直し
                is_erase_ok = self._nandcmd.erase_block(chip_index=cs, block=block)
                if is_erase_ok:
                    self._mark_alloc(chip_index=cs, block=block)
                    return cs, block
                else:
                    # Erase失敗、BadBlockとしてマークし、Freeせず次のBlockを探す
                    self._mark_bad(chip_index=cs, block=block)

    def free(self, chip_index: CHIP, block: BLOCK) -> None:
        self._mark_free(chip_index=chip_index, block=block)

    def read(self, chip_index: CHIP, block: BLOCK, page: PAGE) -> bytearray | None:
        return self._nandcmd.read_page(chip_index=chip_index, block=block, page=page)

    def program(
        self, chip_index: CHIP, block: BLOCK, page: PAGE, data: bytearray
    ) -> bool:
        return self._nandcmd.program_page(
            chip_index=chip_index, block=block, page=page, data=data
        )


class Lfsr8:
    """Linear Feedback Shift Register"""

    def __init__(
        self,
        init_value: int = 1,
        seed: int = 0xA5,
    ) -> None:
        self._init_value = init_value
        self._current = init_value
        self._seed = seed

    def reset(self, init_value: int | None = None):
        if init_value is not None:
            self._current = init_value
        else:
            self._current = self._init_value

    def next(self) -> int:
        self._current = (
            (self._current >> 1) ^ (-(self._current & 1) & self._seed)
        ) & 0xFF
        return self._current


class PageCodec:
    """
    NAND Flash Page Encoder/Decoder
    Reference: https://github.com/wipeseals/broccoli/blob/main/misc/design-memo/data-layout.ipynb
    """

    def __init__(
        self,
        scramble_seed: int = 0xA5,
        use_scramble: bool = True,
        use_ecc: bool = True,
        use_crc: bool = True,
    ) -> None:
        self._scramble_seed = scramble_seed
        self._use_scramble = use_scramble
        self._use_ecc = use_ecc
        self._use_crc = use_crc

    def encode(self, data: bytearray) -> bytearray:
        assert len(data) == NandConfig.PAGE_USABLE_BYTES
        # TODO: scramble
        # lfsr = Lfsr8(seed=self._scramble_seed)
        # data = bytearray([lfsr.next() ^ x for x in data])
        # TODO: ecc
        # TODO: crc
        return data + bytearray(
            [0x00] * NandConfig.PAGE_SPARE_BYTES
        )  # TODO: 正式なParity付与

    def decode(self, data: bytearray) -> bytearray | None:
        assert len(data) == NandConfig.PAGE_ALL_BYTES

        # TODO: crc
        # TODO: ecc
        # TODO: descramble
        # lfsr = Lfsr8(seed=self._scramble_seed)
        # data = bytearray([lfsr.next() ^ x for x in data])
        # TODO: CRC Errorを解消できなかった場合、エラー応答する
        return data[: NandConfig.PAGE_USABLE_BYTES]  # Parity除去
