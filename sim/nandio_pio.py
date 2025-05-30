import array
import math

# Logical Block Address
LBA = int
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
# block mark bitmap type (1bit per block)
BLOCK_BITMAP = int


class NandConfig:
    """
    NAND Flash Configuration for JISC-SSD TC58NVG0S3HTA00
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
    # block bytes
    BLOCK_BYTES = PAGE_ALL_BYTES * PAGES_PER_BLOCK
    # block usable bytes
    BLOCK_USABLE_BYTES = PAGE_USABLE_BYTES * PAGES_PER_BLOCK
    # sector size
    SECTOR_BYTES = 512
    # number of sectors per page (2048byte / 512byte = 4)
    SECTOR_PER_PAGE = PAGE_USABLE_BYTES // SECTOR_BYTES


class NandCommandId:
    """NAND Flash Command"""

    READ_1ST = 0x00
    READ_2ND = 0x30
    PROGRAM_1ST = 0x80
    PROGRAM_2ND = 0x10
    ERASE_1ST = 0x60
    ERASE_2ND = 0xD0
    READ_ID = 0x90
    STATUS_READ = 0x70
    RESET = 0xFF


class NandStatus:
    PROGRAM_ERASE_FAIL = 0x01
    CACHE_PROGRAM_FAIL = 0x02
    PAGE_BUFFER_READY = 0x20
    DATA_CACHE_READY = 0x40
    WRITE_PROTECT_DISABLE = 0x80


class PinAssign:
    """
    NAND IC Pinout
    | 15  | 14  | 13  | 12  | 11  | 10  | 9    | 8    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
    | --- | --- | --- | --- | --- | --- | ---- | ---- | --- | --- | --- | --- | --- | --- | --- | --- |
    | rbb | reb | web | wpb | ale | cle | ceb1 | ceb0 | io7 | io6 | io5 | io4 | io3 | io2 | io1 | io0 |
    | in  | out | out | out | out | out | out  | out  | io  | io  | io  | io  | io  | io  | io  | io  |
    """

    IO0 = 0
    IO1 = 1
    IO2 = 2
    IO3 = 3
    IO4 = 4
    IO5 = 5
    IO6 = 6
    IO7 = 7
    CEB0 = 8
    CEB1 = 9
    CLE = 10
    ALE = 11
    WPB = 12
    WEB = 13
    REB = 14
    RBB = 15


class Util:
    @staticmethod
    def bit_on(bit_pos: int) -> int:
        """指定したbitだけ1の値"""
        return 0x01 << bit_pos

    @staticmethod
    def combine_halfword(low: int, high: int) -> int:
        """2byteの値を結合する"""
        return (high << 16) | low

    @classmethod
    def gen_ceb_bits(cls, cs: int | None = None) -> int:
        """cs指定からCEB0/CEB1のピン状態を返す"""
        if cs is None:
            return cls.bit_on(PinAssign.CEB0) | cls.bit_on(PinAssign.CEB1)
        elif cs == 0:
            return cls.bit_on(PinAssign.CEB1)
        elif cs == 1:
            return cls.bit_on(PinAssign.CEB0)
        else:
            raise ValueError("cs must be 0 or 1 or None")

    @classmethod
    def apply_cs(cls, data_src: int, cs: int | None) -> int:
        """data_srcに対して、csを指定してCEB0/CEB1をセットする。単一変数・arrayどちらでも対応。arrayの場合は内容を変更する。"""
        return cls.gen_ceb_bits(cs) | data_src

    @classmethod
    def apply_cs_to_data_array(cls, data_src: array.array, cs: int | None) -> None:
        """data_srcに対して、csを指定してCEB0/CEB1をセットする。arrayの場合は内容を変更する。"""
        for i in range(len(data_src)):
            data_src[i] = cls.gen_ceb_bits(cs) | data_src[i]

    @staticmethod
    def roundup4(value: int) -> int:
        """4の倍数に切り上げる"""
        return (value + 3) & ~0x03


# RBB以外全部Outputに設定するpindir値
PIN_DIR_WRITE: int = (
    Util.bit_on(PinAssign.REB)
    | Util.bit_on(PinAssign.WEB)
    | Util.bit_on(PinAssign.WPB)
    | Util.bit_on(PinAssign.ALE)
    | Util.bit_on(PinAssign.CLE)
    | Util.bit_on(PinAssign.CEB1)
    | Util.bit_on(PinAssign.CEB0)
    | Util.bit_on(PinAssign.IO7)
    | Util.bit_on(PinAssign.IO6)
    | Util.bit_on(PinAssign.IO5)
    | Util.bit_on(PinAssign.IO4)
    | Util.bit_on(PinAssign.IO3)
    | Util.bit_on(PinAssign.IO2)
    | Util.bit_on(PinAssign.IO1)
    | Util.bit_on(PinAssign.IO0)
)

# RBB,IO以外Outputに設定するpindir値
PIN_DIR_READ: int = (
    Util.bit_on(PinAssign.REB)
    | Util.bit_on(PinAssign.WEB)
    | Util.bit_on(PinAssign.WPB)
    | Util.bit_on(PinAssign.ALE)
    | Util.bit_on(PinAssign.CLE)
    | Util.bit_on(PinAssign.CEB1)
    | Util.bit_on(PinAssign.CEB0)
)


class NandAddr:
    @staticmethod
    def create_full_addr(
        arr: array.array,
        column_addr: COLUMN,
        page_addr: PAGE,
        block_addr: BLOCK,
    ) -> None:
        """アドレスをNAND Flashの指定フォーマットに変換する。Schematic Cell Layout and Address Assignment参照

        |              | I/O7 | I/O6 | I/O5 | I/O4 | I/O3 | I/O2 | I/O1 | I/O0 |
        | -------------|------|------|------|------|------|------|------|------|
        | First  cycle | CA7  | CA6  | CA5  | CA4  | CA3  | CA2  | CA1  | CA0  |
        | Second cycle | L    | L    | L    | L    | CA11 | CA10 | CA9  | CA8  |
        | Third  cycle | PA7  | PA6  | PA5  | PA4  | PA3  | PA2  | PA1  | PA0  |
        | Fourth cycle | PA15 | PA14 | PA13 | PA12 | PA11 | PA10 | PA9  | PA8  |

        - CA0 to CA11: Column address
        - PA0 to PA5: Page address in block
        - PA6 to PA15: Block address
        """
        ca = column_addr & 0xFFF
        pa = (page_addr & 0x3F) | ((block_addr & 0x3FF) << 6)
        arr.append(ca & 0xFF)
        arr.append((ca >> 8) & 0x0F)
        arr.append(pa & 0xFF)
        arr.append((pa >> 8) & 0xFF)

    @staticmethod
    def create_block_addr(arr: array.array, block_addr: BLOCK) -> None:
        """Block Addressを2byteのAddressInput用に変換する。Auto Block Erase用。"""
        arr.append(block_addr & 0xFF)
        arr.append((block_addr >> 8) & 0xFF)


class PioCmdId:
    """Broccoli NAND IO Command"""

    Bitbang = 0x00
    CmdLatch = 0x01
    AddrLatch = 0x02
    DataOutput = 0x03
    DataInput = 0x04
    WaitRbb = 0x05


class PioCmdBuilder:
    """PIO Command Build helper"""

    @staticmethod
    def create_cmd_header(
        cmd_id: int,
        pindir: int,
        transfer_count: int,
        cmd1: int | None,
        arr: array.array,
    ) -> None:
        """コマンドの先頭wordをarrに追加する."""
        arr.append(
            ((cmd_id & 0xF) << 28)
            | ((((transfer_count - 1) & 0x0FFF) << 16) | (pindir & 0xFFFF))
        )
        arr.append(cmd1 if cmd1 is not None else 0x00000000)

    @classmethod
    def init_pin(cls, arr: array.array) -> None:
        """Initialize pin direction and set transfer count."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.Bitbang,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=Util.apply_cs(0x00, None),
            arr=arr,
        )

    @classmethod
    def assert_cs(
        cls,
        arr: array.array,
        cs: int | None = None,
    ) -> None:
        """Set CEB0/CEB1 pin state."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.Bitbang,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=Util.apply_cs(0x00, cs),
            arr=arr,
        )

    @classmethod
    def deassert_cs(cls, arr: array.array) -> None:
        """Deassert CEB0/CEB1 pin state."""
        cls.assert_cs(arr=arr, cs=None)

    @classmethod
    def cmd_latch(
        cls,
        arr: array.array,
        cmd: int,
        cs: int | None,
    ) -> None:
        """Latch command to NAND Flash."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.CmdLatch,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=Util.apply_cs(cmd, cs),
            arr=arr,
        )

    @classmethod
    def addr_latch(
        cls,
        arr: array.array,
        addrs: array.array,
        cs: int | None,
    ) -> None:
        """Latch address to NAND Flash."""
        Util.apply_cs_to_data_array(addrs, cs)  # Ensure addresses are modified with CS
        cls.create_cmd_header(
            cmd_id=PioCmdId.AddrLatch,
            pindir=PIN_DIR_WRITE,
            transfer_count=len(addrs),
            cmd1=None,
            arr=arr,
        )
        arr.extend(addrs)

    @classmethod
    def data_output(cls, arr: array.array, data_count: int) -> None:
        """Output data from NAND Flash."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.DataOutput,
            pindir=PIN_DIR_READ,
            transfer_count=data_count,
            cmd1=None,
            arr=arr,
        )

    @classmethod
    def data_input_only_header(cls, arr: array.array, data_count: int) -> None:
        """Input data header to NAND Flash."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.DataInput,
            pindir=PIN_DIR_WRITE,
            transfer_count=data_count,
            cmd1=None,
            arr=arr,
        )

    @classmethod
    def data_input(
        cls,
        arr: array.array,
        data: array.array,
        cs: int,
    ) -> None:
        """Input data to NAND Flash."""
        Util.apply_cs_to_data_array(data, cs)  # Ensure data is modified with CS
        cls.data_input_only_header(arr, len(data))
        arr.extend(data)

    @classmethod
    def wait_rbb(cls, arr: array.array) -> None:
        """Wait for RBB pin to be low."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.WaitRbb,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=None,
            arr=arr,
        )

    @classmethod
    def full_addr_latch(
        cls,
        arr: array.array,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        cs: int | None = None,
    ) -> None:
        """Latch full address to NAND Flash."""
        addrs = array.array("I")
        NandAddr.create_full_addr(addrs, column_addr, page_addr, block_addr)
        cls.addr_latch(arr, addrs, cs)

    @classmethod
    def block_addr_latch(
        cls,
        arr: array.array,
        block_addr: int,
        cs: int | None = None,
    ) -> None:
        """Latch block address to NAND Flash."""
        addrs = array.array("I")
        NandAddr.create_block_addr(addrs, block_addr)
        cls.addr_latch(arr, addrs, cs)

    @classmethod
    def seq_reset(cls, arr: array.array, cs: int) -> None:
        """Reset sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.RESET, cs=cs)
        cls.wait_rbb(arr)
        cls.deassert_cs(arr)

    @classmethod
    def seq_read_id(
        cls,
        arr: array.array,
        cs: int,
        offset: int = 0,
        data_count: int = 5,
    ) -> None:
        """Read ID sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.READ_ID, cs=cs)
        addrs = array.array("I")
        addrs.append(offset)  # 1-byte address
        cls.addr_latch(arr, addrs=addrs, cs=cs)
        cls.data_output(arr, data_count=data_count)
        cls.deassert_cs(arr)

    @classmethod
    def seq_read(
        cls,
        arr: array.array,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        data_count: int,
    ) -> None:
        """Read sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.READ_1ST, cs=cs)
        cls.full_addr_latch(arr, column_addr, page_addr, block_addr, cs)
        cls.cmd_latch(arr, cmd=NandCommandId.READ_2ND, cs=cs)
        cls.wait_rbb(arr)
        cls.data_output(arr, data_count=data_count)
        cls.deassert_cs(arr)

    @classmethod
    def seq_status_read(
        cls,
        arr: array.array,
        cs: int,
    ) -> None:
        """Read status sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.STATUS_READ, cs=cs)
        cls.data_output(arr, data_count=1)
        cls.deassert_cs(arr)

    @classmethod
    def seq_program(
        cls,
        arr: array.array,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        data: array.array,
    ) -> None:
        """Program sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.PROGRAM_1ST, cs=cs)
        cls.full_addr_latch(arr, column_addr, page_addr, block_addr, cs)
        cls.data_input(arr, data=data, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.PROGRAM_2ND, cs=cs)
        cls.wait_rbb(arr)
        cls.cmd_latch(arr, cmd=NandCommandId.STATUS_READ, cs=cs)
        cls.data_output(arr, data_count=1)
        cls.deassert_cs(arr)

    @classmethod
    def seq_erase(
        cls,
        arr: array.array,
        cs: int,
        block_addr: int,
    ) -> None:
        """Erase sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.ERASE_1ST, cs=cs)
        cls.block_addr_latch(arr, block_addr, cs)
        cls.cmd_latch(arr, cmd=NandCommandId.ERASE_2ND, cs=cs)
        cls.wait_rbb(arr)
        cls.cmd_latch(arr, cmd=NandCommandId.STATUS_READ, cs=cs)
        cls.data_output(arr, data_count=1)
        cls.deassert_cs(arr)
