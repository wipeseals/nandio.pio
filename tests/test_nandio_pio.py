from pathlib import Path
import pytest
from typing import List
from src.nandio_pio import (
    PIN_DIR_READ,
    PIN_DIR_WRITE,
    PioCmdBuilder,
    NandCommandId,
    PioCmdId,
    Util,
)
from src.simulator import Result, Simulator


class TestPioCmdBuilderBasics:
    @staticmethod
    def cmd0(
        cmd: PioCmdId,
        dir: int,
        count: int,
    ) -> int:
        """
        Encode the first command word for Test.
        `cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }`
        """
        return (cmd << 28) | ((count - 1) << 16) | dir

    def test_init_pin(self):
        payload: List[int] = PioCmdBuilder.init_pin()

        assert payload[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitor_cs(0x00, None)

    @pytest.mark.parametrize(
        "cs",
        [0, 1, None],
    )
    def test_assert_cs(self, cs: int | None):
        payload: List[int] = PioCmdBuilder.assert_cs(cs)

        assert payload[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitor_cs(0x00, cs)

    def test_deassert_cs(self):
        payload: List[int] = PioCmdBuilder.deassert_cs()

        assert payload[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitor_cs(0x00, None)

    @pytest.mark.parametrize(
        "cs",
        [0, 1, None],
    )
    @pytest.mark.parametrize(
        "cmd",
        [NandCommandId.Reset, NandCommandId.ReadId],
    )
    def test_cmd_latch(self, cs: int | None, cmd: int):
        payload: List[int] = PioCmdBuilder.cmd_latch(cmd, cs)

        assert payload[0x0] == self.cmd0(PioCmdId.CmdLatch, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitor_cs(cmd, cs)

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    @pytest.mark.parametrize(
        "addrs",
        [[0xAA, 0x99, 0x55, 0x66], [0x11, 0x22]],
    )
    def test_addr_latch(self, cs: int, addrs: List[int]):
        payload: List[int] = PioCmdBuilder.addr_latch(addrs, cs)

        assert payload[0x0] == self.cmd0(PioCmdId.AddrLatch, PIN_DIR_WRITE, len(addrs))
        assert payload[0x1] == 0x00  # don't care
        for i, addr in enumerate(addrs):
            # CS が追加されたデータを転送するはず
            assert payload[i + 2] == Util.bitor_cs(addr, cs)

    @pytest.mark.parametrize(
        "data_count",
        [1, 5, 2048],
    )
    def test_data_output(self, data_count: int):
        payload: List[int] = PioCmdBuilder.data_output(data_count)

        assert payload[0x0] == self.cmd0(PioCmdId.DataOutput, PIN_DIR_READ, data_count)
        assert payload[0x1] == 0x00  # don't care

    @pytest.mark.parametrize(
        "data_count",
        [1, 5, 2048],
    )
    def test_data_input_only_header(self, data_count: int):
        payload: List[int] = PioCmdBuilder.data_input_only_header(data_count)

        assert payload[0x0] == self.cmd0(PioCmdId.DataInput, PIN_DIR_WRITE, data_count)
        assert payload[0x1] == 0x00  # don't care

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    @pytest.mark.parametrize(
        "datas",
        [
            [0xAA, 0x99, 0x55, 0x66],
            [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88],
            list(range(512)),
            list(range(2048)),
        ],
    )
    def test_data_input(self, cs: int, datas: List[int]):
        payload: List[int] = PioCmdBuilder.data_input(datas, cs)

        assert payload[0x0] == self.cmd0(PioCmdId.DataInput, PIN_DIR_WRITE, len(datas))
        assert payload[0x1] == 0x00  # don't care
        for i, data in enumerate(datas):
            # CS が追加されたデータを転送するはず
            assert payload[i + 2] == Util.bitor_cs(data, cs)

    def test_set_irq(self):
        payload: List[int] = PioCmdBuilder.set_irq()

        assert payload[0x0] == self.cmd0(PioCmdId.SetIrq, PIN_DIR_WRITE, 1)
        assert payload[0x1] == 0x00

    def test_wait_rbb(self):
        payload: List[int] = PioCmdBuilder.wait_rbb()

        assert payload[0x0] == self.cmd0(PioCmdId.WaitRbb, PIN_DIR_WRITE, 1)
        assert payload[0x1] == 0x00


class TestPioCmdBuilderSequences:
    def setup_class(self):
        self.pio_text = Path("nandio.pio").read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    def test_seq_reset(self, cs: int):
        payload: List[int] = PioCmdBuilder.seq_reset(cs)
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100,
            tx_fifo_entries=payload,
        )

        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.Reset
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
        payload: List[int] = PioCmdBuilder.seq_read_id(
            cs, offset=offset, data_count=data_count
        )
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100,
            tx_fifo_entries=payload,
        )

        # READ ID
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.ReadId
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
        payload: List[int] = PioCmdBuilder.seq_read(
            cs, column_addr, page_addr, block_addr, data_count
        )
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100 + data_count * 10,
            tx_fifo_entries=payload,
        )

        # read 1st cycle
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.Read1stCycle
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
        assert ret.event_df.iloc[5]["io_raw"] == NandCommandId.Read2ndCycle
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
        payload: List[int] = PioCmdBuilder.seq_status_read(cs)
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=50,
            tx_fifo_entries=payload,
        )

        # Read Status
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.StatusRead
        assert ret.event_df.iloc[0]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[0]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[0]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        assert ret.event_df.iloc[1]["event"] == "data_out"
        assert ret.event_df.iloc[1]["io_raw"] == ret.received_from_rx_fifo[0]

    @pytest.mark.parametrize(
        "cs,column_addr,page_addr,block_addr,datas",
        [
            (0, 0, 0, 0, [0xAA, 0x99, 0x55, 0x66]),
            (1, 0, 0, 3, [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]),
            (0, 128, 33, 256, list(range(15))),
            (1, 256, 2, 3, list(range(512))),
            # too long
            # (0, 512, 16, 1023, list(range(2048))),
        ],
    )
    def test_seq_program(
        self,
        cs: int,
        column_addr: int,
        page_addr: int,
        block_addr: int,
        datas: List[int],
    ):
        payload: List[int] = PioCmdBuilder.seq_program(
            cs, column_addr, page_addr, block_addr, datas
        )
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100 + len(datas) * 10,
            tx_fifo_entries=payload,
        )

        # write 1st cycle
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.AutoPageProgram1stCycle
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
        assert (
            ret.event_df.iloc[len(datas) + 5]["io_raw"]
            == NandCommandId.AutoPageProgram2ndCycle
        )
        assert ret.event_df.iloc[len(datas) + 5]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[len(datas) + 5]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[len(datas) + 5]["ceb1"] == (0 if cs == 1 else 1)
        # status read
        assert ret.event_df.iloc[len(datas) + 6]["event"] == "cmd_in"
        assert ret.event_df.iloc[len(datas) + 6]["io_raw"] == NandCommandId.StatusRead
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
        payload: List[int] = PioCmdBuilder.seq_erase(cs, block_addr)
        ret: Result = Simulator.execute(
            program_str=self.pio_text,
            test_cycles=100,
            tx_fifo_entries=payload,
        )

        # Erase 1st cycle
        assert ret.event_df.iloc[0]["event"] == "cmd_in"
        assert ret.event_df.iloc[0]["io_raw"] == NandCommandId.AutoBlockErase1stCycle
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
        assert ret.event_df.iloc[3]["io_raw"] == NandCommandId.AutoBlockErase2ndCycle
        assert ret.event_df.iloc[3]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[3]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[3]["ceb1"] == (0 if cs == 1 else 1)
        # status read
        assert ret.event_df.iloc[4]["event"] == "cmd_in"
        assert ret.event_df.iloc[4]["io_raw"] == NandCommandId.StatusRead
        assert ret.event_df.iloc[4]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[4]["ceb0"] == (0 if cs == 0 else 1)
        assert ret.event_df.iloc[4]["ceb1"] == (0 if cs == 1 else 1)
        # Data Output
        assert ret.event_df.iloc[5]["event"] == "data_out"
        assert ret.event_df.iloc[5]["io_raw"] == ret.received_from_rx_fifo[0]
