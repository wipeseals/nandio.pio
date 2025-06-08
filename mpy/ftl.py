import uasyncio
import rp2
import json
from mpy.driver import NandIo, FwNandCommander, PioNandCommander
from sim.nandio_pio import BLOCK, CHIP, LBA, PAGE, PBA, SECTOR, NandConfig

# Logical Block Address Group
LBG = int


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

    def num_blocks(self) -> int:
        """使用可能なNAND Block数を返す"""
        return self.num_chip * NandConfig.BLOCKS_PER_CS

    def num_usable_blocks(self) -> int:
        """使用可能なNAND Block数を返す"""
        num_usable = 0
        for chip_index in range(self.num_chip):
            num_usable += NandConfig.BLOCKS_PER_CS - bin(
                self.badblock_bitmaps[chip_index]
            ).count("1")
        return num_usable

    def num_bad_blocks(self) -> int:
        """Bad Block数を返す"""
        num_bad = 0
        for chip_index in range(self.num_chip):
            num_bad += bin(self.badblock_bitmaps[chip_index]).count("1")
        return num_bad

    def num_allocated_blocks(self) -> int:
        """確保済みのNAND Block数を返す"""
        num_allocated = 0
        for chip_index in range(self.num_chip):
            num_allocated += bin(self.allocated_bitmaps[chip_index]).count("1")
        return num_allocated

    def num_total_capacity(self) -> int:
        """総容量を返す (バイト単位)"""
        return self.num_chip * NandConfig.BLOCKS_PER_CS * NandConfig.BLOCK_USABLE_BYTES

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
            chip, block = self._pick_free()
            if block is None or chip is None:
                raise ValueError("No Free Block")
            else:
                # Erase OKのものを採用。だめならやり直し
                is_erase_ok = await self._nandcmd.erase_block(
                    chip_index=chip, block=block
                )
                if is_erase_ok:
                    self._mark_alloc(chip_index=chip, block=block)
                    return chip, block
                else:
                    # Erase失敗、BadBlockとしてマークし、Freeせず次のBlockを探す
                    self._mark_bad(chip_index=chip, block=block)

    async def free(self, chip_index: CHIP, block: BLOCK) -> None:
        """Blockを解放"""
        self._mark_free(chip_index=chip_index, block=block)

    async def read(
        self,
        chip_index: CHIP,
        block: BLOCK,
        page: PAGE,
        num_bytes: int = NandConfig.PAGE_USABLE_BYTES,
        col: int = 0,
    ) -> bytearray | None:
        """指定されたページを読み出す"""
        print(f"Read: Chip {chip_index}, Block {block}, Page {page}")

        return await self._nandcmd.read_page(
            chip_index=chip_index, block=block, page=page, num_bytes=num_bytes, col=col
        )

    async def program(
        self, chip_index: CHIP, block: BLOCK, page: PAGE, data: bytearray
    ) -> bool:
        """指定されたページにデータを書き込む"""
        print(
            f"Program: Chip {chip_index}, Block {block}, Page {page}, Data Length: {len(data)}"
        )
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


