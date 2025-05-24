from typing import List
import pytest
import itertools
from src.nandio import PIN_DIR_WRITE, CmdBuilder, NandCommandId, PioCmdId, Util


class TestCmdBuilder:
    def test_init_pin(self):
        payload: List[int] = CmdBuilder.init_pin()
        # cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }
        # arg_0 = { arg0[31:0] }
        assert payload[0x0] == (PioCmdId.Bitbang << 28) | (0x0000 << 16) | PIN_DIR_WRITE
        assert payload[0x1] == (
            0x00000000 | Util.bitmerge_cs(0x00, None)
        )  # CS0/1ともに非選択

    @pytest.mark.parametrize(
        "cs",
        [0, 1],
    )
    def test_create_reset_payload(self, cs: int):
        payload: List[int] = CmdBuilder.seq_reset(cs)

        # cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }
        # arg_0 = { arg0[31:0] }
        assert payload[0x0] == (PioCmdId.Bitbang << 28) | (0x0000 << 16) | PIN_DIR_WRITE
        assert payload[0x1] == (0x00000000 | Util.bitmerge_cs(0x00, None))
