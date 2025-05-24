from typing import List
import pytest
import itertools
from src.nandio import PIN_DIR_WRITE, CmdBuilder, NandCommandId, PioCmdId, Util


class TestCmdBuilder:
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
        payload: List[int] = CmdBuilder.init_pin()

        # arg_0 = { arg0[31:0] }
        assert payload[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitmerge_cs(0x00, None)

    @pytest.mark.parametrize(
        "cs",
        [0, 1, None],
    )
    def test_assert_cs(self, cs: int | None):
        payload: List[int] = CmdBuilder.assert_cs(cs)

        assert payload[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitmerge_cs(0x00, cs)

    def test_deassert_cs(self):
        payload: List[int] = CmdBuilder.deassert_cs()

        assert payload[0x0] == self.cmd0(PioCmdId.Bitbang, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitmerge_cs(0x00, None)

    @pytest.mark.parametrize(
        "cs",
        [0, 1, None],
    )
    @pytest.mark.parametrize(
        "cmd",
        [NandCommandId.Reset, NandCommandId.ReadId],
    )
    def test_cmd_latch(self, cs: int | None, cmd: int):
        payload: List[int] = CmdBuilder.cmd_latch(cmd, cs)

        assert payload[0x0] == self.cmd0(PioCmdId.CmdLatch, PIN_DIR_WRITE, 1)
        assert payload[0x1] == Util.bitmerge_cs(cmd, cs)