class Mapping:
    # (2048byte * 64page) / 512byte = 256 [LBA/LBG]
    LBA_PER_LBG = (
        NandConfig.PAGE_USABLE_BYTES * NandConfig.PAGES_PER_BLOCK
    ) // NandConfig.SECTOR_BYTES

    @staticmethod
    def lba_to_lbg(lba: LBA) -> tuple[LBG, LBA]:
        return lba // Mapping.LBA_PER_LBG, lba % Mapping.LBA_PER_LBG

    @staticmethod
    def lbg_to_lba(lbg: LBG, offset_lba: LBA = 0) -> LBA:
        return lbg * Mapping.LBA_PER_LBG + offset_lba

    def __init__(self) -> None:
        # LBG -> (CHIP, BLOCK) mapping. LBA % LBGで内部オフセットが求まる
        self._mapping: dict[LBG, tuple[CHIP, BLOCK]] = {}

    async def init_config(self) -> None:
        self._mapping.clear()

    def save_config(self, config: FtlConfig) -> bool:
        config.set("mapping", self._mapping, save=False)
        return True

    def load_config(self, config: FtlConfig) -> bool:
        self._mapping = config.get("mapping", {})
        return True

    def update(self, lbg: LBG, chip: CHIP, block: BLOCK) -> None:
        self._mapping[lbg] = (chip, block)

    def resolve(self, lbg: LBG) -> tuple[CHIP | None, BLOCK | None]:
        return self._mapping.get(lbg, (None, None))


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
        over_provision_ratio: float = 0.1,
    ) -> None:
        #########################################
        # Set by External
        self.nandio = nandio
        self.nandcmd = nandcmd
        self.config = config if config is not None else FtlConfig()
        self.over_provision_ratio = over_provision_ratio

        #########################################
        # Internal Components
        self._blockmng = NandBlockManager(nandcmd=self.nandcmd)
        self._mapping = Mapping()

        #########################################
        # Primitives
        # 現在処理中のLBG
        self._write_lbg: LBG | None = None
        # １NAND Block分のwrite_buffers[page]
        self._write_buffers: list[bytearray] = list()
        for _ in range(NandConfig.PAGES_PER_BLOCK):
            self._write_buffers.append(bytearray(NandConfig.PAGE_USABLE_BYTES))
        # 変更したらTrue
        self._is_write_dirty: bool = False

    async def _store_write_buffer(self) -> None:
        """書き込みバッファをNAND Flashに書き込み、Write Buffersをクリアする"""
        # 不要
        if self._write_lbg is None or not self._is_write_dirty:
            return
        # 途中でエラーが出たケースは最初からやり直せるようにする
        is_ok = False

        while not is_ok:
            # 書き込み先決定
            chip, block = await self._blockmng.alloc()
            # 先頭から全Page書き込み
            for page_index in range(NandConfig.PAGES_PER_BLOCK):
                data = self._write_buffers[page_index]
                prog_ret = await self._blockmng.program(
                    chip_index=chip, block=block, page=page_index, data=data
                )
                # 書き込み失敗、BadBlockとしてマークし、やり直し
                if not prog_ret:
                    await self._blockmng.free(chip_index=chip, block=block)
                    self._blockmng._mark_bad(chip_index=chip, block=block)
                    break  # 残りのPageは書き込まない
            # 全部やりきれたら完了とする
            is_ok = True

        # Update Mapping
        self._mapping.update(self._write_lbg, chip, block)
        # Clear Write Buffers
        self._write_lbg = None
        self._is_write_dirty = False

    async def _load_write_buffer(self, lbg: LBG) -> None:
        """LBGに対応する書き込みバッファをNAND Flashから読み込み、Write Buffersをセットする"""
        # Write先取得
        chip, block = self._mapping.resolve(lbg)

        # まだWriteしたことがない場合、読み出し不要
        if chip is None or block is None:
            return

        # 全Page読み込み
        for page_index in range(NandConfig.PAGES_PER_BLOCK):
            read_page_data = await self._blockmng.read(
                chip_index=chip, block=block, page=page_index
            )
            # Read Error
            if read_page_data is None:
                raise ValueError(
                    f"Read Error: Chip {chip}, Block {block}, Page {page_index} data: {read_page_data}"
                )

            # Copy data to write buffers
            for sector_index in range(NandConfig.SECTOR_PER_PAGE):
                byte_offset = sector_index * NandConfig.SECTOR_BYTES
                src_buf = memoryview(read_page_data)[
                    byte_offset : byte_offset + NandConfig.SECTOR_BYTES
                ]
                dst_buf = memoryview(self._write_buffers[page_index])[
                    byte_offset : byte_offset + NandConfig.SECTOR_BYTES
                ]
                dst_buf[: len(src_buf)] = src_buf
        # LBGをセット
        self._write_lbg = lbg
        self._is_write_dirty = False

    def _sector_offset_to_write_buffer_pos(
        self, sector_offset: LBA
    ) -> tuple[PAGE, SECTOR]:
        """LBAからWrite Bufferの位置を計算"""
        page_in_block = sector_offset // NandConfig.SECTOR_PER_PAGE
        sector_in_page = sector_offset % NandConfig.SECTOR_PER_PAGE
        return page_in_block, sector_in_page

    async def write_logical(self, lba: LBA, src_data: bytearray) -> None:
        """指定されたLBAにデータを書き込む"""
        lbg, sector_in_block = Mapping.lba_to_lbg(lba)
        # LBGが変わった場合、書き込みバッファをフラッシュ
        if self._write_lbg != lbg and self._is_write_dirty:
            await self._store_write_buffer()
        # まだLBGがセットされていない場合、読み込み
        if self._write_lbg is None:
            await self._load_write_buffer(lbg)

        # 転送先決定
        page_in_block, sector_in_page = self._sector_offset_to_write_buffer_pos(lba)
        byte_offset = sector_in_page * NandConfig.SECTOR_BYTES
        print(
            f"Update writebuffer[{page_in_block}][{byte_offset}: {byte_offset + NandConfig.SECTOR_BYTES}] = {src_data[0]: 02x}"
        )
        # 書き込みバッファにデータを転送
        self._write_buffers[page_in_block][
            byte_offset : byte_offset + NandConfig.SECTOR_BYTES
        ] = src_data[: NandConfig.SECTOR_BYTES]
        # 変更したことを覚えておく
        self._write_lbg = lbg
        self._is_write_dirty = True
        print(
            f"Write: LBA {lba}, LBG {lbg}, Page {page_in_block}, Sector {sector_in_page}, Data0: {src_data[0]: 02x}"
        )

    async def flush(self) -> None:
        """書き込みバッファをNAND Flashに書き込む"""
        await self._store_write_buffer()
        # Mappingを保存
        self.save_config()

    async def read_logical(self, lba: LBA) -> bytearray:
        """指定されたLBAのデータを読み出す"""
        # NAND Block内位置を計算
        page_in_block, sector_in_page = self._sector_offset_to_write_buffer_pos(lba)
        # LBGとSectorを計算
        lbg, _ = Mapping.lba_to_lbg(lba)
        # Mapping を確認
        chip, block = self._mapping.resolve(lbg)
        print(
            f"Read: LBA {lba}, LBG {lbg}, Chip {chip}, Block {block}, Page {page_in_block}, Sector {sector_in_page}"
        )

        # 現在のLBG上にある -> 書き込みバッファから読み出し
        if self._write_lbg == lbg:
            # 書き込みバッファから読み出し
            byte_offset = sector_in_page * NandConfig.SECTOR_BYTES
            src_buf = memoryview(self._write_buffers[page_in_block])[
                byte_offset : byte_offset + NandConfig.SECTOR_BYTES
            ]
            print(
                f"refer writebuffer[{page_in_block}][{byte_offset}: {byte_offset + NandConfig.SECTOR_BYTES}] = {src_buf[0]: 02x}"
            )
            return bytearray(src_buf)

        # Mappingがない -> 空データ
        if chip is None or block is None:
            print("No Mapping found, returning empty data")
            return bytearray(NandConfig.SECTOR_BYTES)

        # Mappingがある -> NAND Flashから読み出し
        start_index = sector_in_page * NandConfig.SECTOR_BYTES
        read_sector_data = await self._blockmng.read(
            chip_index=chip,
            block=block,
            page=page_in_block,
            col=start_index,
            num_bytes=NandConfig.SECTOR_BYTES,
        )
        # Read Error
        if read_sector_data is None:
            raise ValueError(
                f"Read Error: Chip {chip}, Block {block}, Page {page_in_block} sector {sector_in_page} data0: {read_sector_data}"
            )
        print(f"Read from NAND: {read_sector_data[0]: 02x}")
        return read_sector_data

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

    def report_capacity_lb(self) -> int:
        """FTLの容量を返す"""
        # 搭載された全部の容量
        total_capacity = self._blockmng.num_total_capacity()
        # max:1024/min:1004blockであることや後のエラーで減ることを想定して設定
        spare_capacity = int(total_capacity * self.over_provision_ratio)
        # total-spareで使える範囲. USB MSC等で公開する容量
        usable_capacity = total_capacity - spare_capacity

        return usable_capacity // NandConfig.SECTOR_BYTES
