from typing import List, Optional, Union
import array


class NandCommandId:
    """NAND Flash Command"""

    SerialDataInput = 0x80
    Read1stCycle = 0x00
    Read2ndCycle = 0x30
    ReadWithDataCache = 0x31
    ReadStartForLastPageInReadCycleWithDataCache = 0x3F
    AutoPageProgram1stCycle = 0x80
    AutoPageProgram2ndCycle = 0x10
    ColumnAddressChangeInSerialDataInput = 0x85
    AutoPageProgramWithDataCache1stCycle = 0x80
    AutoPageProgramWithDataCache2ndCycle = 0x15
    ReadForPageCopyWithDataOut1stCycle = 0x00
    ReadForPageCopyWithDataOut2ndCycle = 0x3A
    AutoProgramWithDataCacheDuringPageCopy1stCycle = 0x8C
    AutoProgramWithDataCacheDuringPageCopy2ndCycle = 0x15
    AutoProgramForLastPageDuringPageCopy1stCycle = 0x8C
    AutoProgramForLastPageDuringPageCopy2ndCycle = 0x10
    AutoBlockErase1stCycle = 0x60
    AutoBlockErase2ndCycle = 0xD0
    ReadId = 0x90
    StatusRead = 0x70
    Reset = 0xFF


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
    def gen_ceb_bits(cls, cs: Optional[int] = None) -> int:
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
    def bitor_cs(
        cls, data_src: int | array.array, cs: Optional[int]
    ) -> int | array.array:
        """data_srcに対して、csを指定してCEB0/CEB1をセットする。単一変数・arrayどちらでも対応。arrayの場合は内容を変更する。"""
        if isinstance(data_src, int):
            return cls.gen_ceb_bits(cs) | data_src
        elif isinstance(data_src, array.array):
            for i in range(len(data_src)):
                data_src[i] = cls.gen_ceb_bits(cs) | data_src[i]
            return data_src
        else:
            raise TypeError("data_src must be int, list, or array.array type")


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
        arr: array.array, column_addr: int, page_addr: int, block_addr: int
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
        arr[0] = ca & 0xFF
        arr[1] = (ca >> 8) & 0x0F
        arr[2] = pa & 0xFF
        arr[3] = (pa >> 8) & 0xFF

    @staticmethod
    def create_block_addr(arr: array.array, block_addr: int) -> None:
        """Block Addressを2byteのAddressInput用に変換する。Auto Block Erase用。"""

        arr[0] = block_addr & 0xFF
        arr[1] = (block_addr >> 8) & 0xFF


class PioCmdId:
    """Broccoli NAND IO Command"""

    Bitbang = 0x00
    CmdLatch = 0x01
    AddrLatch = 0x02
    DataOutput = 0x03
    DataInput = 0x04
    SetIrq = 0x05
    WaitRbb = 0x06


