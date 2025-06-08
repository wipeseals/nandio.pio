import json
from mpy.driver import NandIo, FwNandCommander, PioNandCommander
from sim.nandio_pio import BLOCK, CHIP, LBA, PAGE, PBA, NandConfig


class FtlConfig:
    """FTL Configuration"""

    def __init__(self, filepath: str = "ftl.json") -> None:
        self._filepath = filepath
        self._data = dict()

    def load(self) -> bool:
        f = open(self._filepath, "r")
        json_text = f.read()
        self._data = json.loads(json_text)
        f.close()
        return True

    def save(self) -> bool:
        json_str = json.dumps(self._data)
        f = open(self._filepath, "w")
        f.write(json_str)
        f.close()
        return True

    def get(self, key: str, default=None) -> any:
        return self._data.get(key, default)

    def set(self, key: str, value, save: bool = False) -> None:
        self._data[key] = value
        if save:
            self.save()


class NandBlockManager:
    def __init__(
        self,
        nandcmd: FwNandCommander | PioNandCommander,
    ) -> None:
        self._nandcmd = nandcmd
        self.num_chip: int = 0
        self.badblock_bitmaps: list[int] = []

    ########################################################
    # Wrapper functions
    ########################################################
    async def _check_chip_num(
        self,
        check_num_chip: CHIP = 2,
        expect_id: bytearray = NandConfig.READ_ID_EXPECT,
    ) -> int:
        num_chip = 0
        for chip_index in range(check_num_chip):
            id = await self._nandcmd.read_id(chip_index=chip_index)
            is_ok = id == expect_id
            if not is_ok:
                return num_chip
            num_chip += 1
        return num_chip

    async def _check_allbadblocks(
        self, chip_index: CHIP, num_blocks: int = NandConfig.BLOCKS_PER_CS
    ) -> int:
        badblock_bitmap = 0
        for block in range(num_blocks):
            data = await self._nandcmd.read_page(
                chip_index=chip_index, block=block, page=0, col=0, num_bytes=1
            )
            # Read Exception
            if data is None:
                raise ValueError(
                    f"Read Error: Chip {chip_index}, Block {block}, Page 0"
                )
            # Check Bad Block
            is_bad = data[0] != 0xFF
            if is_bad:
                badblock_bitmap |= 1 << block
        return badblock_bitmap

    async def init_config(self) -> None:
        """NAND Flashの初期化"""
        if self.num_chip == 0:
            self.num_chip = await self._check_chip_num()
        if self.num_chip == 0:
            raise ValueError("No Active CS")

        # badblock
        # Read Pageを投げて、BadBlockをチェック
        self.badblock_bitmaps = []
        for chip_index in range(self.num_chip):
            self.badblock_bitmaps.append(0)
            bitmaps = await self._check_allbadblocks(chip_index=chip_index)
            self.badblock_bitmaps[chip_index] = bitmaps

        # allocated bitmap
        # badblock部分は確保済としてマーク
        self.allocated_bitmaps = [0] * self.num_chip
        for chip_index in range(self.num_chip):
            self.allocated_bitmaps[chip_index] = self.badblock_bitmaps[chip_index]

    def load_config(self, config: FtlConfig) -> bool:
        """Load FTL Configuration"""
        self.num_chip = config.get("num_chip", 0)
        self.badblock_bitmaps = config.get("badblock_bitmaps", [])
        self.allocated_bitmaps = config.get("allocated_bitmaps", [])
        return True

    def save_config(self, config: FtlConfig) -> bool:
        """Save FTL Configuration"""
        config.set("num_chip", self.num_chip, save=False)
        config.set("badblock_bitmaps", self.badblock_bitmaps, save=False)
        config.set("allocated_bitmaps", self.allocated_bitmaps, save=False)
        return True

    def _pick_free(self) -> tuple[CHIP | None, BLOCK | None]:
        """空きBlockを探す"""
        # 先頭から空きを探す
        # TODO: Wear Levelingを考慮して、ランダムに選ぶようにする
        for chip_index in range(self.num_chip):
            for block in range(NandConfig.BLOCKS_PER_CS):
                # free & not badblock
                if (self.allocated_bitmaps[chip_index] & (1 << block)) == 0 and (
                    self.badblock_bitmaps[chip_index] & (1 << block)
                ) == 0:
                    return chip_index, block
        return None, None

    def _mark_alloc(self, chip_index: CHIP, block: BLOCK) -> None:
        """Blockを確保済としてマーク"""
        if (self.allocated_bitmaps[chip_index] & (1 << block)) != 0:
            raise ValueError("Block Already Allocated")

        self.allocated_bitmaps[chip_index] |= 1 << block

    def _mark_free(self, chip_index: CHIP, block: BLOCK) -> None:
        """Blockを解放済としてマーク"""
        if (self.allocated_bitmaps[chip_index] & (1 << block)) == 0:
            raise ValueError("Block Already Free")

        self.allocated_bitmaps[chip_index] &= ~(1 << block)

    def _mark_bad(self, chip_index: CHIP, block: BLOCK) -> None:
        """BlockをBadBlockとしてマーク"""
        self.badblock_bitmaps[chip_index] |= 1 << block

    async def alloc(self) -> tuple[CHIP, BLOCK]:
        """空きBlockを確保"""
        while True:
            cs, block = self._pick_free()
            if block is None or cs is None:
                raise ValueError("No Free Block")
            else:
                # Erase OKのものを採用。だめならやり直し
                is_erase_ok = await self._nandcmd.erase_block(
                    chip_index=cs, block=block
                )
                if is_erase_ok:
                    self._mark_alloc(chip_index=cs, block=block)
                    return cs, block
                else:
                    # Erase失敗、BadBlockとしてマークし、Freeせず次のBlockを探す
                    self._mark_bad(chip_index=cs, block=block)

    async def free(self, chip_index: CHIP, block: BLOCK) -> None:
        """Blockを解放"""
        self._mark_free(chip_index=chip_index, block=block)

    async def read(
        self, chip_index: CHIP, block: BLOCK, page: PAGE
    ) -> bytearray | None:
        """指定されたページを読み出す"""
        return await self._nandcmd.read_page(
            chip_index=chip_index, block=block, page=page
        )

    async def program(
        self, chip_index: CHIP, block: BLOCK, page: PAGE, data: bytearray
    ) -> bool:
        """指定されたページにデータを書き込む"""
        return await self._nandcmd.program_page(
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


# Logical Block Address Group
LBG = int


class Mapping:
    # (2048byte * 64page) / 512byte = 256 [LBA/LBG]
    LBA_PER_LBG = (
        NandConfig.PAGE_USABLE_BYTES * NandConfig.PAGES_PER_BLOCK
    ) // NandConfig.SECTOR_BYTES

    @staticmethod
    def lba_to_lbg(lba: LBA) -> LBG:
        """Convert Logical Block Address to Logical Block Group"""
        return lba // Mapping.LBA_PER_LBG

    @staticmethod
    def lbg_to_lba(lbg: LBG, offset_lba: LBA = 0) -> LBA:
        """Convert Logical Block Group to Logical Block Address"""
        return lbg * Mapping.LBA_PER_LBG + offset_lba

    def __init__(self) -> None:
        # Mapping from Logical Block Group (LBG) to NAND Block (Chip, Block)
        self._mapping: dict[LBG, tuple[CHIP, BLOCK]] = {}

    async def init_config(self) -> None:
        """Initialize the mapping configuration"""
        self._mapping.clear()

    def save_config(self, config: FtlConfig) -> bool:
        """Save the mapping configuration to FTL config"""
        config.set("mapping", self._mapping, save=False)
        return True

    def load_config(self, config: FtlConfig) -> bool:
        """Load the mapping configuration from FTL config"""
        self._mapping = config.get("mapping", {})
        return True


class FlashTranslationLayer:
    """
    Flash Translation Layer class

    前提
    - NAND Page Size: 2048 byte
    - NAND Block Size: 128 KiB (64page * 2048 byte)
    - Maximum Chip Size: 128 MiB (1024 Block * 128 KiB)
    - Maximum Size: 256 MiB (2 Chip * 128 MiB)
    - LBA (Logical Block Address):  512 byte
    - SRAM Size: 264 KiB (RP2040のSRAMサイズ)

    実装案
    - NAND Page単位マッピング: 柔軟だが、マッピングテーブルが大きくなる
    - NAND Block単位マッピング: マッピングテーブルが小さくなるが、柔軟性が低い (採用)

    方式
    - 128 KiB / 512 byte = 256 LBA を 1 Logical Block Group (LBGと呼ぶことにする) 単位で管理
    - 必要なマッピングテーブルは、 Max Size / LBG Size = 256 MiB / 128 KiB = 2048 LBG = 4 KiB
        - 2byte (2048blockなので11bitあればよい) / LBG = 4096 byte = 4 KiB
    - SRAM上に 1 LBG 分の Buffer を持ち、そこに書き込みを行う
    - Write
        - LBG 範囲内のアクセスは SRAM上のBufferに書き込み
        - LBG 範囲外のアクセスもしくはデータ確定が必要な場合、 NAND Flashに書き込み
    - Read
        - LBG 範囲内のアクセスは SRAM上のBufferから読み出し
        - LBG 範囲外のアクセスは NAND Flashから読み出し
            - 読み出しは Page単位で行う
    """

    def __init__(
        self,
        nandio: NandIo,
        nandcmd: FwNandCommander | PioNandCommander,
        config: FtlConfig | None = None,
    ) -> None:
        # NAND IO Drivers/Commander, Config
        self.nandio = nandio
        self.nandcmd = nandcmd
        self.config = config if config is not None else FtlConfig()

        # NAND Block Manager
        self._blockmng = NandBlockManager(nandcmd=self.nandcmd)
        # Mapping
        self._mapping = Mapping()

    async def init_config(self) -> None:
        """FTLの初期化 (初めて起動したときの設定)"""
        await self._blockmng.init_config()
        await self._mapping.init_config()

    def save_config(self) -> bool:
        """FTLの設定を反映して保存"""
        self._blockmng.save_config(self.config)
        self._mapping.save_config(self.config)
        return self.config.save()

    def load_config(self) -> bool:
        """FTLの設定を読み込み"""
        if not self.config.load():
            return False
        self._blockmng.load_config(self.config)
        self._mapping.load_config(self.config)
        return True
