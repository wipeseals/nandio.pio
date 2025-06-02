from micropython import const
import array
import rp2

from mpy.driver import NandIo
from mpy.ftl import FlashTranslationLayer
from sim.nandio_pio import LBA, NandConfig, PioCmdBuilder, Util


class PioNandCommander:
    """
    PIO-based NAND Commander for Raspberry Pi Pico.

    Pin configuration for PIO.
    | bit                | 15  | 14  | 13  | 12  | 11  | 10  | 9    | 8    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
    | ------------------ | --- | --- | --- | --- | --- | --- | ---- | ---- | --- | --- | --- | --- | --- | --- | --- | --- |
    | hw: func           | rbb | reb | web | wpb | ale | cle | ceb1 | ceb0 | io7 | io6 | io5 | io4 | io3 | io2 | io1 | io0 |
    | hw: dir            | in  | out | out | out | out | out | out  | out  | io  | io  | io  | io  | io  | io  | io  | io  |
    | pio: pins-out      | -   | 14  | 13  | 12  | 11  | 10  | 9    | 8    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
    | pio: pins-in       | 15  | -   | -   | -   | -   | -   | -    | -    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
    | pio: pins-sideset  | -   | 4   | 3   | 2   | 1   | 0   | -    | -    | -   | -   | -   | -   | -   | -   | -   | -   |

    Sideset pin configuration for PIO. (w/o WPB)
    | description                 | reb | web | wpb | ale | cle |
    | --------------------------- | --- | --- | --- | --- | --- |
    | init                        | 1   | 1   | 1   | 0   | 0   |
    | data output state0          | 0   | 1   | 1   | 0   | 0   |
    | data output state1 (=init)  | 1   | 1   | 1   | 0   | 0   |
    | data input state0           | 1   | 0   | 1   | 0   | 0   |
    | data input state1 (=init)   | 1   | 1   | 1   | 0   | 0   |
    | cmd  latch state0           | 1   | 0   | 1   | 0   | 1   |
    | cmd  latch state1           | 1   | 1   | 1   | 0   | 1   |
    | addr latch state0           | 1   | 0   | 1   | 1   | 0   |
    | addr latch state1           | 1   | 1   | 1   | 1   | 0   |

    """

    def __init__(
        self,
        nandio: NandIo,
        timeout_ms: int = 1000,
        max_freq: int = 100_000_000,  # 100MHz
    ) -> None:
        self._timeout_ms = timeout_ms
        self._max_freq = max_freq
        self._nandio = nandio
        # for PIO
        self._out_pins = [
            nandio._io0,
            nandio._io1,
            nandio._io2,
            nandio._io3,
            nandio._io4,
            nandio._io5,
            nandio._io6,
            nandio._io7,
            nandio._ceb0,
            nandio._ceb1,
        ]
        self._sideset_pins = [
            nandio._cle,
            nandio._ale,
            nandio._wpb,
            nandio._web,
            nandio._reb,
        ]
        # rbb pin
        self._rbb_idx = const(15)
        # sideset pin index
        self._ss_idx_cle = const(0)
        self._ss_idx_ale = const(1)
        self._ss_idx_wpb = const(2)
        self._ss_idx_web = const(3)
        self._ss_idx_reb = const(4)
        # sideset pin states
        self._ss_state_init = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_web)
            | Util.bit_on(self._ss_idx_wpb)
        )
        self._ss_state_dout0 = Util.bit_on(self._ss_idx_web) | Util.bit_on(
            self._ss_idx_wpb
        )
        self._ss_state_dout1 = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_web)
            | Util.bit_on(self._ss_idx_wpb)
        )
        self._ss_state_din0 = Util.bit_on(self._ss_idx_reb) | Util.bit_on(
            self._ss_idx_wpb
        )
        self._ss_state_din1 = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_web)
            | Util.bit_on(self._ss_idx_wpb)
        )
        self._ss_state_cle0 = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_cle)
            | Util.bit_on(self._ss_idx_wpb)
        )
        self._ss_state_cle1 = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_web)
            | Util.bit_on(self._ss_idx_cle)
            | Util.bit_on(self._ss_idx_wpb)
        )
        self._ss_state_ale0 = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_ale)
            | Util.bit_on(self._ss_idx_wpb)
        )
        self._ss_state_ale1 = (
            Util.bit_on(self._ss_idx_reb)
            | Util.bit_on(self._ss_idx_web)
            | Util.bit_on(self._ss_idx_ale)
            | Util.bit_on(self._ss_idx_wpb)
        )

        # PIO assembly code
        # /nandio.pio からの移植
        @rp2.asm_pio(
            out_init=[rp2.PIO.OUT_HIGH] * len(self._out_pins),
            sideset_init=[rp2.PIO.OUT_HIGH] * len(self._sideset_pins),
            in_shiftdir=rp2.PIO.SHIFT_LEFT,
            out_shiftdir=rp2.PIO.SHIFT_RIGHT,
            autopush=True,
            push_thresh=32,
        )
        def __nandio_pio_asm_impl():
            wrap_target()
            ########################################################################
            # get command
            # cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }
            label("setup")
            pull(block).side(self._ss_state_init)
            out(pindirs, 16).side(self._ss_state_init)  # pindirs[15:0]
            out(x, 12).side(self._ss_state_init)  # transfer_count
            out(y, 4).side(self._ss_state_init)  # cmd_id[3:0]
            # cmd_1 = { cmd_idにより指定 }
            pull(block).side(self._ss_state_init)
            ########################################################################
            # bitbang command
            # check cmd_id
            label("bitbang_setup")
            jmp(y_dec, "cmd_latch_setup").side(self._ss_state_init)
            # 指定した内容をそのまま出力。io/CSの設定を行う。
            # cmd_1 = { pins_data[9:0] }
            #         { ceb1, ceb0, io7, io6, io5, io4, io3, io2, io1, io0 }
            label("bitbang_main")
            out(pins, len(self._out_pins)).side(self._ss_state_init)
            jmp("setup").side(self._ss_state_init)

            ########################################################################
            # cmd latch command
            # check cmd_id
            label("cmd_latch_setup")
            jmp(y_dec, "addr_latch_setup").side(self._ss_state_init)
            # 指定したCmdIdをCLE=1, /WE=L->H, /WP=L で出力
            # cmd_1 = { ceb[1:0], nand_cmd_id[7:0] }
            # t_cls = 12ns / 2cyc = 6ns => 166MHz
            label("cmd_latch_main")
            out(pins, len(self._out_pins)).side(self._ss_state_cle0)  # CLE=H /WE=L 1cyc
            nop().side(self._ss_state_cle0)  #  CLE=H /WE=H 2cyc
            jmp("setup").side(self._ss_state_cle1)  #  CLE=1, /WE=H (t_clh>5ns)

            ########################################################################
            # addr latch command
            label("addr_latch_setup")
            jmp(y_dec, "data_out_setup").side(self._ss_state_init)
            label("addr_latch_main")
            # cmd_1 = { reserved }
            # data_0, data_1, data_2, ... (transfer_count分だけ) : { ceb[1:0], addr[7:0] }
            # t_als = 12ns / 2cyc = 6ns => 166MHz
            pull(block).side(self._ss_state_ale0)  # ALE=H /WE=L 1cyc
            out(pins, len(self._out_pins)).side(self._ss_state_ale0)  # ALE=H /WE=L 2cyc
            jmp(x_dec, "addr_latch_main").side(
                self._ss_state_ale1
            )  # ALE=H /WE=H (t_alh>5ns)
            jmp("setup").side(self._ss_state_init)

            ########################################################################
            # data output command
            label("data_out_setup")
            jmp(y_dec, "data_input_setup").side(self._ss_state_init)
            label("data_out_main")
            # cmd_1 = { reserved }
            # transfer_count分だけ /RE をトグルし、データをGPIOから読み取りpush
            # /RE=L (t_rr + t_rea = 40ns / 4cyc => 10ns = 100MHz)
            nop().side(self._ss_state_dout0)  # /RE=L 1cyc
            nop().side(self._ss_state_dout0)  # /RE=L 2cyc
            nop().side(self._ss_state_dout0)  # /RE=L 3cyc
            nop().side(self._ss_state_dout0)  # /RE=L 4cyc
            in_(pins, 8).side(self._ss_state_dout1)  # /RE=H, ceb0/1は無視
            jmp(x_dec, "data_out_main").side(self._ss_state_dout1)  # /RE=H
            push(block).side(self._ss_state_dout1)  # 非4byte align分の強制吐き出し
            jmp("setup").side(self._ss_state_dout1)

            ########################################################################
            # data input command
            label("data_input_setup")
            jmp(y_dec, "wait_rbb_setup").side(self._ss_state_init)
            label("data_input_main")
            # cmd_1 = { reserved }
            # data_0, data_1, data_2, ... (transfer_count分だけ) : { ceb[1:0], data[7:0] }
            # t_ds = 12ns / 2cyc = 6ns => 166MHz
            pull(block).side(self._ss_state_din0)  # /WE=L 1cyc
            out(pins, len(self._out_pins)).side(self._ss_state_din0)  # /WE=L 2cyc
            jmp(x_dec, "data_input_main").side(self._ss_state_din1)
            jmp("setup").side(self._ss_state_init)

            ########################################################################
            # wait_rbb_setup
            label("wait_rbb_setup")
            # 命令数削減のため、以後のcmdidはすべて wait_rbb扱い
            label("wait_rbb_main")
            wait(1, gpio, self._rbb_idx).side(self._ss_state_init)
            wrap()

        self._nandio_pio_asm = __nandio_pio_asm_impl

        # DREQ Assign
        # DREQ# = PIO# * 4 + (4 if RX else 0) + SM#
        # | PIO | SM | PORT | DREQ# | Description           |
        # |-----|----| -----|-------|-----------------------|
        # | 0   | 0  | TX   | 0     | PIO0 SM0 TX DREQ      |
        # | 0   | 0  | RX   | 4     | PIO0 SM0 RX DREQ      |
        # | 1   | 0  | TX   | 8     | PIO1 SM0 TX DREQ      |
        # | 1   | 0  | RX   | 12    | PIO1 SM0 RX DREQ      |
        self._pio0_sm0_tx_dreq = const(0)
        self._pio0_sm0_rx_dreq = const(4)
        self._pio1_sm0_tx_dreq = const(8)
        self._pio1_sm0_rx_dreq = const(12)

    def setup_pio0_nandio(self) -> rp2.StateMachine:
        """nandio.pioのセットアップ"""
        sm = rp2.StateMachine(0)
        sm.init(
            prog=self._nandio_pio_asm,
            freq=self._max_freq,
            in_base=self._nandio._io0,
            out_base=self._nandio._io0,
            sideset_base=self._nandio._cle,
            in_shiftdir=rp2.PIO.SHIFT_LEFT,
            out_shiftdir=rp2.PIO.SHIFT_RIGHT,
        )  # type: ignore
        return sm

    def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        # 4byte単位で受信するデータ数
        read_bytes = Util.roundup4(num_bytes)

        ###########################################################
        # Setup PIO State Machine
        # RESET + READID + IRQ のコマンドシーケンスを送信
        sm0 = self.setup_pio0_nandio()
        sm0.active(1)

        tx_payload = array.array("I")
        PioCmdBuilder.seq_reset(tx_payload, cs=chip_index)
        PioCmdBuilder.seq_read_id(tx_payload, cs=chip_index, data_count=read_bytes)

        ###########################################################
        # Setup TX DMA
        tx_dma0 = rp2.DMA()
        tx_dma0_ctrl = tx_dma0.pack_ctrl(
            size=2,  # 4byte転送
            inc_read=True,
            inc_write=False,  # tx_fifoは場所固定
            bswap=False,
            treq_sel=self._pio0_sm0_tx_dreq,  # PIO0 SM0 TX DREQ
        )
        tx_dma0.config(
            read=tx_payload,
            write=sm0,
            count=len(tx_payload),
            ctrl=tx_dma0_ctrl,
            trigger=True,
        )
        #############################################################
        # Setup RX DMA
        rx_data = array.array("B", [0] * read_bytes)

        rx_dma0 = rp2.DMA()
        rx_dma0_ctrl = rx_dma0.pack_ctrl(
            size=2,  # 4byte転送
            inc_read=False,  # rx_fifoは場所固定
            inc_write=True,
            bswap=True,  # 受信データはBig Endianなので、バイトオーダーを反転
            treq_sel=self._pio0_sm0_rx_dreq,  # PIO0 SM0 RX DREQ
        )
        rx_dma0.config(
            read=sm0,
            write=rx_data,
            count=read_bytes // 4,  # 4byte単位で設定
            ctrl=rx_dma0_ctrl,
            trigger=True,
        )

        #############################################################
        # wait for finished
        while rx_dma0.active():
            print(
                f"waiting. tx_dma0.active(): {tx_dma0.active()}, tx_fifo: {sm0.tx_fifo()}, rx_fifo: {sm0.rx_fifo()}, rx_dma0.active(): {rx_dma0.active()}"
            )
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()

        for i in range(len(rx_data)):
            print(f"RX Data[{i}]: {rx_data[i]:#02x}")

    def read_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        col: int = 0,
        num_bytes: int = NandConfig.PAGE_ALL_BYTES,
    ) -> bytearray | None:
        pass

    def read_status(self, chip_index: int) -> int:
        pass

    def erase_block(self, chip_index: int, block: int) -> bool:
        pass

    def program_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        data: bytearray,
        col: int = 0,
    ) -> bool:
        pass


def test_pio() -> None:
    nandio = NandIo()
    pio_commander = PioNandCommander(nandio)
    pio_commander.read_id(0)


def main() -> None:
    ftl = FlashTranslationLayer()

    def create_test_data(lba: LBA) -> bytearray:
        return bytearray([lba] * NandConfig.SECTOR_BYTES)

    for lba in range(0, 10):
        ftl.write_logical(lba, create_test_data(lba))
    for lba in reversed(range(0, 10)):
        read_data = ftl.read_logical(lba)
        print(f"LBA {lba} -> Read Data: {list(read_data)}")
        assert read_data is not None, f"Read data is None for LBA {lba}"


if __name__ == "__main__":
    test_pio()
    # main()
