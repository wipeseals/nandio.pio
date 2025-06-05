import uasyncio
import utime
from micropython import const
import array
import rp2

from mpy.driver import NandIo
from mpy.ftl import FlashTranslationLayer
from sim.nandio_pio import (
    LBA,
    NandCommandId,
    NandConfig,
    NandStatus,
    PioCmdBuilder,
    Util,
)


class Dreq:
    """
    DMA Data Request (DREQ) Assign
    DREQ# = PIO# * 4 + (4 if RX else 0) + SM#
    | PIO | SM | PORT | DREQ# | Description           |
    |-----|----| -----|-------|-----------------------|
    | 0   | 0  | TX   | 0     | PIO0 SM0 TX DREQ      |
    | 0   | 0  | RX   | 4     | PIO0 SM0 RX DREQ      |
    | 1   | 0  | TX   | 8     | PIO1 SM0 TX DREQ      |
    | 1   | 0  | RX   | 12    | PIO1 SM0 RX DREQ      |
    """

    PIO0_SM0_TX = const(0)
    PIO0_SM0_RX = const(4)
    PIO1_SM0_TX = const(8)
    PIO1_SM0_RX = const(12)


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
        timeout_ms: int = 5000,
        max_freq: int = 125_000_000,
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
        # 1byte のデータを受信し、上位2bitにCSをmergeする
        @rp2.asm_pio()
        def __merge_cs_pio_asm_impl():
            ########################################################################
            # setup
            # 4byte受信して、bitor元データとしてscratch xに保持
            pull(block)  # fifo -> osr
            out(x, 32)  # osr  -> x

            ########################################################################
            # main
            wrap_target()
            pull(block)  # fifo -> osr
            mov(isr, x)  # x    -> isr : isr = x
            in_(osr, 8)  # osr  -> isr : isr = (x << 8) | osr
            push(block)  # isr  -> fifo
            wrap()

        self._merge_cs_pio_asm = __merge_cs_pio_asm_impl

        # PIO assembly code
        # nandio.pio からの移植. NAND IO Driver
        @rp2.asm_pio(
            out_init=[rp2.PIO.OUT_HIGH] * len(self._out_pins),
            sideset_init=[rp2.PIO.OUT_HIGH] * len(self._sideset_pins),
            in_shiftdir=rp2.PIO.SHIFT_LEFT,
            out_shiftdir=rp2.PIO.SHIFT_RIGHT,
            autopush=True,
            push_thresh=8,
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
            # /RE=L (t_rr + t_rea = 40ns / 5cyc => 8ns = 125MHz)
            nop().side(self._ss_state_dout0)  # /RE=L 1cyc
            nop().side(self._ss_state_dout0)  # /RE=L 2cyc
            nop().side(self._ss_state_dout0)  # /RE=L 3cyc
            nop().side(self._ss_state_dout0)  # /RE=L 4cyc
            nop().side(self._ss_state_dout0)  # /RE=L 5cyc
            in_(pins, 8).side(self._ss_state_dout1)  # /RE=H, ceb0/1は無視
            jmp(x_dec, "data_out_main").side(self._ss_state_dout1)  # /RE=H
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

    def _setup_pio0_nandio(self) -> rp2.StateMachine:
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

    def _setup_pio1_merge_cs(self) -> rp2.StateMachine:
        """merge_cs_pioのセットアップ"""
        sm = rp2.StateMachine(4)  # PIO1/SM0
        sm.init(
            prog=self._merge_cs_pio_asm,
            freq=self._max_freq,
            in_shiftdir=rp2.PIO.SHIFT_LEFT,
            out_shiftdir=rp2.PIO.SHIFT_RIGHT,
        )  # type: ignore
        return sm

    def _setup_tx_dma_payload(
        self,
        dreq: int,
        sm: rp2.StateMachine,
        tx_payload: array.array,
    ) -> rp2.DMA:
        """TX payload送信用DMAのセットアップ"""
        dma = rp2.DMA()

        tx_dma0_ctrl = dma.pack_ctrl(
            size=2,  # 4byte転送
            inc_read=True,
            inc_write=False,  # tx_fifoは場所固定
            bswap=False,
            treq_sel=dreq,
        )
        dma.config(
            read=tx_payload,
            write=sm,
            count=len(tx_payload),
            ctrl=tx_dma0_ctrl,
            trigger=False,  # 自動開始しない
        )
        return dma

    def _setup_tx_dma_data(
        self,
        dreq: int,
        sm: rp2.StateMachine,
        data: bytearray,
    ) -> rp2.DMA:
        """TX payload送信用DMAのセットアップ"""
        dma = rp2.DMA()

        tx_dma0_ctrl = dma.pack_ctrl(
            size=0,  # 1byte転送
            inc_read=True,
            inc_write=False,  # tx_fifoは場所固定
            bswap=False,
            treq_sel=dreq,
        )
        dma.config(
            read=data,
            write=sm,
            count=len(data),
            ctrl=tx_dma0_ctrl,
            trigger=False,  # 自動開始しない
        )
        return dma

    def _setup_rx_dma_data(
        self, dreq: int, sm: rp2.StateMachine, rx_data: bytearray, num_bytes: int
    ) -> rp2.DMA:
        """データ受信用DMAのセットアップ"""
        dma = rp2.DMA()
        rx_dma0_ctrl = dma.pack_ctrl(
            size=0,  # 1byte転送
            inc_read=False,  # rx_fifoは場所固定
            inc_write=True,
            bswap=False,
            treq_sel=dreq,
        )
        dma.config(
            read=sm,
            write=rx_data,
            count=num_bytes,
            ctrl=rx_dma0_ctrl,
            trigger=False,
        )
        return dma

    async def _wait_for_dma(self, dma: rp2.DMA, f=None) -> None:
        """DMAが完了するまで待機"""
        start_ms = utime.ticks_ms()
        while dma.active():
            if f:
                f()
            await uasyncio.sleep_ms(1)
            elapsed_ms = utime.ticks_diff(utime.ticks_ms(), start_ms)
            if elapsed_ms > self._timeout_ms:
                raise RuntimeError(
                    f"Timeout while waiting for DMA to finish. Elapsed: {elapsed_ms} ms"
                )

    async def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        sm0 = self._setup_pio0_nandio()
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_reset(tx_payload, cs=chip_index)
        PioCmdBuilder.seq_read_id(tx_payload, cs=chip_index, data_count=num_bytes)
        tx_dma0 = self._setup_tx_dma_payload(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )
        tx_dma0.active(1)

        # RX Data
        rx_data = bytearray(num_bytes)
        rx_dma0 = self._setup_rx_dma_data(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=num_bytes
        )
        rx_dma0.active(1)
        await self._wait_for_dma(rx_dma0)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()
        return rx_data

    async def read_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        col: int = 0,
        num_bytes: int = NandConfig.PAGE_ALL_BYTES,
    ) -> bytearray | None:
        sm0 = self._setup_pio0_nandio()
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_read(
            tx_payload,
            cs=chip_index,
            column_addr=col,
            page_addr=page,
            block_addr=block,
            data_count=num_bytes,
        )
        tx_dma0 = self._setup_tx_dma_payload(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )
        tx_dma0.active(1)

        # RX Data
        rx_data = bytearray(num_bytes)
        rx_dma0 = self._setup_rx_dma_data(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=num_bytes
        )
        rx_dma0.active(1)
        await self._wait_for_dma(rx_dma0)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()
        return rx_data

    async def read_status(self, chip_index: int) -> int:
        sm0 = self._setup_pio0_nandio()
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_status_read(tx_payload, cs=chip_index)
        tx_dma0 = self._setup_tx_dma_payload(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )
        tx_dma0.active(1)

        # RX Data
        rx_data = bytearray(1)
        rx_dma0 = self._setup_rx_dma_data(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )
        rx_dma0.active(1)
        await self._wait_for_dma(rx_dma0)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()
        return rx_data[0]

    async def erase_block(self, chip_index: int, block: int) -> bool:
        sm0 = self._setup_pio0_nandio()
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_erase(tx_payload, cs=chip_index, block_addr=block)
        PioCmdBuilder.seq_status_read(tx_payload, cs=chip_index)
        tx_dma0 = self._setup_tx_dma_payload(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )
        tx_dma0.active(1)

        # RX Data
        rx_data = bytearray(1)
        rx_dma0 = self._setup_rx_dma_data(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )
        rx_dma0.active(1)
        await self._wait_for_dma(rx_dma0)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()

        is_ok = (rx_data[0] & NandStatus.PROGRAM_ERASE_FAIL) == 0
        return is_ok

    async def _bitor_cs(self, chip_index: int, data: bytearray) -> array.array:
        """PIO + DMAを使用して、CSをビットORする. 1byte -> 4byte"""
        sm4 = self._setup_pio1_merge_cs()
        sm4.active(1)

        # CEB[1:0] に設定する値を合成するPIO
        bitor_data = 0xFFFFFFFF & ~(1 << chip_index)
        sm4.put(bitor_data)

        tx_dma0 = self._setup_tx_dma_data(dreq=Dreq.PIO1_SM0_TX, sm=sm4, data=data)
        tx_dma0.active(1)

        rx_data = array.array("I", Util.roundup4(len(data)) * [0])
        rx_dma0 = rp2.DMA()
        rx_dma0_ctrl = rx_dma0.pack_ctrl(
            size=2,  # 4byte転送
            inc_read=False,  # rx_fifoは場所固定
            inc_write=True,
            treq_sel=Dreq.PIO1_SM0_RX,
        )
        rx_dma0.config(
            read=sm4,
            write=rx_data,
            count=len(rx_data),
            ctrl=rx_dma0_ctrl,
            trigger=False,
        )
        rx_dma0.active(1)
        await self._wait_for_dma(rx_dma0)

        return rx_data

    async def program_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        data: bytearray,
        col: int = 0,
    ) -> bool:
        sm0 = self._setup_pio0_nandio()
        sm0.active(1)

        data_extend = array.array("I", [x for x in data])
        tx_payload0 = array.array("I")
        PioCmdBuilder.seq_program(
            tx_payload0,
            cs=chip_index,
            column_addr=col,
            page_addr=page,
            block_addr=block,
            data=data_extend,
        )

        tx_dma0 = self._setup_tx_dma_payload(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload0
        )
        tx_dma0.active(1)

        rx_data = bytearray(1)
        rx_dma0 = self._setup_rx_dma_data(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )
        rx_dma0.active(1)

        await self._wait_for_dma(rx_dma0)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()

        is_ok = (rx_data[0] & NandStatus.PROGRAM_ERASE_FAIL) == 0
        return is_ok


