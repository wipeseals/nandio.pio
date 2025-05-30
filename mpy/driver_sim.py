import os
from nand import NandConfig


class NandIo:
    def __init__(self, keep_wp: bool = True) -> None:
        # VCD traceしたくなった場合は実装
        pass


class NandCommander:
    def __init__(
        self,
        nandio: NandIo,
        num_chip: int = 1,
        base_dir: str | None = "nand_datas",
        ram_cache: bool = False,
    ) -> None:
        self._nandio = nandio
        self._num_chip = num_chip
        self._base_dir = base_dir
        self._ram_cache = ram_cache
        # chip -> block -> page -> data
        self._ram_cache_data: dict[int, dict[int, dict[int, bytearray]]] = dict()

        if base_dir is not None:
            # os.pathが無いのでとりあえず試す
            try:
                os.mkdir(base_dir)
            except OSError:
                pass
            # stat取れないケースは失敗
            os.stat(base_dir)

    def _data_path(self, chip_index: int, block: int, page: int) -> str:
        # check range
        if chip_index >= self._num_chip:
            raise ValueError(
                f"Invalid CS Index: {chip_index} (support={self._num_chip})"
            )
        if block >= NandConfig.BLOCKS_PER_CS:
            raise ValueError(f"Invalid Block: {block} (max={NandConfig.BLOCKS_PER_CS})")
        if page >= NandConfig.PAGES_PER_BLOCK:
            raise ValueError(f"Invalid Page: {page} (max={NandConfig.PAGES_PER_BLOCK})")

        return (
            f"{self._base_dir}/cs{chip_index:02d}_block{block:04d}_page{page:02d}.bin"
        )

    def _update_ram_cache(
        self, chip_index: int, block: int, page: int, data: bytearray
    ) -> None:
        if chip_index not in self._ram_cache_data:
            self._ram_cache_data[chip_index] = dict()
        if block not in self._ram_cache_data[chip_index]:
            self._ram_cache_data[chip_index][block] = dict()
        self._ram_cache_data[chip_index][block][page] = data

    def _read_data(self, chip_index: int, block: int, page: int) -> bytearray | None:
        # read cache
        if self._ram_cache and chip_index in self._ram_cache_data:
            if block in self._ram_cache_data[chip_index]:
                if page in self._ram_cache_data[chip_index][block]:
                    return self._ram_cache_data[chip_index][block][page]

        if self._base_dir is None:
            dst = bytearray([0xFF] * NandConfig.PAGE_ALL_BYTES)
            # cache to ram
            if self._ram_cache:
                self._update_ram_cache(chip_index, block, page, dst)
            return dst
        else:
            # from file
            path = self._data_path(chip_index=chip_index, block=block, page=page)
            with open(path, "rb") as f:
                dst = bytearray(f.read())
                # cache to ram
                if self._ram_cache:
                    self._update_ram_cache(chip_index, block, page, dst)
                return dst


    def _write_data(
        self, chip_index: int, block: int, page: int, data: bytearray
    ) -> None:
        # cache to ram
        if self._ram_cache:
            self._update_ram_cache(chip_index, block, page, data)

        if self._base_dir is None:
            # do nothing
            return
        else:
            # to file
            path = self._data_path(chip_index=chip_index, block=block, page=page)
            with open(path, "wb") as f:
                f.write(data)

    ########################################################
    # Communication functions
    ########################################################
    def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        if chip_index < self._num_chip:
            return NandConfig.READ_ID_EXPECT
        else:
            return bytearray([0x00] * num_bytes)

    def read_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        col: int = 0,
        num_bytes: int = NandConfig.PAGE_ALL_BYTES,
    ) -> bytearray | None:
        data = self._read_data(chip_index=chip_index, block=block, page=page)
        return data

    def read_status(self, chip_index: int) -> int:
        return 0x00

    def erase_block(self, chip_index: int, block: int) -> bool:
        self._write_data(
            chip_index=chip_index,
            block=block,
            page=0,
            data=bytearray([0xFF] * NandConfig.PAGE_ALL_BYTES),
        )
        return True

    def program_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        data: bytearray,
        col: int = 0,
    ) -> bool:
        self._write_data(chip_index=chip_index, block=block, page=page, data=data)
        return True
