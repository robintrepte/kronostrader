from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "kronos"
if _VENDOR.exists() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


class ModelNotReadyError(RuntimeError):
    pass


class KronosEngine:
    def __init__(self) -> None:
        self.predictor: Any = None
        self.model_id: str = ""
        self.tokenizer_id: str = ""
        self.device: str = "cpu"
        self.max_context: int = 512
        self.loaded: bool = False

    def load(
        self,
        model_id: str,
        tokenizer_id: str,
        device: str,
        max_context: int,
    ) -> None:
        try:
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Kronos vendor not found. Run: git submodule update --init "
                "apps/inference/vendor/kronos"
            ) from exc

        logger.info(
            "Loading Kronos",
            extra={"model": model_id, "tokenizer": tokenizer_id, "device": device},
        )
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)
        model = Kronos.from_pretrained(model_id)
        self.predictor = KronosPredictor(
            model, tokenizer, device=device, max_context=max_context
        )
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id
        self.device = getattr(self.predictor, "device", device)
        self.max_context = max_context
        self.loaded = True
        logger.info("Kronos loaded", extra={"device": self.device})

    def predict(
        self,
        bars: list[dict[str, Any]],
        pred_len: int,
        pred_timestamps: Optional[list[pd.Timestamp]],
        temperature: float,
        top_p: float,
        sample_count: int,
    ) -> list[dict[str, Any]]:
        if not self.loaded or self.predictor is None:
            raise ModelNotReadyError("Model not loaded")

        hist = pd.DataFrame(bars)
        hist["timestamp"] = pd.to_datetime(hist["timestamp"], utc=True)
        hist = hist.sort_values("timestamp").tail(self.max_context).reset_index(drop=True)

        cols = ["open", "high", "low", "close", "volume"]
        if "amount" in hist.columns and hist["amount"].notna().any():
            x_df = hist[cols + ["amount"]].copy()
        else:
            x_df = hist[cols].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(
                axis=1
            )

        x_ts = hist["timestamp"]
        if pred_timestamps is None or len(pred_timestamps) != pred_len:
            # Infer bar frequency from last two timestamps
            if len(x_ts) >= 2:
                delta = x_ts.iloc[-1] - x_ts.iloc[-2]
            else:
                delta = pd.Timedelta(minutes=5)
            y_ts = pd.Series(
                [x_ts.iloc[-1] + delta * (i + 1) for i in range(pred_len)]
            )
        else:
            y_ts = pd.to_datetime(pd.Series(pred_timestamps), utc=True)

        runs: list[pd.DataFrame] = []
        for _ in range(sample_count):
            pred_df = self.predictor.predict(
                df=x_df,
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=1,
                verbose=False,
            )
            runs.append(pred_df)

        mean_df = runs[0].copy()
        if sample_count > 1:
            stacked = np.stack([r["close"].to_numpy() for r in runs], axis=0)
            mean_close = stacked.mean(axis=0)
            std_close = stacked.std(axis=0)
            mean_df["close"] = mean_close
            mean_df["close_low"] = mean_close - std_close
            mean_df["close_high"] = mean_close + std_close
            for col in ("open", "high", "low", "volume", "amount"):
                if col in mean_df.columns:
                    mean_df[col] = np.stack([r[col].to_numpy() for r in runs], axis=0).mean(
                        axis=0
                    )

        out: list[dict[str, Any]] = []
        reset = mean_df.reset_index()
        ts_col = "index" if "index" in reset.columns else reset.columns[0]
        for _, row in reset.iterrows():
            point = {
                "timestamp": pd.Timestamp(row[ts_col]).isoformat(),
                "open": float(row.get("open", row["close"])),
                "high": float(row.get("high", row["close"])),
                "low": float(row.get("low", row["close"])),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0) or 0.0),
                "amount": float(row.get("amount", 0.0) or 0.0),
            }
            if "close_low" in mean_df.columns:
                point["close_low"] = float(row["close_low"])
                point["close_high"] = float(row["close_high"])
            out.append(point)
        return out


engine = KronosEngine()