async def test_pio() -> None:
    nandio = NandIo()
    pio_commander = PioNandCommander(nandio)
    id = await pio_commander.read_id(0)

    for i, byte in enumerate(id):
        print(f"ID Byte {i}: {byte:02x}")

    data = await pio_commander.read_page(chip_index=0, block=0, page=0, col=0)
    print(f"Read Page Data: {list(data)}")

    status = await pio_commander.read_status(chip_index=0)
    print(f"Read Status: {status:02x}")

    is_erased = await pio_commander.erase_block(chip_index=0, block=0)
    print(f"Erase Block Result: {'Success' if is_erased else 'Failure'}")

    data = await pio_commander.read_page(chip_index=0, block=0, page=0, col=0)
    print(f"Read Page Data: {list(data)}")

    is_programmed = await pio_commander.program_page(
        chip_index=0,
        block=0,
        page=0,
        data=bytearray([x & 0xFF for x in range(NandConfig.PAGE_ALL_BYTES)]),
        col=0,
    )
    print(f"Program Page Result: {'Success' if is_programmed else 'Failure'}")

    data = await pio_commander.read_page(chip_index=0, block=0, page=0, col=0)
    print(f"Read Page Data: {list(data)}")


async def main() -> None:
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
    uasyncio.run(test_pio())
    # main()
