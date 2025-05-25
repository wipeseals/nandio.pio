import pytest
from typing import List
from src.nandio import PIN_DIR_WRITE, PioCmdBuilder, NandCommandId, PioCmdId, Util


class TestPioCmdBuilder:
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
            assert payload[i + 2] == Util.bitor_cs(addr, cs)
