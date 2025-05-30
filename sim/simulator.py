import array
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
from collections import deque
import itertools
import adafruit_pioasm
import pioemu
import wavedrom
import svgwrite


class Util:
    @staticmethod
    def to_hex_u32(x: int) -> str:
        """32bit符号なし整数を16進数文字列に変換する"""
        return f"0x{(x & 0xFFFFFFFF):08X}"

    @classmethod
    def to_hex_str_arr(cls, src: List[int]) -> List[str]:
        return [cls.to_hex_u32(x) for x in src]

    @staticmethod
    def to_wavedrom_signal(
        df: pd.DataFrame,
        col: str,
        replace_f: Optional[Callable[[Any, Any], Any]] = None,
    ) -> Dict[str, Any]:
        """DataFrameの列をWavedromの信号に変換する"""
        src = df[col].map(lambda x: "1" if x else "0").to_list()
        dst_wave = []

        prev_data = None
        for entry in src:
            # 差し替え関数あるなら任せる
            if replace_f is not None:
                dst_wave.append(replace_f(prev_data, entry))
            elif prev_data == entry:
                dst_wave.append(".")
            else:
                dst_wave.append(entry)
            # 一つ前のデータを保存
            prev_data = entry
        return {"name": col, "wave": "".join(dst_wave)}

    @staticmethod
    def to_wavedrom_data(df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """DataFrameの列をWavedromの信号に変換する"""
        src = df[col].to_list()
        dst_wave = []
        dst_data = []

        prev_data = None
        for entry in src:
            # Noneのときは最初から一致してしまう
            if entry is None:
                dst_wave.append("x")
            elif prev_data == entry:
                dst_wave.append(".")
            else:
                dst_wave.append("=")
                dst_data.append(
                    hex(
                        int(entry, 16),
                    ).replace("0x", "")
                    if isinstance(entry, str)
                    else entry
                )  # 長いので縮める, str|intの場合分け
            # 一つ前のデータを保存
            prev_data = entry
        return {"name": col, "wave": "".join(dst_wave), "data": dst_data}


@dataclass
class Result:
    """PIOのエミュレーション結果を格納するクラス"""

    program_str: str
    test_cycles: int
    states_df: pd.DataFrame
    event_df: pd.DataFrame
    received_from_rx_fifo: List[int]
    tx_fifo: List[int]
    rx_fifo: List[int]
    wavedrom_src: str
    wave_svg: svgwrite.drawing.Drawing

    def save(self, dst_path: Path) -> None:
        """結果を指定されたパスに保存する"""

        dst_path.mkdir(exist_ok=True)

        # 各種データを保存
        (dst_path / "program.txt").write_text(self.program_str, encoding="utf-8")
        (dst_path / "tx_fifo.json").write_text(
            json.dumps(self.tx_fifo), encoding="utf-8"
        )
        (dst_path / "rx_fifo.json").write_text(
            json.dumps(self.rx_fifo), encoding="utf-8"
        )
        (dst_path / "received_from_rx_fifo.json").write_text(
            json.dumps(self.received_from_rx_fifo), encoding="utf-8"
        )
        Path(dst_path / "wave.json").write_text(self.wavedrom_src)
        self.states_df.to_csv(dst_path / "states.csv")
        self.event_df.to_csv(dst_path / "event.csv")
        self.states_df.to_json(dst_path / "states.json", orient="records")
        self.event_df.to_json(dst_path / "event.json", orient="records")
        self.wave_svg.saveas(dst_path / "wave.svg")


class Simulator:
    @staticmethod
    def __analyze_steps(states_df: pd.DataFrame, opcodes: array.array) -> None:
        def get_insert_idx() -> int:
            """DataFrameに新しい列を挿入するためのインデックスを返す"""

            dst = get_insert_idx.insert_idx  # increment前を返す
            get_insert_idx.insert_idx += 1
            return dst

        get_insert_idx.insert_idx = 0

        states_df.insert(
            get_insert_idx(),
            "cyc",
            states_df["clock"],
        )
        states_df.insert(
            get_insert_idx(),
            "pc",
            states_df["program_counter"],
        )
        states_df.insert(
            get_insert_idx(),
            "inst",
            states_df["pc"].map(lambda pc: Util.to_hex_u32(opcodes[pc])),
        )
        states_df.insert(
            get_insert_idx(), "x", states_df["x_register"].map(Util.to_hex_u32)
        )
        states_df.insert(
            get_insert_idx(), "y", states_df["y_register"].map(Util.to_hex_u32)
        )
        states_df.insert(
            get_insert_idx(),
            "isr",
            states_df["input_shift_register"].map(
                lambda sr: Util.to_hex_u32(sr.contents)
            ),
        )
        states_df.insert(
            get_insert_idx(),
            "osr",
            states_df["output_shift_register"].map(
                lambda sr: Util.to_hex_u32(sr.contents)
            ),
        )
        states_df.insert(
            get_insert_idx(),
            "pindirs",
            states_df["pin_directions"].map(Util.to_hex_u32),
        )
        states_df.insert(
            get_insert_idx(), "pins", states_df["pin_values"].map(Util.to_hex_u32)
        )
        states_df.insert(
            get_insert_idx(),
            "io",
            states_df["pin_values"].map(
                lambda data: Util.to_hex_u32((data & 0x000000FF))
            ),
        )
        states_df.insert(
            get_insert_idx(),
            "io_dir",
            states_df["pin_directions"].map(
                lambda data: Util.to_hex_u32((data & 0x000000FF))
            ),
        )

        signals: List[(str, int)] = [
            ("ceb0", 8),
            ("ceb1", 9),
            ("cle", 10),
            ("ale", 11),
            ("wpb", 12),
            ("web", 13),
            ("reb", 14),
            ("rbb", 15),
        ]
        for signal, bit_pos in signals:
            states_df.insert(
                get_insert_idx(),
                signal,
                states_df["pin_values"].map(lambda data: (data >> bit_pos) & 0x01),
            )

        states_df.insert(
            get_insert_idx(),
            "txfifo_head",
            states_df["transmit_fifo"].map(
                lambda data: Util.to_hex_u32(data[0]) if len(data) > 0 else None
            ),
        )
        states_df.insert(
            get_insert_idx(),
            "txfifo_remain",
            states_df["transmit_fifo"].map(lambda data: len(data)),
        )
        states_df.insert(
            get_insert_idx(),
            "rxfifo_tail",
            states_df["receive_fifo"].map(
                lambda data: Util.to_hex_u32(data[-1]) if len(data) > 0 else None
            ),
        )
        states_df.insert(
            get_insert_idx(),
            "rxfifo_remain",
            states_df["receive_fifo"].map(lambda data: len(data)),
        )

        # シーケンス解析
        states_df["cs_assert"] = (states_df["ceb0"] == 0) | (states_df["ceb1"] == 0)
        # riseでNAND ICでキャプチャ想定
        states_df["web_edge"] = (states_df["web"] == 1) & (
            states_df.shift(1)["web"] == 0
        )
        # fallでICから出力、(t_rea遅れて) riseでPIOでキャプチャ想定。両方用意する
        states_df["reb_edge_nand"] = (states_df["reb"] == 0) & (
            states_df.shift(1)["reb"] == 1
        )
        states_df["reb_edge_pio"] = (states_df["reb"] == 1) & (
            states_df.shift(1)["reb"] == 0
        )
        states_df["reb_edge"] = states_df["reb_edge_pio"]

        states_df.insert(
            get_insert_idx(),
            "cmd_in",
            states_df["web_edge"]
            & states_df["cs_assert"]
            & (states_df["reb"] == 1)
            & (states_df["cle"] == 1)
            & (states_df["ale"] == 0),
        )
        states_df.insert(
            get_insert_idx(),
            "addr_in",
            states_df["web_edge"]
            & states_df["cs_assert"]
            & (states_df["reb"] == 1)
            & (states_df["cle"] == 0)
            & (states_df["ale"] == 1),
        )
        states_df.insert(
            get_insert_idx(),
            "data_in",
            states_df["web_edge"]
            & states_df["cs_assert"]
            & (states_df["reb"] == 1)
            & (states_df["cle"] == 0)
            & (states_df["ale"] == 0),
        )
        states_df.insert(
            get_insert_idx(),
            "data_out",
            states_df["reb_edge"]
            & states_df["cs_assert"]
            & (states_df["web"] == 1)
            & (states_df["cle"] == 0)
            & (states_df["ale"] == 0),
        )

    @staticmethod
    def __extract_events(states_df: pd.DataFrame) -> pd.DataFrame:
        """DataFrameからイベントを抽出して新しいDataFrameを返す"""
        event_src = []
        for _, row in states_df.iterrows():
            event_type = None
            if row["cmd_in"]:
                event_type = "cmd_in"
            elif row["addr_in"]:
                event_type = "addr_in"
            elif row["data_in"]:
                event_type = "data_in"
            elif row["data_out"]:
                event_type = "data_out"
            else:
                continue
            event_src.append(
                {
                    "cycle": row["cyc"],
                    "pc": row["pc"],
                    "event": event_type,
                    "ceb0": row["ceb0"],
                    "ceb1": row["ceb1"],
                    "io": row["io"],
                    "io_dir": row["io_dir"],
                    # for testing
                    "io_raw": int(row["io"], 16),
                    "io_dir_raw": int(row["io_dir"], 16),
                }
            )
        event_df = pd.DataFrame.from_records(event_src)
        return event_df

    @staticmethod
    def __to_wavedrom(states_df: pd.DataFrame) -> object:
        """DataFrameからWavedromの信号定義を生成する"""
        return {
            "signal": [
                [
                    "pio",
                    [
                        "ctrl",
                        Util.to_wavedrom_data(states_df, "cyc"),
                        Util.to_wavedrom_data(states_df, "pc"),
                        Util.to_wavedrom_data(states_df, "inst"),
                        [
                            "fifo",
                            [
                                "tx",
                                Util.to_wavedrom_data(states_df, "txfifo_head"),
                                Util.to_wavedrom_data(states_df, "txfifo_remain"),
                            ],
                            [
                                "rx",
                                Util.to_wavedrom_data(states_df, "rxfifo_tail"),
                                Util.to_wavedrom_data(states_df, "rxfifo_remain"),
                            ],
                        ],
                    ],
                    {},
                    [
                        "regs",
                        [
                            "scratch",
                            Util.to_wavedrom_data(states_df, "x"),
                            Util.to_wavedrom_data(states_df, "y"),
                        ],
                        [
                            "fifo",
                            Util.to_wavedrom_data(states_df, "isr"),
                            Util.to_wavedrom_data(states_df, "osr"),
                        ],
                        [
                            "pinout",
                            Util.to_wavedrom_data(states_df, "pindirs"),
                            Util.to_wavedrom_data(states_df, "pins"),
                        ],
                    ],
                ],
                {},
                [
                    "nand",
                    [
                        "out",
                        [
                            "cs",
                            Util.to_wavedrom_signal(states_df, "ceb0"),
                            Util.to_wavedrom_signal(states_df, "ceb1"),
                        ],
                        [
                            "latch",
                            Util.to_wavedrom_signal(states_df, "cle"),
                            Util.to_wavedrom_signal(states_df, "ale"),
                        ],
                        [
                            "edge",
                            Util.to_wavedrom_signal(states_df, "web"),
                            Util.to_wavedrom_signal(states_df, "reb"),
                        ],
                        Util.to_wavedrom_signal(states_df, "wpb"),
                    ],
                    {},
                    [
                        "inout",
                        Util.to_wavedrom_data(states_df, "io"),
                        Util.to_wavedrom_data(states_df, "io_dir"),
                    ],
                    {},
                    [
                        "in",
                        Util.to_wavedrom_signal(states_df, "rbb"),
                    ],
                    {},
                    [
                        "analysis",
                        [
                            "src",
                            Util.to_wavedrom_signal(states_df, "cs_assert"),
                            Util.to_wavedrom_signal(states_df, "web_edge"),
                            Util.to_wavedrom_signal(states_df, "reb_edge"),
                        ],
                        [
                            "event",
                            Util.to_wavedrom_signal(states_df, "cmd_in"),
                            Util.to_wavedrom_signal(states_df, "addr_in"),
                            Util.to_wavedrom_signal(states_df, "data_in"),
                            Util.to_wavedrom_signal(states_df, "data_out"),
                        ],
                    ],
                ],
            ]
        }

    @staticmethod
    def __example_input_source(clock: int) -> int:
        """検証用な適当な入力を生成する"""
        return ((clock // 2) & 0xFF) | (0x8000 if (((clock // 8) % 2) == 1) else 0x0000)

    @classmethod
    def execute(
        cls,
        program_str: str,
        test_cycles: int,
        tx_fifo_entries: List[int] | array.array = [],
        # dequeue が速すぎると、simulator上のFIFOが常に空になってしまう
        dequeue_period_cyc: int = 6,
        input_source: Callable[[pioemu.State], int]
        | Callable[[int], int]
        | None = None,
    ) -> Result:
        """PIOのsimulationを行う"""

        # tx_fifo_entries が array.array の場合は List[int] に変換
        if isinstance(tx_fifo_entries, array.array):
            tx_fifo_entries = list(tx_fifo_entries)

        # pio textをアセンブルして、opcodesを生成
        opcodes: array.array = adafruit_pioasm.assemble(program_str)
        # emulatorセットアップ
        emu_generator = pioemu.emulate(
            opcodes=opcodes,
            stop_when=lambda _, state: state.clock > test_cycles,
            input_source=cls.__example_input_source
            if input_source is None
            else input_source,
            initial_state=pioemu.State(
                clock=0,
                program_counter=0,
                transmit_fifo=deque(tx_fifo_entries),
                receive_fifo=deque([]),
                x_register=0,
                y_register=0,
            ),
            shift_isr_right=False,
            shift_osr_right=True,
            side_set_count=5,
            side_set_base=10,
            auto_push=True,
            push_threshold=8,
        )

        # stepを進め、pinの状態, fifoの状態を収集
        run_states: List[Any] = []
        received_data: List[int] = []
        dma_dequeue_ready_cnt = 0  # dequeue_period_cycより大きければDequeue可能
        for before, after in itertools.islice(emu_generator, test_cycles):
            run_states.append(after.__dict__)
            # dequeue
            dma_dequeue_ready_cnt += 1
            if (dma_dequeue_ready_cnt > dequeue_period_cyc) and (
                len(before.receive_fifo) > 0
            ):
                received_data.append(after.receive_fifo.popleft())
                dma_dequeue_ready_cnt = 0

        # 各stepで収集したstateをDataFrameに変換
        states_df = pd.DataFrame.from_records(run_states)
        # 最終stepのrxfifoの状態を抽出
        rx_fifo = list(states_df[-1:]["receive_fifo"].values[0])
        # 各stepの情報をparseし、信号の情報を抽出
        cls.__analyze_steps(states_df, opcodes)
        # イベントだけを抽出しておく
        event_df = cls.__extract_events(states_df)
        # wavedrom向けobjectに変換し、SVGに変換
        wavedrom_src = json.dumps(cls.__to_wavedrom(states_df), indent=2)
        wave_svg = wavedrom.render(wavedrom_src)

        return Result(
            program_str=program_str,
            test_cycles=test_cycles,
            tx_fifo=tx_fifo_entries,
            states_df=states_df,
            event_df=event_df,
            rx_fifo=rx_fifo,
            received_from_rx_fifo=received_data,
            wavedrom_src=wavedrom_src,
            wave_svg=wave_svg,
        )
