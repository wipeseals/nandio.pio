import uctypes
import uasyncio
import utime
from micropython import const
import array
import time

from sim.nandio_pio import (
    NandConfig,
    NandAddr,
    NandCommandId,
    NandStatus,
    PinAssign,
    PioCmdBuilder,
    Util,
)
import nandio as nandio_pio

from machine import Pin
import rp2


class NandIo:
    def __init__(
        self,
        keep_wp: bool = True,
    ) -> None:
        self._keep_wp = keep_wp
        self._io0 = Pin(PinAssign.IO0, Pin.OUT)
        self._io1 = Pin(PinAssign.IO1, Pin.OUT)
        self._io2 = Pin(PinAssign.IO2, Pin.OUT)
        self._io3 = Pin(PinAssign.IO3, Pin.OUT)
        self._io4 = Pin(PinAssign.IO4, Pin.OUT)
        self._io5 = Pin(PinAssign.IO5, Pin.OUT)
        self._io6 = Pin(PinAssign.IO6, Pin.OUT)
        self._io7 = Pin(PinAssign.IO7, Pin.OUT)
        self._ceb0 = Pin(PinAssign.CEB0, Pin.OUT)
        self._ceb1 = Pin(PinAssign.CEB1, Pin.OUT)
        self._cle = Pin(PinAssign.CLE, Pin.OUT)
        self._ale = Pin(PinAssign.ALE, Pin.OUT)
        self._wpb = Pin(PinAssign.WPB, Pin.OUT)
        self._web = Pin(PinAssign.WEB, Pin.OUT)
        self._reb = Pin(PinAssign.REB, Pin.OUT)
        self._rbb = Pin(PinAssign.RBB, Pin.IN, Pin.PULL_UP)

        self._io = [
            self._io0,
            self._io1,
            self._io2,
            self._io3,
            self._io4,
            self._io5,
            self._io6,
            self._io7,
        ]
        self._ceb = [self._ceb0, self._ceb1]
        # debug indicator
        self._led = Pin("LED", Pin.OUT, value=1)
        self.setup_pin()

    async def delay(self) -> None:
        await uasyncio.sleep_ms(1)

    ########################################################
    # Low-level functions
    ########################################################

    async def set_io(self, value: int) -> None:
        for i in range(8):
            self._io[i].value((value >> i) & 0x1)

    async def get_io(self) -> int:
        value = 0
        for i in range(8):
            value |= self._io[i].value() << i
        return value

    async def set_io_dir(self, is_output: bool) -> None:
        for pin in self._io:
            pin.init(Pin.OUT if is_output else Pin.IN)

    async def set_ceb(self, chip_index: int | None) -> None:
        # status indicator
        self._led.toggle()

        assert chip_index is None or chip_index in [0, 1]
        if chip_index is None:
            self._ceb0.on()
            self._ceb1.on()
        else:
            self._ceb0.value(0 if chip_index == 0 else 1)
            self._ceb1.value(0 if chip_index == 1 else 1)

    async def set_cle(self, value: int) -> None:
        self._cle.value(value)

    async def set_ale(self, value: int) -> None:
        self._ale.value(value)

    async def set_web(self, value: int) -> None:
        self._web.value(value)

    def set_wpb(self, value: int) -> None:
        self._wpb.value(value)
        # serialにまつ
        utime.sleep_ms(1)  # wait for WPB to be set

    async def set_reb(self, value: int) -> None:
        self._reb.value(value)

    def setup_pin(self) -> None:
        for pin in self._io:
            pin.init(Pin.OUT)
            pin.off()
        for pin in self._ceb:
            pin.init(Pin.OUT)
            pin.on()
        self._cle.init(Pin.OUT)
        self._cle.off()
        self._ale.init(Pin.OUT)
        self._ale.off()
        self._wpb.init(Pin.OUT)
        if self._keep_wp:
            self.set_wpb(0)
        else:
            self.set_wpb(1)
        self._web.init(Pin.OUT)
        self._web.on()
        self._reb.init(Pin.OUT)
        self._reb.on()
        self._rbb.init(Pin.IN, Pin.PULL_UP)

    async def get_rbb(self) -> int:
        return self._rbb.value()

    async def init_pin(self) -> None:
        await self.set_io_dir(is_output=True)
        await self.set_ceb(None)
        await self.set_cle(0)
        await self.set_ale(0)
        await self.set_web(1)
        await self.set_reb(1)

    async def input_cmd(self, cmd: int) -> None:
        await self.set_io(cmd)
        await self.set_cle(1)
        await self.set_web(0)
        # await self.delay() # FWOHで十分遅いので無効
        await self.set_web(1)
        await self.set_cle(0)

    async def input_addrs(self, addrs: array.array) -> None:
        for addr in addrs:
            await self.set_io(addr)
            await self.set_ale(1)
            await self.set_web(0)
            # await self.delay() # FWOHで十分遅いので無効
            await self.set_web(1)
            await self.set_ale(0)

    async def input_addr(self, addr: int) -> None:
        addrs = array.array("B", [addr])
        await self.input_addrs(addrs)

    async def output_data(self, num_bytes: int) -> bytearray:
        datas = bytearray()
        await self.set_io_dir(is_output=False)
        for i in range(num_bytes):
            await self.set_reb(0)
            # await self.delay() # FWOHで十分遅いので無効
            datas.append(await self.get_io())
            await self.set_reb(1)
            # await self.delay() # FWOHで十分遅いので無効
        await self.set_io_dir(is_output=True)
        return datas

    async def wait_busy(self, timeout_ms: int) -> bool:
        start = utime.ticks_ms()
        while self.get_rbb() == 0:
            await uasyncio.sleep_ms(1)
            if utime.ticks_diff(utime.ticks_ms(), start) > timeout_ms:
                return False
        return True


