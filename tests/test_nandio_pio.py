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
        assert ret.event_df.iloc[0]["ceb0"] == 0 if cs == 0 else 1
        assert ret.event_df.iloc[0]["ceb1"] == 0 if cs == 1 else 1
        # Addr In
        assert ret.event_df.iloc[1]["event"] == "addr_in"
        assert ret.event_df.iloc[1]["io_raw"] == offset
        assert ret.event_df.iloc[1]["io_dir_raw"] == 0xFF
        assert ret.event_df.iloc[1]["ceb0"] == 0 if cs == 0 else 1
        assert ret.event_df.iloc[1]["ceb1"] == 0 if cs == 1 else 1
        # Data Output
        for i in range(data_count):
            assert ret.event_df.iloc[i + 2]["event"] == "data_out"
            assert (
                ret.event_df.iloc[i + 2]["io_raw"] == ret.received_from_rx_fifo[i]
            )  # created random value from the simulator
            assert ret.event_df.iloc[i + 2]["io_dir_raw"] == 0x00  # read
            assert ret.event_df.iloc[i + 2]["ceb0"] == 0 if cs == 0 else 1
            assert ret.event_df.iloc[i + 2]["ceb1"] == 0 if cs == 1 else 1