class PioCmdBuilder:
    """PIO Command Build helper"""

    @staticmethod
    def create_cmd_header(
        cmd_id: PioCmdId,
        pindir: int,
        transfer_count: int,
        cmd1: Optional[int],
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
            cmd1=Util.bitor_cs(0x00, None),
            arr=arr,
        )

    @classmethod
    def assert_cs(
        cls,
        arr: array.array,
        cs: Optional[int] = None,
    ) -> None:
        """Set CEB0/CEB1 pin state."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.Bitbang,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=Util.bitor_cs(0x00, cs),
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
        cmd: NandCommandId,
        cs: int,
    ) -> None:
        """Latch command to NAND Flash."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.CmdLatch,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=Util.bitor_cs(cmd, cs),
            arr=arr,
        )

    @classmethod
    def addr_latch(
        cls,
        arr: array.array,
        addrs: array.array,
        cs: int,
    ) -> None:
        """Latch address to NAND Flash."""
        Util.bitor_cs(addrs, cs)  # Ensure addresses are modified with CS
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
        data: array.array ,
        cs: int,
    ) -> None:
        """Input data to NAND Flash."""
        Util.bitor_cs(data, cs)  # Ensure data is modified with CS
        cls.data_input_only_header(arr, len(data))
        arr.extend(data)

    @classmethod
    def set_irq(cls, arr: array.array) -> None:
        """Set IRQ."""
        cls.create_cmd_header(
            cmd_id=PioCmdId.SetIrq,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,
            cmd1=None,
            arr=arr,
        )

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
        cs: Optional[int] = None,
    ) -> None:
        """Latch full address to NAND Flash."""
        addrs = array.array('I', [0, 0, 0, 0])  # 4-byte address
        NandAddr.create_full_addr(addrs, column_addr, page_addr, block_addr)
        cls.addr_latch(arr, addrs, cs)

    @classmethod
    def block_addr_latch(
        cls,
        arr: array.array,
        block_addr: int,
        cs: Optional[int] = None,
    ) -> None:
        """Latch block address to NAND Flash."""
        addrs = array.array('I', [0, 0])  # 2-byte address
        NandAddr.create_block_addr(addrs, block_addr)
        cls.addr_latch(arr, addrs, cs)

    @classmethod
    def seq_reset(cls, arr: array.array, cs: int) -> None:
        """Reset sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.Reset, cs=cs)
        cls.wait_rbb(arr)
        cls.deassert_cs(arr)
        cls.set_irq(arr)

    @classmethod
    def seq_read_id(cls, arr: array.array, cs: int, offset: int = 0, data_count: int = 5,) -> None:
        """Read ID sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.ReadId, cs=cs)
        addrs = array.array('I', [offset])  # 1-byte address
        cls.addr_latch(arr, addrs=addrs, cs=cs)
        cls.data_output(arr, data_count=data_count)
        cls.deassert_cs(arr)
        cls.set_irq(arr)

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
        cls.cmd_latch(arr, cmd=NandCommandId.Read1stCycle, cs=cs)
        cls.full_addr_latch(arr, column_addr, page_addr, block_addr, cs)
        cls.cmd_latch(arr, cmd=NandCommandId.Read2ndCycle, cs=cs)
        cls.wait_rbb(arr)
        cls.data_output(arr, data_count=data_count)
        cls.deassert_cs(arr)
        cls.set_irq(arr)

    @classmethod
    def seq_status_read(
        cls,
        arr: array.array,
        cs: int,
    ) -> None:
        """Read status sequence for NAND Flash."""
        cls.init_pin(arr)
        cls.assert_cs(arr, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.StatusRead, cs=cs)
        cls.data_output(arr, data_count=1)
        cls.deassert_cs(arr)
        cls.set_irq(arr)

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
        cls.cmd_latch(arr, cmd=NandCommandId.AutoPageProgram1stCycle, cs=cs)
        cls.full_addr_latch(arr, column_addr, page_addr, block_addr, cs)
        cls.data_input(arr, data=data, cs=cs)
        cls.cmd_latch(arr, cmd=NandCommandId.AutoPageProgram2ndCycle, cs=cs)
        cls.wait_rbb(arr)
        cls.cmd_latch(arr, cmd=NandCommandId.StatusRead, cs=cs)
        cls.data_output(arr, data_count=1)
        cls.deassert_cs(arr)
        cls.set_irq(arr)

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
        cls.cmd_latch(arr, cmd=NandCommandId.AutoBlockErase1stCycle, cs=cs)
        cls.block_addr_latch(arr, block_addr, cs)
        cls.cmd_latch(arr, cmd=NandCommandId.AutoBlockErase2ndCycle, cs=cs)
        cls.wait_rbb(arr)
        cls.cmd_latch(arr, cmd=NandCommandId.StatusRead, cs=cs)
        cls.data_output(arr, data_count=1)
        cls.deassert_cs(arr)
        cls.set_irq(arr)
