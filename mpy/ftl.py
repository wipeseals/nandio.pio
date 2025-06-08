import json
from mpy.driver import NandIo, FwNandCommander, PioNandCommander
from sim.nandio_pio import BLOCK, CHIP, LBA, PAGE, PBA, NandConfig


class NandBlockManager:
    def __init__(
        self,
        nandcmd: FwNandCommander | PioNandCommander,
    ) -> None:
        self._nandcmd = nandcmd

    async def init(
        self,
        is_initial: bool = False,
        num_chip: CHIP = NandConfig.MAX_CS,
        initial_badblock_bitmaps: list[int] | None = None,
    ) -> None:
        if not is_initial:
            try:
                self._load()
            except OSError as _:
                is_initial = True

        if is_initial:
            self.num_chip: CHIP = num_chip
            self.badblock_bitmaps = (
                initial_badblock_bitmaps if initial_badblock_bitmaps else []
            )
            await self._setup()
            # save initialized values
            await self._save()

    async def _save(self, filepath: str = "nand_block_allocator.json") -> None:
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
        except OSError as e:
            raise e

    def _load(self, filepath: str = "nand_block_allocator.json") -> None:
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
    ) -> int | None:
        badblock_bitmap = 0
        for block in range(num_blocks):
            data = await self._nandcmd.read_page(
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
    async def _setup(self) -> None:
        # cs
        if self.num_chip == 0:
            self.num_chip = await self._check_chip_num()
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
                bitmaps = await self._check_allbadblocks(chip_index=chip_index)
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

    async def alloc(self) -> tuple[CHIP, BLOCK]:
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
        self._mark_free(chip_index=chip_index, block=block)

    async def read(
        self, chip_index: CHIP, block: BLOCK, page: PAGE
    ) -> bytearray | None:
        return await self._nandcmd.read_page(
            chip_index=chip_index, block=block, page=page
        )

    async def program(
        self, chip_index: CHIP, block: BLOCK, page: PAGE, data: bytearray
    ) -> bool:
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
    """LBAとPBAのマッピングを管理するクラス"""

    def __init__(self) -> None:
        self.l2p: dict[LBA, PBA] = dict()

    def resolve(self, lba: LBA) -> PBA | None:
        """LBA -> PBAの変換"""
        pba = self.l2p.get(lba)
        return pba

    def update(self, lba: LBA, pba: PBA) -> None:
        """LBA -> PBAの割当更新"""
        self.l2p[lba] = pba

    def unmap(self, lba: LBA) -> None:
        """LBAのマッピング削除"""
        self.l2p.pop(lba, None)


class FlashTranslationLayer:
    """Flash Translation Layer (FTL)"""

    def __init__(
        self, nandio: NandIo, nandcmd: FwNandCommander | PioNandCommander
    ) -> None:
        # NAND IO Drivers
        self.nandio = nandio
        # NAND Commander
        self.nandcmd = nandcmd
        # NAND Block Manager
        self.blockmng = NandBlockManager(nandcmd=self.nandcmd)
        # NAND Page Codec
        self.codec = PageCodec()
        # LBA -> PBAのマッピング
        self.mapping = Mapping()

        # Write Buffer (WriteはEncode都合でpage単位で行うため、複数sector束ねる用)
        self.write_buffer: bytearray = bytearray([0x0] * NandConfig.PAGE_USABLE_BYTES)
        # write buffer 上にあるLBA (有効なsector数を求める目的と、Write Buffer城のデータを返却するケースで使用)
        self.write_buffer_lbas: list[LBA] = list()
        # 現在の書き込み進捗
        self.current_write_chip: int | None = None
        self.current_write_block: int | None = None
        self.current_write_page: int | None = None
        self.current_write_sector: int | None = None

    async def init(
        self,
        is_initial: bool,
    ) -> None:
        await self.blockmng.init(is_initial=is_initial)

    ########################################################
    # Physical Address Read
    ########################################################

    async def read_page(
        self, chip_index: int, block: int, page: int
    ) -> bytearray | None:
        """指定されたページをすべて読み出し"""
        # データを読み込む
        page_data = await self.blockmng.read(chip_index, block, page)
        if page_data is None:
            return None
        # データをデコード
        decode_page_data = self.codec.decode(page_data)
        if decode_page_data is None:
            return None
        return decode_page_data

    async def read_sector(
        self, chip_index: int, block: int, page: int, sector: int
    ) -> bytearray | None:
        """指定されたページのセクタを読み出し"""
        # データを読み込む
        page_data = await self.read_page(chip_index, block, page)
        if page_data is None:
            return None
        # ほしいSectorを取得
        sector_data = page_data[
            sector * NandConfig.SECTOR_BYTES : (sector + 1) * NandConfig.SECTOR_BYTES
        ]
        return sector_data

    ########################################################
    # Physical Address Write
    ########################################################

    async def write_page(
        self, chip_index: int, block: int, page: int, data: bytearray
    ) -> bool:
        """指定されたページを書き込む"""
        # データをエンコード
        encode_page_data = self.codec.encode(data)
        if encode_page_data is None:
            return False
        # データを書き込む
        result = await self.blockmng.program(chip_index, block, page, encode_page_data)
        if not result:
            return False
        return True

    ########################################################
    # Logical Address Functions
    ########################################################

    @staticmethod
    def unmap_sector() -> bytearray:
        return bytearray([0x0] * NandConfig.SECTOR_BYTES)

    async def read_logical(self, lba: LBA) -> bytearray:
        """指定されたLBAを読み出し"""
        # Write Bufferに書き込み中の場合は、Write Bufferから読み出す
        if lba in self.write_buffer_lbas:
            # Write Buffer上のLBAを取得
            sector_index = self.write_buffer_lbas.index(lba)
            # Write Buffer上のSectorを取得
            sector_data = self.write_buffer[
                sector_index * NandConfig.SECTOR_BYTES : (sector_index + 1)
                * NandConfig.SECTOR_BYTES
            ]
            return sector_data
        # LBA -> PBAの変換
        pba = self.mapping.resolve(lba)
        if pba is None:
            return self.unmap_sector()

        # PBAをCS, Block, Page, Sectorに展開して読み出し
        chip, block, page, sector = NandConfig.decode_phys_addr(pba)
        sector_data = await self.read_sector(chip, block, page, sector)
        if sector_data is None:
            return self.unmap_sector()
        return sector_data

    async def write_logical(self, lba: LBA, data: bytearray) -> bool:
        """指定されたLBAに書き込む"""
        # 書き込み先Chip/Blockを予約して先頭から使う
        if (
            self.current_write_chip is None
            or self.current_write_block is None
            or self.current_write_page is None
            or self.current_write_sector is None
        ):
            (
                self.current_write_chip,
                self.current_write_block,
            ) = await self.blockmng.alloc()
            self.current_write_page = 0
            self.current_write_sector = 0
            self.write_buffer_lbas = list()  # 書き込み先LBAを初期化
        # PBA決定 + Mapping更新
        pba = NandConfig.encode_phys_addr(
            self.current_write_chip,
            self.current_write_block,
            self.current_write_page,
            self.current_write_sector,
        )
        self.mapping.update(lba, pba)
        # Write Bufferに書き込み
        self.write_buffer[
            self.current_write_sector * NandConfig.SECTOR_BYTES : (
                self.current_write_sector + 1
            )
            * NandConfig.SECTOR_BYTES
        ] = data
        # Write Buffer上のLBA情報を更新
        self.write_buffer_lbas.append(lba)

        # Write Bufferがいっぱいになったら書き込み
        if len(self.write_buffer_lbas) < NandConfig.SECTOR_PER_PAGE:
            # 次のセクタへ移動
            self.current_write_sector += 1
            return True
        else:
            # 書き込み
            write_result = await self.write_page(
                self.current_write_chip,
                self.current_write_block,
                self.current_write_page,
                self.write_buffer,
            )
            # 書き込み先LBAを初期化
            self.write_buffer_lbas = list()
            # 次のページへ移動
            self.current_write_sector = 0
            self.current_write_page += 1
            # Block内のページを使い切ったら書き込み先を初期化
            if self.current_write_page >= NandConfig.PAGES_PER_BLOCK:
                self.current_write_chip = None
                self.current_write_block = None
                self.current_write_page = None
                self.current_write_sector = None
            # 書き込み結果を返却
            return write_result