class FwNandCommander:
    def __init__(
        self,
        nandio: NandIo,
        timeout_ms: int = 1000,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._nandio = nandio

    async def reset(self, chip_index: int) -> None:
        nandio = self._nandio

        await nandio.init_pin()
        await nandio.set_ceb(chip_index=chip_index)
        await nandio.input_cmd(NandCommandId.RESET)
        await nandio.set_ceb(None)

        # wait for RBB to be set
        is_ok = await nandio.wait_busy(timeout_ms=self._timeout_ms)
        if not is_ok:
            raise RuntimeError("NAND reset failed: RBB did not clear in time.")

    async def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        nandio = self._nandio

        await nandio.init_pin()
        await nandio.set_ceb(chip_index=chip_index)
        await nandio.input_cmd(NandCommandId.READ_ID)
        await nandio.input_addr(0)
        id = await nandio.output_data(num_bytes=num_bytes)
        await nandio.set_ceb(None)

        return id

    async def read_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        col: int = 0,
        num_bytes: int = NandConfig.PAGE_ALL_BYTES,
    ) -> bytearray | None:
        addrs = array.array("B", [0, 0, 0, 0])
        NandAddr.create_full_addr(addrs, col, page, block)

        nand = self._nandio
        await nand.init_pin()
        await nand.set_ceb(chip_index=chip_index)
        await nand.input_cmd(NandCommandId.READ_1ST)
        await nand.input_addrs(addrs)
        await nand.input_cmd(NandCommandId.READ_2ND)
        is_ok = await nand.wait_busy(timeout_ms=self._timeout_ms)
        if not is_ok:
            return None
        data = await nand.output_data(num_bytes=num_bytes)
        await nand.set_ceb(None)
        return data

    async def read_status(self, chip_index: int) -> int:
        nand = self._nandio

        await nand.init_pin()
        await nand.set_ceb(chip_index=chip_index)
        await nand.input_cmd(NandCommandId.STATUS_READ)
        status = await nand.output_data(num_bytes=1)
        await nand.set_ceb(None)
        return status[0]

    async def erase_block(self, chip_index: int, block: int) -> bool:
        addrs = array.array("B", [0, 0])
        NandAddr.create_block_addr(addrs, block)

        nand = self._nandio
        await nand.init_pin()
        await nand.set_ceb(chip_index=chip_index)
        await nand.input_cmd(NandCommandId.ERASE_1ST)
        await nand.input_addrs(addrs)
        await nand.input_cmd(NandCommandId.ERASE_2ND)
        is_ok = await nand.wait_busy(timeout_ms=self._timeout_ms)
        await nand.set_ceb(None)
        if not is_ok:
            return False

        status = await self.read_status(chip_index=chip_index)
        is_ok = (status & NandStatus.PROGRAM_ERASE_FAIL) == 0

        return is_ok

    async def program_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        data: bytearray,
        col: int = 0,
    ) -> bool:
        addrs = array.array("B", [0, 0, 0, 0])
        NandAddr.create_full_addr(addrs, col, page, block)

        nand = self._nandio
        await nand.init_pin()
        await nand.set_ceb(chip_index=chip_index)
        await nand.input_cmd(NandCommandId.PROGRAM_1ST)
        await nand.input_addrs(addrs)
        # Data Input
        for i in range(len(data)):
            await nand.set_io(data[i])
            await nand.set_web(0)
            await nand.delay()
            await nand.set_web(1)
        await nand.input_cmd(NandCommandId.PROGRAM_2ND)
        is_ok = await nand.wait_busy(timeout_ms=self._timeout_ms)
        await nand.set_ceb(None)
        if not is_ok:
            return False
        status = await self.read_status(chip_index=chip_index)
        is_ok = (status & NandStatus.PROGRAM_ERASE_FAIL) == 0

        return is_ok


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
        wait_ms: int = 1,
        timeout_ms: int = 5000,
        max_freq: int = 125_000_000,
    ) -> None:
        self._wait_ms = wait_ms
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
            # /RE=L (t_rr + t_rea = 40ns / 4cyc => 10ns = 100MHz)
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

    def _setup_tx_dma_word(
        self,
        dreq: int,
        sm: rp2.StateMachine,
        tx_payload: array.array,
        dma: rp2.DMA | None = None,
        chain_dma: rp2.DMA | None = None,
    ) -> rp2.DMA:
        """TX payload送信用DMAのセットアップ"""

        # Channel指定されていなければ新規確保
        if dma is None:
            dma = rp2.DMA()
        # chain先が指定されていたらそのDMAのchannel、指定がなければ自身(Chainしない)
        chain_to: int = dma.channel if chain_dma is None else chain_dma.channel  # type: ignore

        tx_dma0_ctrl = dma.pack_ctrl(
            size=2,  # 4byte転送
            inc_read=True,
            inc_write=False,  # tx_fifoは場所固定
            bswap=False,
            treq_sel=dreq,
            chain_to=chain_to,
        )
        dma.config(
            read=tx_payload,
            write=sm,
            count=len(tx_payload),
            ctrl=tx_dma0_ctrl,
            trigger=False,  # 自動開始しない
        )
        return dma

    def _setup_tx_dma_byte(
        self,
        dreq: int,
        sm: rp2.StateMachine,
        data: bytearray,
        dma: rp2.DMA | None = None,
        chain_dma: rp2.DMA | None = None,
    ) -> rp2.DMA:
        """TX data送信用DMAのセットアップ"""

        if dma is None:
            dma = rp2.DMA()
        # chain先が指定されていたらそのDMAのchannel、指定がなければ自身(Chainしない)
        chain_to: int = dma.channel if chain_dma is None else chain_dma.channel  # type: ignore

        tx_dma0_ctrl = dma.pack_ctrl(
            size=0,  # 1byte転送
            inc_read=True,
            inc_write=False,  # tx_fifoは場所固定
            bswap=False,
            treq_sel=dreq,
            chain_to=chain_to,
        )
        dma.config(
            read=data,
            write=sm,
            count=len(data),
            ctrl=tx_dma0_ctrl,
            trigger=False,  # 自動開始しない
        )
        return dma

    def _setup_rx_dma_byte(
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

    async def reset(self, chip_index: int) -> None:
        sm0 = self._setup_pio0_nandio()
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_reset(tx_payload, cs=chip_index)  # w/ wait RBB
        tx_dma0 = self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )
        tx_dma0.active(1)

        # wait after RESET
        await uasyncio.sleep_ms(100)

        sm0.active(0)
        tx_dma0.close()

    async def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        sm0 = self._setup_pio0_nandio()
        complete = False

        def set_complete(_):
            nonlocal complete
            complete = True

        sm0.irq(set_complete)
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_read_id(tx_payload, cs=chip_index, data_count=num_bytes)
        tx_dma0 = self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )

        # RX Data
        rx_data = bytearray(num_bytes)
        rx_dma0 = self._setup_rx_dma_byte(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )

        # Start DMA
        rx_dma0.active(1)
        tx_dma0.active(1)
        while rx_dma0.active():
            await uasyncio.sleep_ms(self._wait_ms)

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

        complete = False

        def set_complete(_):
            nonlocal complete
            complete = True

        sm0.irq(set_complete)
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
        tx_dma0 = self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )

        # RX Data
        rx_data = bytearray(num_bytes)
        rx_dma0 = self._setup_rx_dma_byte(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=num_bytes
        )

        # start DMA
        rx_dma0.active(1)
        tx_dma0.active(1)
        while rx_dma0.active():
            await uasyncio.sleep_ms(self._wait_ms)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()
        return rx_data

    async def read_status(self, chip_index: int) -> int:
        sm0 = self._setup_pio0_nandio()
        complete = False

        def set_complete(_):
            nonlocal complete
            complete = True

        sm0.irq(set_complete)
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_status_read(tx_payload, cs=chip_index)
        tx_dma0 = self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )

        # RX Data
        rx_data = bytearray(1)
        rx_dma0 = self._setup_rx_dma_byte(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )

        # start DMA
        rx_dma0.active(1)
        tx_dma0.active(1)
        while rx_dma0.active():
            await uasyncio.sleep_ms(self._wait_ms)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()
        return rx_data[0]

    async def erase_block(self, chip_index: int, block: int) -> bool:
        sm0 = self._setup_pio0_nandio()
        complete = False

        def set_complete(_):
            nonlocal complete
            complete = True

        sm0.irq(set_complete)
        sm0.active(1)

        # TX Payload
        tx_payload = array.array("I")
        PioCmdBuilder.seq_erase(tx_payload, cs=chip_index, block_addr=block)
        PioCmdBuilder.seq_status_read(tx_payload, cs=chip_index)
        tx_dma0 = self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX, sm=sm0, tx_payload=tx_payload
        )

        # RX Data
        rx_data = bytearray(1)
        rx_dma0 = self._setup_rx_dma_byte(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )

        # start DMA
        rx_dma0.active(1)
        tx_dma0.active(1)
        while rx_dma0.active():
            await uasyncio.sleep_ms(self._wait_ms)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        rx_dma0.close()

        is_ok = (rx_data[0] & NandStatus.PROGRAM_ERASE_FAIL) == 0
        return is_ok

    async def program_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        data: bytearray,
        col: int = 0,
    ) -> bool:
        # for NAND IO
        sm0 = self._setup_pio0_nandio()
        complete = False

        def set_complete(_):
            nonlocal complete
            complete = True

        sm0.irq(set_complete)
        sm0.active(1)

        async def _create_payload0() -> array.array:
            tx_payload0 = array.array("I")
            PioCmdBuilder.init_pin(tx_payload0)
            PioCmdBuilder.assert_cs(tx_payload0, cs=chip_index)
            PioCmdBuilder.cmd_latch(
                tx_payload0, cmd=NandCommandId.PROGRAM_1ST, cs=chip_index
            )
            PioCmdBuilder.full_addr_latch(
                tx_payload0,
                column_addr=col,
                page_addr=page,
                block_addr=block,
                cs=chip_index,
            )
            PioCmdBuilder.data_input_only_header(tx_payload0, len(data))
            return tx_payload0

        async def _create_payload1(
            self, chip_index: int, data: bytearray
        ) -> array.array:
            sm4 = self._setup_pio1_merge_cs()
            sm4.active(1)

            # CEB[1:0] に設定する値を合成するPIO
            bitor_data = 0xFFFFFFFF & ~(1 << chip_index)
            sm4.put(bitor_data)

            tx_dma0 = self._setup_tx_dma_byte(dreq=Dreq.PIO1_SM0_TX, sm=sm4, data=data)
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
            while rx_dma0.active():
                await uasyncio.sleep_ms(self._wait_ms)

            return rx_data

        async def _create_payload2() -> array.array:
            tx_payload2 = array.array("I")
            PioCmdBuilder.cmd_latch(
                tx_payload2, cmd=NandCommandId.PROGRAM_2ND, cs=chip_index
            )
            PioCmdBuilder.wait_rbb(tx_payload2)
            PioCmdBuilder.cmd_latch(
                tx_payload2, cmd=NandCommandId.STATUS_READ, cs=chip_index
            )
            PioCmdBuilder.data_output(tx_payload2, data_count=1)
            PioCmdBuilder.deassert_cs(tx_payload2)
            return tx_payload2

        tx_payload0, tx_payload1, tx_payload2 = await uasyncio.gather(
            _create_payload0(),
            _create_payload1(self, chip_index, data),
            _create_payload2(),
        )

        # TX PayloadのChain用に事前確保
        tx_dma0 = rp2.DMA()
        tx_dma1 = rp2.DMA()
        tx_dma2 = rp2.DMA()

        self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX,
            sm=sm0,
            tx_payload=tx_payload0,
            dma=tx_dma0,
            chain_dma=tx_dma1,
        )
        self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX,
            sm=sm0,
            tx_payload=tx_payload1,
            dma=tx_dma1,
            chain_dma=tx_dma2,
        )
        self._setup_tx_dma_word(
            dreq=Dreq.PIO0_SM0_TX,
            sm=sm0,
            tx_payload=tx_payload2,
            dma=tx_dma2,
        )

        # RX Data (Status Read Response)
        rx_data = bytearray(1)
        rx_dma0 = self._setup_rx_dma_byte(
            dreq=Dreq.PIO0_SM0_RX, sm=sm0, rx_data=rx_data, num_bytes=1
        )

        # Start DMA
        rx_dma0.active(1)
        tx_dma0.active(1)
        while rx_dma0.active():
            await uasyncio.sleep_ms(self._wait_ms)

        # finalize
        sm0.active(0)
        tx_dma0.close()
        tx_dma1.close()
        tx_dma2.close()
        rx_dma0.close()

        is_ok = (rx_data[0] & NandStatus.PROGRAM_ERASE_FAIL) == 0
        return is_ok
