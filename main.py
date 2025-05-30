from mpy.nand import NandConfig, NandBlockManager, PageCodec, get_driver, PBA

# Logical Block Address
LBA = int


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

    def __init__(self) -> None:
        # NAND Drivers
        self.nandio, self.nandcmd = get_driver(keep_wp=False)
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

    ########################################################
    # Physical Address Read
    ########################################################

    def read_page(self, chip_index: int, block: int, page: int) -> bytearray | None:
        """指定されたページをすべて読み出し"""
        # データを読み込む
        page_data = self.blockmng.read(chip_index, block, page)
        if page_data is None:
            return None
        # データをデコード
        decode_page_data = self.codec.decode(page_data)
        if decode_page_data is None:
            return None
        return decode_page_data

    def read_sector(
        self, chip_index: int, block: int, page: int, sector: int
    ) -> bytearray | None:
        """指定されたページのセクタを読み出し"""
        # データを読み込む
        page_data = self.read_page(chip_index, block, page)
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

    def write_page(
        self, chip_index: int, block: int, page: int, data: bytearray
    ) -> bool:
        """指定されたページを書き込む"""
        # データをエンコード
        encode_page_data = self.codec.encode(data)
        if encode_page_data is None:
            return False
        # データを書き込む
        result = self.blockmng.program(chip_index, block, page, encode_page_data)
        if not result:
            return False
        return True

    ########################################################
    # Logical Address Functions
    ########################################################

    @staticmethod
    def unmap_sector() -> bytearray:
        return bytearray([0x0] * NandConfig.SECTOR_BYTES)

    def read_logical(self, lba: LBA) -> bytearray:
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
        sector_data = self.read_sector(chip, block, page, sector)
        if sector_data is None:
            return self.unmap_sector()
        return sector_data

    def write_logical(self, lba: LBA, data: bytearray) -> bool:
        """指定されたLBAに書き込む"""
        # 書き込み先Chip/Blockを予約して先頭から使う
        if (
            self.current_write_chip is None
            or self.current_write_block is None
            or self.current_write_page is None
            or self.current_write_sector is None
        ):
            self.current_write_chip, self.current_write_block = self.blockmng.alloc()
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
            write_result = self.write_page(
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
    main()
