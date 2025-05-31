import array
import time

from sim.nandio_pio import (
    NandConfig,
    NandAddr,
    NandCommandId,
    NandStatus,
    PinAssign,
    PioCmdBuilder,
)
import nandio as nandio_pio

from machine import Pin
import rp2


class NandIo:
    def __init__(
        self,
        delay_us: int = 0,
        keep_wp: bool = True,
    ) -> None:
        self._delay_us = delay_us
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

    def delay(self) -> None:
        time.sleep_us(self._delay_us)

    ########################################################
    # Low-level functions
    ########################################################

    def set_io(self, value: int) -> None:
        for i in range(8):
            self._io[i].value((value >> i) & 0x1)

    def get_io(self) -> int:
        value = 0
        for i in range(8):
            value |= self._io[i].value() << i
        return value

    def set_io_dir(self, is_output: bool) -> None:
        for pin in self._io:
            pin.init(Pin.OUT if is_output else Pin.IN)

    def set_ceb(self, chip_index: int | None) -> None:
        # status indicator
        self._led.toggle()

        assert chip_index is None or chip_index in [0, 1]
        if chip_index is None:
            self._ceb0.on()
            self._ceb1.on()
        else:
            self._ceb0.value(0 if chip_index == 0 else 1)
            self._ceb1.value(0 if chip_index == 1 else 1)

    def set_cle(self, value: int) -> None:
        self._cle.value(value)

    def set_ale(self, value: int) -> None:
        self._ale.value(value)

    def set_web(self, value: int) -> None:
        self._web.value(value)

    def set_wpb(self, value: int) -> None:
        self._wpb.value(value)
        time.sleep_us(100)

    def set_reb(self, value: int) -> None:
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

    def get_rbb(self) -> int:
        return self._rbb.value()

    def init_pin(self) -> None:
        self.set_io_dir(is_output=True)
        self.set_ceb(None)
        self.set_cle(0)
        self.set_ale(0)
        self.set_web(1)
        self.set_reb(1)

    def input_cmd(self, cmd: int) -> None:
        self.set_io(cmd)
        self.set_cle(1)
        self.set_web(0)
        self.delay()
        self.set_web(1)
        self.set_cle(0)

    def input_addrs(self, addrs: array.array) -> None:
        for addr in addrs:
            self.set_io(addr)
            self.set_ale(1)
            self.set_web(0)
            self.delay()
            self.set_web(1)
            self.set_ale(0)

    def input_addr(self, addr: int) -> None:
        addrs = array.array("B", [addr])
        self.input_addrs(addrs)

    def output_data(self, num_bytes: int) -> bytearray:
        datas = bytearray()
        self.set_io_dir(is_output=False)
        for i in range(num_bytes):
            self.set_reb(0)
            self.delay()
            datas.append(self.get_io())
            self.set_reb(1)
            self.delay()
        self.set_io_dir(is_output=True)
        return datas

    def wait_busy(self, timeout_ms: int) -> bool:
        start = time.ticks_ms()
        while self.get_rbb() == 0:
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
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

    ########################################################
    # Communication functions
    ########################################################
    def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        nandio = self._nandio

        # initialize
        nandio.init_pin()
        # CS select
        nandio.set_ceb(chip_index=chip_index)
        # Command Input
        nandio.input_cmd(NandCommandId.READ_ID)
        # Address Input
        nandio.input_addr(0)
        # ID Read
        id = nandio.output_data(num_bytes=num_bytes)
        # CS deselect
        nandio.set_ceb(None)

        return id

    def read_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        col: int = 0,
        num_bytes: int = NandConfig.PAGE_ALL_BYTES,
    ) -> bytearray | None:
        nand = self._nandio
        # initialize
        nand.init_pin()
        # CS select
        nand.set_ceb(chip_index=chip_index)
        # 1st Command Input
        nand.input_cmd(NandCommandId.READ_1ST)
        # Address Input
        addrs = array.array("B", [0, 0, 0, 0])
        NandAddr.create_full_addr(addrs, col, page, block)
        nand.input_addrs(addrs)
        # 2nd Command Input
        nand.input_cmd(NandCommandId.READ_2ND)
        # Wait Busy
        is_ok = nand.wait_busy(timeout_ms=self._timeout_ms)
        if not is_ok:
            return None
        # Data Read
        data = nand.output_data(num_bytes=num_bytes)
        # CS deassert
        nand.set_ceb(None)
        return data

    def read_status(self, chip_index: int) -> int:
        nand = self._nandio
        # initialize
        nand.init_pin()
        # CS select
        nand.set_ceb(chip_index=chip_index)
        # Command Input
        nand.input_cmd(NandCommandId.STATUS_READ)
        # Status Read
        status = nand.output_data(num_bytes=1)
        # CS deselect
        nand.set_ceb(None)
        return status[0]

    def erase_block(self, chip_index: int, block: int) -> bool:
        nand = self._nandio
        # initialize
        nand.init_pin()
        # CS select
        nand.set_ceb(chip_index=chip_index)
        # 1st Command Input
        nand.input_cmd(NandCommandId.ERASE_1ST)
        # Address Input
        addrs = array.array("B", [0, 0])
        NandAddr.create_block_addr(addrs, block)
        nand.input_addrs(addrs)
        # 2nd Command Input
        nand.input_cmd(NandCommandId.ERASE_2ND)
        # Wait Busy
        is_ok = nand.wait_busy(timeout_ms=self._timeout_ms)
        # CS deassert
        nand.set_ceb(None)

        if not is_ok:
            return False

        # status read (erase result)
        status = self.read_status(chip_index=chip_index)
        is_ok = (status & NandStatus.PROGRAM_ERASE_FAIL) == 0

        return is_ok

    def program_page(
        self,
        chip_index: int,
        block: int,
        page: int,
        data: bytearray,
        col: int = 0,
    ) -> bool:
        nand = self._nandio
        # initialize
        nand.init_pin()
        # CS select
        nand.set_ceb(chip_index=chip_index)
        # 1st Command Input
        nand.input_cmd(NandCommandId.PROGRAM_1ST)
        # Address Input
        addrs = array.array("B", [0, 0, 0, 0])
        NandAddr.create_full_addr(addrs, col, page, block)
        nand.input_addrs(addrs)
        # Data Input
        for i in range(len(data)):
            nand.set_io(data[i])
            nand.set_web(0)
            nand.delay()
            nand.set_web(1)
        # 2nd Command Input
        nand.input_cmd(NandCommandId.PROGRAM_2ND)
        # Wait Busy
        is_ok = nand.wait_busy(timeout_ms=self._timeout_ms)
        # CS deassert
        nand.set_ceb(None)
        if not is_ok:
            return False

        # status read (program result)
        status = self.read_status(chip_index=chip_index)
        is_ok = (status & NandStatus.PROGRAM_ERASE_FAIL) == 0

        return is_ok


class PioNandCommander:
    def __init__(
        self,
        nandio: NandIo,
        timeout_ms: int = 1000,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._nandio = nandio

    def read_id(self, chip_index: int, num_bytes: int = 5) -> bytearray:
        required_freq = int(83e6)  # TODO: これ以下にしておく
        sm = rp2.StateMachine(0)
        sm.init(
            prog=nandio_pio.PIO_OPCODES,
            freq=-1,  # TODO: 疎通できたら姑息可
            in_base=self._nandio._io0,
            out_base=self._nandio._io0,
            set_base=self._nandio._io0,
            jmp_pin=None,
            sideset_base=self._nandio._cle,  # [REB,WEB,WPB,ALE,CLE]
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

        pass

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
