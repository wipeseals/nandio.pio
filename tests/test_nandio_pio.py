from pathlib import Path
import pytest
from typing import List
import array
from sim.nandio_pio import (
    PIN_DIR_READ,
    PIN_DIR_WRITE,
    NandAddr,
    PioCmdBuilder,
    NandCommandId,
    PioCmdId,
    Util,
)
from sim.simulator import Result, Simulator


class TestUtil:
    @pytest.mark.parametrize(
        "bitpos,expect",
        [
            (0, 0x0001),
            (1, 0x0002),
            (2, 0x0004),
            (3, 0x0008),
            (4, 0x0010),
            (5, 0x0020),
            (6, 0x0040),
            (7, 0x0080),
            (8, 0x0100),
            (9, 0x0200),
            (10, 0x0400),
            (11, 0x0800),
            (12, 0x1000),
            (13, 0x2000),
            (14, 0x4000),
            (15, 0x8000),
            (16, 0x00010000),
            (17, 0x00020000),
            (18, 0x00040000),
            (19, 0x00080000),
            (20, 0x00100000),
            (21, 0x00200000),
            (22, 0x00400000),
            (23, 0x00800000),
            (24, 0x01000000),
            (25, 0x02000000),
            (26, 0x04000000),
            (27, 0x08000000),
            (28, 0x10000000),
            (29, 0x20000000),
            (30, 0x40000000),
            (31, 0x80000000),
        ],
    )
    def test_bit_on(self, bitpos: int, expect: int):
        assert Util.bit_on(bitpos) == expect

    @pytest.mark.parametrize(
        "high,low,expect",
        [
            (0x0000, 0x0000, 0x0000_0000),
            (0x0001, 0x0000, 0x0001_0000),
            (0x0000, 0x0001, 0x0000_0001),
            (0x1234, 0x5678, 0x1234_5678),
            (0xFFFF, 0xFFFF, 0xFFFF_FFFF),
            (0x1234, 0xFFFF, 0x1234_FFFF),
            (0xFFFF, 0x5678, 0xFFFF_5678),
        ],
    )
    def test_combine_halfword(self, high: int, low: int, expect: int):
        assert Util.combine_halfword(low, high) == expect

    @pytest.mark.parametrize(
        "cmd,cs,expect",
        [
            (0x00, None, 0x300),
            (0x00, 0, 0x200),
            (0x00, 1, 0x100),
            (0xA5, None, 0x3A5),
            (0xA5, 0, 0x2A5),
            (0xA5, 1, 0x1A5),
            (0xFF, None, 0x3FF),
            (0xFF, 0, 0x2FF),
            (0xFF, 1, 0x1FF),
        ],
    )
    def test_apply_cs(self, cmd: int, cs: int | None, expect: int):
        assert Util.apply_cs(cmd, cs) == expect

    @pytest.mark.parametrize(
        "data_src,cs,expect",
        [
            (array.array("I", [0x00, 0x12]), None, array.array("I", [0x300, 0x312])),
            (array.array("I", [0x00, 0x12]), 0, array.array("I", [0x200, 0x212])),
            (array.array("I", [0x00, 0x12]), 1, array.array("I", [0x100, 0x112])),
            (array.array("I", [0xA5, 0x12]), None, array.array("I", [0x3A5, 0x312])),
            (array.array("I", [0xA5, 0x12]), 0, array.array("I", [0x2A5, 0x212])),
            (array.array("I", [0xA5, 0x12]), 1, array.array("I", [0x1A5, 0x112])),
            (array.array("I", [0xFF, 0x12]), None, array.array("I", [0x3FF, 0x312])),
            (array.array("I", [0xFF, 0x12]), 0, array.array("I", [0x2FF, 0x212])),
            (array.array("I", [0xFF, 0x12]), 1, array.array("I", [0x1FF, 0x112])),
        ],
    )
    def test_apply_cs_to_data_array(
        self, data_src: array.array, cs: int | None, expect: array.array
    ):
        data = array.array("I", data_src)
        Util.apply_cs_to_data_array(data, cs)
        assert data.tolist() == expect.tolist()

    def test_PIN_DIR_WRITE(self):
        assert PIN_DIR_WRITE == 0b01111111_11111111

    def test_PIN_DIR_READ(self):
        assert PIN_DIR_READ == 0b01111111_00000000

    @pytest.mark.parametrize(
        "src,expect",
        [
            (0, 0),
            (1, 4),
            (2, 4),
            (3, 4),
            (4, 4),
            (5, 8),
            (6, 8),
            (7, 8),
            (8, 8),
        ],
    )
    def test_roundup4(self, src: int, expect: int):
        """
        Test for rounding up to the nearest multiple of 4.
        """
        assert Util.roundup4(src) == expect


