import array
import rp2

from mpy.driver import NandIo, PioNandCommander
from mpy.ftl import FlashTranslationLayer
from sim.nandio_pio import LBA, NandConfig, PioCmdBuilder, Util


def test_pio() -> None:
    nandio = NandIo()
    # pio_commander = PioNandCommander(nandio)
    # pio_commander.read_id(0)

    chip_index = 0
    required_freq = int(83e6)  # TODO: これ以下にしておく

    class PinConfig:
        """
        Pin configuration for PIO.
        | bit                | 15  | 14  | 13  | 12  | 11  | 10  | 9    | 8    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
        | ------------------ | --- | --- | --- | --- | --- | --- | ---- | ---- | --- | --- | --- | --- | --- | --- | --- | --- |
        | hw: func           | rbb | reb | web | wpb | ale | cle | ceb1 | ceb0 | io7 | io6 | io5 | io4 | io3 | io2 | io1 | io0 |
        | hw: dir            | in  | out | out | out | out | out | out  | out  | io  | io  | io  | io  | io  | io  | io  | io  |
        | pio: pins-out      | -   | 14  | 13  | 12  | 11  | 10  | 9    | 8    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
        | pio: pins-in       | 15  | -   | -   | -   | -   | -   | -    | -    | 7   | 6   | 5   | 4   | 3   | 2   | 1   | 0   |
        | pio: pins-sideset  | -   | 4   | 3   | 2   | 1   | 0   | -    | -    | -   | -   | -   | -   | -   | -   | -   | -   |
        """

        out_pins = [
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
            nandio._cle,
            nandio._ale,
            nandio._wpb,
            nandio._web,
            nandio._reb,
        ]
        sideset_pins = [
            nandio._cle,
            nandio._ale,
            nandio._wpb,
            nandio._web,
            nandio._reb,
        ]

        SIDESET_CLE_IDX = 0
        SIDESET_ALE_IDX = 1
        SIDESET_WPB_IDX = 2
        SIDESET_WEB_IDX = 3
        SIDESET_REB_IDX = 4

    class SidesetState:
        """
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

        INIT = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WEB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )
        DOUT_0 = Util.bit_on(PinConfig.SIDESET_WEB_IDX) | Util.bit_on(
            PinConfig.SIDESET_WPB_IDX
        )
        DOUT_1 = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WEB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )
        DIN_0 = Util.bit_on(PinConfig.SIDESET_REB_IDX) | Util.bit_on(
            PinConfig.SIDESET_WPB_IDX
        )
        DIN_1 = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WEB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )
        CLE_0 = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_CLE_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )
        CLE_1 = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WEB_IDX)
            | Util.bit_on(PinConfig.SIDESET_CLE_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )
        ALE_0 = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_ALE_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )
        ALE_1 = (
            Util.bit_on(PinConfig.SIDESET_REB_IDX)
            | Util.bit_on(PinConfig.SIDESET_WEB_IDX)
            | Util.bit_on(PinConfig.SIDESET_ALE_IDX)
            | Util.bit_on(PinConfig.SIDESET_WPB_IDX)
        )

    @rp2.asm_pio(
        out_init=[rp2.PIO.OUT_HIGH] * len(PinConfig.out_pins),
        sideset_init=[rp2.PIO.OUT_HIGH] * len(PinConfig.sideset_pins),
        in_shiftdir=rp2.PIO.SHIFT_LEFT,
        out_shiftdir=rp2.PIO.SHIFT_RIGHT,
        autopush=False,
        autopull=False,
        fifo_join=rp2.PIO.JOIN_TX | rp2.PIO.JOIN_RX,
    )
    def nandio_pio_asm():
        wrap_target()
        ########################################################################
        # get command
        # cmd_0 = { cmd_id[3:0], transfer_count[11:0], pindirs[15:0] }
        label("setup")
        pull(block).side(SidesetState.INIT)
        out(pindirs, 16).side(SidesetState.INIT)  # pindirs[15:0]
        out(x, 12).side(SidesetState.INIT)  # transfer_count
        out(y, 4).side(SidesetState.INIT)  # cmd_id[3:0]
        # cmd_1 = { cmd_idにより指定 }
        pull(block).side(SidesetState.INIT)
        ########################################################################
        # bitbang command
        # check cmd_id
        label("bitbang_setup")
        jmp(y_dec, "cmd_latch_setup").side(SidesetState.INIT)
        # 指定した内容をそのまま出力。io/CSの設定を行う。
        # cmd_1 = { pins_data[9:0] }
        #         { ceb1, ceb0, io7, io6, io5, io4, io3, io2, io1, io0 }
        label("bitbang_main")
        out(pins, 10).side(SidesetState.INIT)
        jmp("setup")

        ########################################################################
        # cmd latch command
        # check cmd_id
        label("cmd_latch_setup")
        jmp(y_dec, "addr_latch_setup").side(SidesetState.INIT)
        # 指定したCmdIdをCLE=1, /WE=L->H, /WP=L で出力
        # cmd_1 = { ceb[1:0], nand_cmd_id[7:0] }
        label("cmd_latch_main")
        out(pins, 10).side(SidesetState.CLE_0)  # CLE=H /WE=L
        nop().side(SidesetState.CLE_1)  #  CLE=H /WE=H (t_cls>12ns)
        jmp("setup").side(SidesetState.CLE_1)  #  CLE=1, /WE=H (t_clh>5ns)

        ########################################################################
        # addr latch command
        label("addr_latch_setup")
        jmp(y_dec, "data_out_setup").side(SidesetState.INIT)
        label("addr_latch_main")
        # cmd_1 = { reserved }
        # data_0, data_1, data_2, ... (transfer_count分だけ) : { ceb[1:0], addr[7:0] }
        pull(block).side(SidesetState.ALE_0)  # ALE=H /WE=L
        out(pins, 10).side(SidesetState.ALE_0)  # ALE=H /WE=L (t_als>12ns)
        jmp(x_dec, "addr_latch_main").side(
            SidesetState.ALE_1
        )  # ALE=H /WE=H (t_alh>5ns)
        jmp("setup").side(SidesetState.INIT)

        ########################################################################
        # data output command
        label("data_out_setup")
        jmp(y_dec, "data_input_setup").side(SidesetState.INIT)
        label("data_out_main")
        # cmd_1 = { reserved }
        # transfer_count分だけ /RE をトグルし、データをGPIOから読み取りpush
        nop().side(SidesetState.DOUT_0)  # /RE=L
        nop().side(SidesetState.DOUT_0)  # /RE=L (t_rp>12ns)
        in_(pins, 8).side(SidesetState.DOUT_1)  # /RE=H
        push(block).side(SidesetState.DOUT_1)  # /RE=H (t_rh>5ns)
        jmp(x_dec, "data_out_main").side(SidesetState.DOUT_1)  # /RE=H
        jmp("setup").side(SidesetState.INIT)

        ########################################################################
        # data input command
        label("data_input_setup")
        jmp(y_dec, "set_irq_setup").side(SidesetState.INIT)
        label("data_input_main")
        # cmd_1 = { reserved }
        # data_0, data_1, data_2, ... (transfer_count分だけ) : { ceb[1:0], data[7:0] }
        pull(block).side(SidesetState.DIN_0)  # /WE=L
        out(pins, 10).side(SidesetState.DIN_0)  # /WE=L (t_wp>12ns)
        jmp(x_dec, "data_input_main").side(SidesetState.DIN_1)
        jmp("setup").side(SidesetState.INIT)

        ########################################################################
        # set irq command
        label("set_irq_setup")
        jmp(y_dec, "wait_rbb_setup").side(SidesetState.INIT)
        label("set_irq_main")
        # cmd_1 = { reserved }
        irq(0).side(SidesetState.INIT)
        # 命令数削減のため、wait_rbbも兼ねる

        ########################################################################
        # wait_rbb_setup
        label("wait_rbb_setup")
        # 命令数削減のため、以後のcmdidはすべて wait_rbb扱い
        label("wait_rbb_main")
        wait(1, gpio, 15).side(SidesetState.INIT)
        wrap()

    sm = rp2.StateMachine(0)
    sm.init(
        prog=nandio_pio_asm,
        freq=-1,  # TODO: 疎通できたら姑息可
        in_base=nandio._io0,
        out_base=nandio._io0,
        set_base=nandio._io0,
        jmp_pin=None,
        sideset_base=nandio._cle,  # [REB,WEB,WPB,ALE,CLE]
        in_shiftdir=rp2.PIO.SHIFT_LEFT,
        out_shiftdir=rp2.PIO.SHIFT_RIGHT,
        push_thresh=None,
        pull_thresh=None,
    )
    sm.active(1)

    tx_data = array.array("I")
    PioCmdBuilder.seq_reset(tx_data, cs=chip_index)
    PioCmdBuilder.seq_read_id(tx_data, cs=chip_index)
    PioCmdBuilder.set_irq(tx_data)

    # TODO: DMAに置き換え
    # TODO: DMA完了後、データの受信まではIRQとDMAの完了で待つ
    # send data
    for payload in tx_data:
        print(f"Sending payload: {payload:#010x}")
        sm.put(payload)

    # receive data
    rx_data = array.array("I", [0] * num_bytes)
    # wait data
    while not sm.rx_fifo():
        pass
    sm.get(rx_data)
    print(f"Received data: {rx_data}")


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
