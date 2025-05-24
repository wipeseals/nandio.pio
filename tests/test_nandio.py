import pytest
import itertools
from src.nandio import PIN_DIR_WRITE, CmdBuilder, NandCommandId, PioCmdId, Util


def test_create_reset_payload():
    cs = 0
    tx_fifo = list(
        itertools.chain.from_iterable(
            [
                CmdBuilder.init_pin(),
                CmdBuilder.assert_cs(select_cs=cs),
                CmdBuilder.cmd_latch(
                    cmd=NandCommandId.Reset,
                    select_cs=cs,
                ),
                CmdBuilder.deassert_cs(select_cs=cs),
            ]
        )
    )

    # cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }
    assert tx_fifo[0x0] == (PioCmdId.Bitbang << 28) | (0x0000 << 16) | PIN_DIR_WRITE
    # arg_0 = { arg0[31:0] }
    assert tx_fifo[0x1] == (0x00000000 | Util.bitmerge_cs(0x00, None))