class TestNandAddr:
    @pytest.mark.parametrize(
        "column_addr,page_addr,block_addr,expect",
        [
            (0, 0, 0, [0x00, 0x00, 0x00, 0x00]),
            (0b10101010, 0, 0, [0b10101010, 0x00, 0x00, 0x00]),
            (0b1101_00000000, 0, 0, [0x00, 0b00001101, 0x00, 0x00]),
            (0, 0b101010, 0, [0x00, 0x00, 0b101010, 0x00]),
            (0, 0, 0b1010101011, [0x00, 0x00, 0b11000000, 0b10101010]),
        ],
    )
    def test_create_full_addr(
        self, column_addr: int, page_addr: int, block_addr: int, expect: List[int]
    ):
        arr = array.array("B")
        NandAddr.create_full_addr(arr, column_addr, page_addr, block_addr)
        assert arr.tolist() == expect

    @pytest.mark.parametrize(
        "block_addr,expect",
        [
            (0, [0x00, 0x00]),
            (0b10101010, [0b10101010, 0x00]),
            (0b10101010_00000000, [0x00, 0b10101010]),
            (0xFFFF, [0xFF, 0xFF]),
        ],
    )
    def test_create_block_addr(self, block_addr: int, expect: List[int]):
        arr = array.array("B")
        NandAddr.create_block_addr(arr, block_addr)
        assert arr.tolist() == expect


