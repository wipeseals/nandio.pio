from typing import List, Optional, Union


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
        cls, data_src: Union[int, List[int]], cs: Optional[int]
    ) -> Union[int, List[int]]:
        """data_srcに対して、csを指定してCEB0/CEB1をセットする。単一変数・リストどちらでも対応"""
        if isinstance(data_src, int):
            return cls.gen_ceb_bits(cs) | data_src
        else:
            return [cls.gen_ceb_bits(cs) | data for data in data_src]


# RBB以外全部Outputに設定するpindir値
PIN_DIR_WRITE: int = (
    Util.bit_on(PinAssign.REB)
    | Util.bit_on(PinAssign.WEB)
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
        column_addr: int, page_addr: int, block_addr: int
    ) -> List[int]:
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
        return [
            ca & 0xFF,
            (ca >> 8) & 0x0F,
            pa & 0xFF,
            (pa >> 8) & 0xFF,
        ]

    @staticmethod
    def create_block_addr(block_addr: int) -> List[int]:
        """Block Addressを2byteのAddressInput用に変換する。Auto Block Erase用。"""
        return [
            block_addr & 0xFF,
            (block_addr >> 8) & 0xFF,
        ]


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
    ) -> List[int]:
        """コマンドの先頭wordを返す. RShiftで取り出す想定. transfer_countに実際にセットされる値は、pio都合で-1される。"""
        return [
            # cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }
            ((cmd_id & 0xF) << 28)
            | ((((transfer_count - 1) & 0x0FFF) << 16) | (pindir & 0xFFFF)),
            # cmd_1 = { arg0[31:0] }
            cmd1 if cmd1 is not None else 0x00000000,
        ]

    @classmethod
    def init_pin(cls) -> List[int]:
        """Initialize pin direction and set transfer count."""
        # cmd_1 = { pins_data[9:0] }
        #         { ceb1,ceb0,io7,io6,io5,io4,io3,io2,io1,io0 }
        return cls.create_cmd_header(
            cmd_id=PioCmdId.Bitbang,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,  # don't care
            cmd1=Util.bitor_cs(0x00, None),
        )

    @classmethod
    def assert_cs(
        cls,
        cs: Optional[int] = None,
    ) -> List[int]:
        """Set CEB0/CEB1 pin state."""
        # cmd_1 = { pins_data[9:0] }
        #         { ceb1,ceb0,io7,io6,io5,io4,io3,io2,io1,io0 }
        return cls.create_cmd_header(
            cmd_id=PioCmdId.Bitbang,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,  # don't care
            cmd1=Util.bitor_cs(0x00, cs),
        )

    @classmethod
    def deassert_cs(cls) -> List[int]:
        """Deassert CEB0/CEB1 pin state."""
        # CS選択なし
        return cls.assert_cs(cs=None)

    @classmethod
    def cmd_latch(
        cls,
        cmd: NandCommandId,
        cs: int,
    ) -> List[int]:
        """Latch command to NAND Flash."""
        # cmd_1 = { ceb[1:0], nand_cmd_id[7:0] }
        return cls.create_cmd_header(
            cmd_id=PioCmdId.CmdLatch,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,  # don't care
            cmd1=Util.bitor_cs(cmd, cs),
        )

    @classmethod
    def addr_latch(
        cls,
        addrs: List[int],
        cs: int,
    ) -> List[int]:
        """Latch address to NAND Flash."""
        # cmd_1 = { reserved }
        # data_0, data_1, data_2, ... : { ceb[1:0], addr[7:0] }

        # addr に CS bitをmergeする
        addrs = [Util.bitor_cs(addr, cs) for addr in addrs]

        return [
            *cls.create_cmd_header(
                cmd_id=PioCmdId.AddrLatch,
                pindir=PIN_DIR_WRITE,
                transfer_count=len(addrs),  # number of address bytes
                cmd1=None,  # don't care
            ),
            *addrs,
        ]

    @classmethod
    def data_output(cls, data_count: int) -> List[int]:
        """Output data from NAND Flash."""
        # cmd_1 = { reserved }

        return cls.create_cmd_header(
            cmd_id=PioCmdId.DataOutput,
            pindir=PIN_DIR_READ,
            transfer_count=data_count,
            cmd1=None,  # don't care
        )

    @classmethod
    def data_input_only_header(cls, data_count: int) -> List[int]:
        """Input data header to NAND Flash. (PIOでCS bitorを行う場合向け)"""
        # cmd_1 = { reserved }
        return cls.create_cmd_header(
            cmd_id=PioCmdId.DataInput,
            pindir=PIN_DIR_WRITE,
            transfer_count=data_count,
            cmd1=None,  # don't care
        )

    @classmethod
    def data_input(
        cls,
        datas: List[int],
        cs: int,
    ) -> List[int]:
        """Input data to NAND Flash."""
        # cmd_1 = { reserved }

        # datas に CS bitをmergeする (PIOをもう一つ利用してbitorするなら省略可)
        datas = [Util.bitor_cs(data, cs) for data in datas]
        return [
            *cls.data_input_only_header(len(datas)),
            *datas,
        ]

    @classmethod
    def set_irq(cls) -> List[int]:
        """Set IRQ."""
        # cmd_1 = { reserved }
        return cls.create_cmd_header(
            cmd_id=PioCmdId.SetIrq,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,  # don't care
            cmd1=None,
        )

    @classmethod
    def wait_rbb(cls) -> List[int]:
        """Wait for RBB pin to be low."""
        # cmd_1 = { reserved }
        return cls.create_cmd_header(
            cmd_id=PioCmdId.WaitRbb,
            pindir=PIN_DIR_WRITE,
            transfer_count=1,  # don't care
            cmd1=None,
        )

    @classmethod
    def full_addr_latch(
        cls,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        cs: Optional[int] = None,
    ) -> List[int]:
        """Latch full address to NAND Flash."""
        addrs = NandAddr.create_full_addr(column_addr, page_addr, block_addr)
        return cls.addr_latch(addrs, cs)

    @classmethod
    def block_addr_latch(
        cls,
        block_addr: int,
        cs: Optional[int] = None,
    ) -> List[int]:
        """Latch block address to NAND Flash."""
        addrs = NandAddr.create_block_addr(block_addr)
        return cls.addr_latch(addrs, cs)

    @classmethod
    def seq_reset(cls, cs: int) -> List[int]:
        """Reset sequence for NAND Flash."""
        return [
            *cls.init_pin(),
            *cls.assert_cs(cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.Reset, cs=cs),
            *cls.wait_rbb(),
            *cls.deassert_cs(),
            *cls.set_irq(),
        ]

    @classmethod
    def seq_read_id(cls, cs: int, offset: int = 0, data_count: int = 5) -> List[int]:
        """Read ID sequence for NAND Flash."""
        return [
            *cls.init_pin(),
            *cls.assert_cs(cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.ReadId, cs=cs),
            *cls.addr_latch(addrs=[offset], cs=cs),  # Offset for Read ID
            *cls.data_output(data_count=data_count),
            *cls.deassert_cs(),
            *cls.set_irq(),
        ]

    @classmethod
    def seq_read(
        cls,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        data_count: int,
    ) -> List[int]:
        """Read sequence for NAND Flash."""
        return [
            *cls.init_pin(),
            *cls.assert_cs(cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.Read1stCycle, cs=cs),
            *cls.full_addr_latch(column_addr, page_addr, block_addr, cs),
            *cls.cmd_latch(cmd=NandCommandId.Read2ndCycle, cs=cs),
            *cls.wait_rbb(),
            *cls.data_output(data_count=data_count),
            *cls.deassert_cs(),
            *cls.set_irq(),
        ]

    @classmethod
    def seq_status_read(
        cls,
        cs: int,
    ) -> List[int]:
        """Read status sequence for NAND Flash."""
        return [
            *cls.init_pin(),
            *cls.assert_cs(cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.StatusRead, cs=cs),
            *cls.data_output(data_count=1),  # Status read
            *cls.deassert_cs(),
            *cls.set_irq(),
        ]

    @classmethod
    def seq_program(
        cls,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        data: List[int],
    ) -> List[int]:
        """Program sequence for NAND Flash."""
        return [
            *cls.init_pin(),
            *cls.assert_cs(cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.AutoPageProgram1stCycle, cs=cs),
            *cls.full_addr_latch(column_addr, page_addr, block_addr, cs),
            *cls.data_input(datas=data, cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.AutoPageProgram2ndCycle, cs=cs),
            *cls.wait_rbb(),
            *cls.cmd_latch(cmd=NandCommandId.StatusRead, cs=cs),
            *cls.data_output(data_count=1),  # Status read
            *cls.deassert_cs(),
            *cls.set_irq(),
        ]

    @classmethod
    def seq_erase(
        cls,
        cs: int,
        block_addr: int,
    ) -> List[int]:
        """Erase sequence for NAND Flash."""
        return [
            *cls.init_pin(),
            *cls.assert_cs(cs=cs),
            *cls.cmd_latch(cmd=NandCommandId.AutoBlockErase1stCycle, cs=cs),
            *cls.block_addr_latch(block_addr, cs),
            *cls.cmd_latch(cmd=NandCommandId.AutoBlockErase2ndCycle, cs=cs),
            *cls.wait_rbb(),
            *cls.cmd_latch(cmd=NandCommandId.StatusRead, cs=cs),
            *cls.data_output(data_count=1),  # Status read
            *cls.deassert_cs(),
            *cls.set_irq(),
        ]