class TestPioCmdBuilderBasics:
    @staticmethod
    def cmd0(
        cmd: int,
        dir: int,
        count: int,
    ) -> int:
        """
        Encode the first command word for Test.
        `cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }`
        """
        return (cmd << 28) | ((count - 1) << 16) | dir

    def test_init_pin(self):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.init_pin(pio_prg_arr)

        assert pio_prg_arr[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert pio_prg_arr[0x1] == Util.apply_cs(0x00, None)

    @pytest.mark.parametrize(
        "cs",
        [0, 1, None],
    )
    def test_assert_cs(self, cs: int | None):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.assert_cs(pio_prg_arr, cs)

        assert pio_prg_arr[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert pio_prg_arr[0x1] == Util.apply_cs(0x00, cs)

    def test_deassert_cs(self):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.deassert_cs(pio_prg_arr)

        assert pio_prg_arr[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert pio_prg_arr[0x1] == Util.apply_cs(0x00, None)

    @pytest.mark.parametrize(
        "cs",
        [0, 1, None],
    )
    @pytest.mark.parametrize(
        "cmd",
        [NandCommandId.RESET, NandCommandId.READ_ID],
    )
    def test_cmd_latch(self, cs: int | None, cmd: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.cmd_latch(pio_prg_arr, cmd, cs)

        assert pio_prg_arr[0x0] == self.cmd0(PioCmdId.CmdLatch, PIN_DIR_WRITE, 1)
        assert pio_prg_arr[0x1] == Util.apply_cs(cmd, cs)

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    @pytest.mark.parametrize(
        "addrs",
        [
            array.array("I", [0xAA, 0x99, 0x55, 0x66]),
            array.array("I", [0x11, 0x22]),
        ],
    )
    def test_addr_latch(self, cs: int, addrs: array.array):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.addr_latch(pio_prg_arr, addrs, cs)

        assert pio_prg_arr[0x0] == self.cmd0(
            PioCmdId.AddrLatch, PIN_DIR_WRITE, len(addrs)
        )
        assert pio_prg_arr[0x1] == 0x00  # don't care
        for i, addr in enumerate(addrs):
            # CS が追加されたデータを転送するはず
            assert pio_prg_arr[i + 2] == Util.apply_cs(addr, cs)

    @pytest.mark.parametrize(
        "data_count",
        [1, 5, 2048],
    )
    def test_data_output(self, data_count: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.data_output(pio_prg_arr, data_count)

        assert pio_prg_arr[0x0] == self.cmd0(
            PioCmdId.DataOutput, PIN_DIR_READ, data_count
        )
        assert pio_prg_arr[0x1] == 0x00  # don't care

    @pytest.mark.parametrize(
        "data_count",
        [1, 5, 2048],
    )
    def test_data_input_only_header(self, data_count: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.data_input_only_header(pio_prg_arr, data_count)

        assert pio_prg_arr[0x0] == self.cmd0(
            PioCmdId.DataInput, PIN_DIR_WRITE, data_count
        )
        assert pio_prg_arr[0x1] == 0x00  # don't care

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    @pytest.mark.parametrize(
        "datas",
        [
            array.array("I", [0xAA, 0x99, 0x55, 0x66]),
            array.array("I", [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]),
            array.array("I", list(range(512))),
            array.array("I", list(range(2048))),
        ],
    )
    def test_data_input(self, cs: int, datas: array.array):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.data_input(pio_prg_arr, datas, cs)

        assert pio_prg_arr[0x0] == self.cmd0(
            PioCmdId.DataInput, PIN_DIR_WRITE, len(datas)
        )
        assert pio_prg_arr[0x1] == 0x00  # don't care
        for i, data in enumerate(datas):
            # CS が追加されたデータを転送するはず
            assert pio_prg_arr[i + 2] == Util.apply_cs(data, cs)

    def test_wait_rbb(self):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.wait_rbb(pio_prg_arr)

        assert pio_prg_arr[0x0] == self.cmd0(PioCmdId.WaitRbb, PIN_DIR_WRITE, 1)
        assert pio_prg_arr[0x1] == 0x00


class TestPioCmdBuilderSequences:
    def setup_class(self):
        self.pio_text = Path("nandio.pio").read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    def test_seq_reset(self, cs: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.seq_reset(pio_prg_arr, cs)
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100,
            tx_fifo_entries=pio_prg_arr,
        )

        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.RESET
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    @pytest.mark.parametrize(
        "offset",
        [0, 2],
    )
    @pytest.mark.parametrize(
        "data_count",
        [1, 5],
    )
    def test_seq_read_id(self, cs: int, offset: int, data_count: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.seq_read_id(
            pio_prg_arr, cs, offset=offset, data_count=Util.roundup4(data_count)
        )
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100,
            tx_fifo_entries=pio_prg_arr,
        )

        # READ ID
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.READ_ID
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)
        # Addr In
        assert ret.event_df.iloc[1]["event"] == "addr_in"
        assert ret.event_df.iloc[1]["io_raw"] == offset
        assert ret.event_df.iloc[1]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[1]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[1]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        for i in range(data_count):
            assert ret.event_df.iloc[i + 2]["event"] == "data_out"
            assert (
                ret.event_df.iloc[i + 2]["io_raw"] == ret.received_from_rx_fifo[i]
            )  # created random value from the simulator
            assert ret.event_df.iloc[i + 2]["io_dir_raw"] == 0x00  # read
            assert ret.event_df.iloc[i + 2]["ceb0"] == (0 if cs == 0 else 1)
            assert ret.event_df.iloc[i + 2]["ceb1"] == (0 if cs == 1 else 1)

    @pytest.mark.parametrize(
        "cs,column_addr,page_addr,block_addr,data_count",
        [
            (0, 0, 0, 0, 1),
            (1, 0, 0, 3, 8),
            (0, 1, 0, 0, 5),
            (1, 1024, 0, 128, 10),
            (0, 128, 33, 256, 15),
            (1, 256, 2, 3, 512),
            # too long
            # (0, 0, 0, 0, 2048),
            # (1, 512, 16, 1023, 2048),
        ],
    )
    def test_seq_read(
        self,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        data_count: int,
    ):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.seq_read(
            pio_prg_arr,
            cs,
            column_addr,
            page_addr,
            block_addr,
            data_count,
        )
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100 + data_count * 20,
            tx_fifo_entries=pio_prg_arr,
        )

        # read 1st cycle
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.READ_1ST
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)
        # address input
        # 1st cycle: col[7:0]
        # 2nd cycle  col[11:8]
        # 3rd cycle: page[7:0] (block[1:0], page_in_block[5:0])
        # 4th cycle: page[11:8] (block[9:2])
        expect_addrs = [
            column_addr & 0xFF,  # col[7:0]
            (column_addr >> 8) & 0x0F,  # col[11:8]
            (page_addr & 0xFF) | ((block_addr & 0x03) << 6),  # page[7:0] + block[1:0]
            (block_addr >> 2) & 0xFF,  # block[9:2]
        ]
        for i in range(len(expect_addrs)):
            assert ret.event_df.iloc[i + 1]["event"] == "addr_in"
            assert ret.event_df.iloc[i + 1]["io_raw"] == expect_addrs[i]
            assert ret.event_df.iloc[i + 1]["io_dir_raw"] == 0xFF
            assert ret.event_df.iloc[i + 1]["ceb0"] == (0 if cs == 0 else 1)
            assert ret.event_df.iloc[i + 1]["ceb1"] == (0 if cs == 1 else 1)
        # Read 2nd cycle
        assert ret.event_df.iloc[5]["event"] == "cmd_in"
        assert ret.event_df.iloc[5]["io_raw"] == NandCommandId.READ_2ND
        assert ret.event_df.iloc[5]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[5]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[5]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        for i in range(data_count):
            assert ret.event_df.iloc[i + 6]["event"] == "data_out"
            assert ret.event_df.iloc[i + 6]["io_raw"] == ret.received_from_rx_fifo[i]
            assert ret.event_df.iloc[i + 6]["io_dir_raw"] == 0x00  # read
            assert ret.event_df.iloc[i + 6]["ceb0"] == (0 if cs == 0 else 1)
            assert ret.event_df.iloc[i + 6]["ceb1"] == (0 if cs == 1 else 1)

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    def test_seq_read_status(self, cs: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.seq_status_read(pio_prg_arr, cs)
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=50,
            tx_fifo_entries=pio_prg_arr,
        )

        # Read Status
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.STATUS_READ
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        assert ret.event_df.iloc[1]["event"] == "data_out"
        assert ret.event_df.iloc[1]["io_raw"] == ret.received_from_rx_fifo[0]

    @pytest.mark.parametrize(
        "cs,column_addr,page_addr,block_addr,datas",
        [
            (0, 0, 0, 0, array.array("I", [0xAA, 0x99, 0x55, 0x66])),
            (
                1,
                0,
                0,
                3,
                array.array("I", [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]),
            ),
            (0, 128, 33, 256, array.array("I", list(range(15)))),
            (1, 256, 2, 3, array.array("I", list(range(512)))),
            # too long
            # (0, 512, 16, 1023, array.array("B", list(range(2048)))),
        ],
    )
    def test_seq_program(
        self,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        datas: array.array,
    ):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.seq_program(
            pio_prg_arr, cs, column_addr, page_addr, block_addr, datas
        )
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100 + len(datas) * 10,
            tx_fifo_entries=pio_prg_arr,
        )

        # write 1st cycle
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.PROGRAM_1ST
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)
        # address input
        # 1st cycle: col[7:0]
        # 2nd cycle  col[11:8]
        # 3rd cycle: page[7:0] (block[1:0], page_in_block[5:0])
        # 4th cycle: page[11:8] (block[9:2])
        expect_addrs = [
            column_addr & 0xFF,  # col[7:0]
            (column_addr >> 8) & 0x0F,  # col[11:8]
            (page_addr & 0xFF) | ((block_addr & 0x03) << 6),  # page[7:0] + block[1:0]
            (block_addr >> 2) & 0xFF,  # block[9:2]
        ]
        for i in range(len(expect_addrs)):
            assert ret.event_df.iloc[i + 1]["event"] == "addr_in"
            assert ret.event_df.iloc[i + 1]["io_raw"] == expect_addrs[i]
            assert ret.event_df.iloc[i + 1]["io_dir_raw"] == 0xFF
            assert ret.event_df.iloc[i + 1]["ceb0"] == (0 if cs == 0 else 1)
            assert ret.event_df.iloc[i + 1]["ceb1"] == (0 if cs == 1 else 1)

        # Data Input
        for i in range(len(datas)):
            assert ret.event_df.iloc[i + 5]["event"] == "data_in"
            assert ret.event_df.iloc[i + 5]["io_raw"] == datas[i] & 0xFF
            assert ret.event_df.iloc[i + 5]["io_dir_raw"] == 0xFF
            assert ret.event_df.iloc[i + 5]["ceb0"] == (0 if cs == 0 else 1)
            assert ret.event_df.iloc[i + 5]["ceb1"] == (0 if cs == 1 else 1)
        # Write 2nd cycle
        assert ret.event_df.iloc[len(datas) + 5]["event"] == "cmd_in"
        assert ret.event_df.iloc[len(datas) + 5]["io_raw"] == NandCommandId.PROGRAM_2ND
        assert ret.event_df.iloc[len(datas) + 5]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[len(datas) + 5]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[len(datas) + 5]["ceb1"] == (0 if cs == 1 else 1)
        # status read
        assert ret.event_df.iloc[len(datas) + 6]["event"] == "cmd_in"
        assert ret.event_df.iloc[len(datas) + 6]["io_raw"] == NandCommandId.STATUS_READ
        assert ret.event_df.iloc[len(datas) + 6]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[len(datas) + 6]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[len(datas) + 6]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        assert ret.event_df.iloc[len(datas) + 7]["event"] == "data_out"
        assert (
            ret.event_df.iloc[len(datas) + 7]["io_raw"] == ret.received_from_rx_fifo[0]
        )  # status
        assert ret.event_df.iloc[len(datas) + 7]["io_dir_raw"] == 0x00
        assert ret.event_df.iloc[len(datas) + 7]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[len(datas) + 7]["ceb1"] == (0 if cs == 1 else 1)

    @pytest.mark.parametrize(
        "cs,block_addr",
        [
            (0, 0),
            (1, 3),
            (0, 128),
            (1, 256),
            (1, 1023),
        ],
    )
    def test_seq_erase(self, cs: int, block_addr: int):
        pio_prg_arr = array.array("I")
        PioCmdBuilder.seq_erase(pio_prg_arr, cs, block_addr)
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100,
            tx_fifo_entries=pio_prg_arr,
        )

        # Erase 1st cycle
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.ERASE_1ST
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)
        # address input
        # 1st cycle: block[7:0]
        # 2nd cycle: block[15:8]
        expect_addrs = [
            block_addr & 0xFF,  # block[7:0]
            (block_addr >> 8) & 0xFF,  # block[15:8]
        ]
        for i in range(len(expect_addrs)):
            assert ret.event_df.iloc[i + 1]["event"] == "addr_in"
            assert ret.event_df.iloc[i + 1]["io_raw"] == expect_addrs[i]
            assert ret.event_df.iloc[i + 1]["io_dir_raw"] == 0xFF
            assert ret.event_df.iloc[i + 1]["ceb0"] == (0 if cs == 0 else 1)
            assert ret.event_df.iloc[i + 1]["ceb1"] == (0 if cs == 1 else 1)
        # Erase 2nd cycle
        assert ret.event_df.iloc[3]["event"] == "cmd_in"
        assert ret.event_df.iloc[3]["io_raw"] == NandCommandId.ERASE_2ND
        assert ret.event_df.iloc[3]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[3]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[3]["ceb1"] == (0 if cs == 1 else 1)
        # status read
        assert ret.event_df.iloc[4]["event"] == "cmd_in"
        assert ret.event_df.iloc[4]["io_raw"] == NandCommandId.STATUS_READ
        assert ret.event_df.iloc[4]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[4]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[4]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        assert ret.event_df.iloc[5]["event"] == "data_out"
        assert ret.event_df.iloc[5]["io_raw"] == ret.received_from_rx_fifo[0]
