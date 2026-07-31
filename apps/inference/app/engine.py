from __future__ import annotations

import inspect
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, Type

import numpy as np
import pandas as pd
import torch

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parents[1]
_VENDOR = _APP_ROOT / "vendor" / "kronos"
_CONFIGS = _APP_ROOT / "configs"
_LOCAL_MODELS = _APP_ROOT / "models"

if _VENDOR.exists() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


class ModelNotReadyError(RuntimeError):
    pass


def _repo_slug(repo_id: str) -> str:
    return repo_id.replace("/", "_")


def _local_model_dir(repo_id: str) -> Path | None:
    """Prefer apps/inference/models/<name> if weights exist."""
    name = repo_id.split("/")[-1]
    candidate = _LOCAL_MODELS / name
    if (candidate / "model.safetensors").is_file() or (candidate / "pytorch_model.bin").is_file():
        return candidate
    return None


def _bundled_config_path(repo_id: str) -> Path | None:
    path = _CONFIGS / f"{_repo_slug(repo_id)}.json"
    return path if path.is_file() else None


def _download_with_retries(repo_id: str, filename: str, retries: int = 5) -> str:
    from huggingface_hub import hf_hub_download

    # Help Windows TLS interception / flaky Hub connections
    os.environ.setdefault("HF_HUB_DISABLE_EXPERIMENTAL_WARNING", "1")
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return hf_hub_download(repo_id=repo_id, filename=filename)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = min(2**attempt, 20)
            logger.warning(
                "HF download failed (%s/%s) %s/%s: %s — retry in %ss",
                attempt,
                retries,
                repo_id,
                filename,
                exc,
                wait,
            )
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _load_config(repo_id: str, local_dir: Path | None = None) -> dict[str, Any]:
    if local_dir is not None:
        local_cfg = local_dir / "config.json"
        if local_cfg.is_file():
            with open(local_cfg, encoding="utf-8") as f:
                return json.load(f)

    bundled = _bundled_config_path(repo_id)
    if bundled is not None:
        logger.info("Using bundled config %s", bundled.name)
        with open(bundled, encoding="utf-8") as f:
            return json.load(f)

    path = _download_with_retries(repo_id, "config.json")
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict) or not config:
        raise RuntimeError(f"Empty config for {repo_id}")
    return config


def _init_kwargs(cls: Type, config: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if name in config:
            kwargs[name] = config[name]
        elif param.default is inspect.Parameter.empty:
            missing.append(name)
    if missing:
        raise RuntimeError(
            f"{cls.__name__} config missing required keys {missing}. "
            f"Available: {sorted(config.keys())}"
        )
    return kwargs


def _load_state_dict(path: Path, map_location: str) -> dict[str, Any]:
    if path.suffix == ".safetensors" or path.name.endswith(".safetensors"):
        from safetensors.torch import load_file

        return load_file(str(path), device=map_location)
    return torch.load(str(path), map_location=map_location, weights_only=True)


def load_hub_model(cls: Type, repo_id: str, map_location: str = "cpu") -> Any:
    """
    Robust replacement for PyTorchModelHubMixin.from_pretrained.

    Hugging Face's mixin silently continues when config.json is missing, which
    causes: TypeError missing 16 required positional arguments (Kronos #240).
    """
    local_dir = _local_model_dir(repo_id)
    config = _load_config(repo_id, local_dir=local_dir)
    kwargs = _init_kwargs(cls, config)
    model = cls(**kwargs)

    if local_dir is not None:
        weights = local_dir / "model.safetensors"
        if not weights.is_file():
            weights = local_dir / "pytorch_model.bin"
        logger.info("Loading weights from local dir %s", local_dir)
        state = _load_state_dict(weights, map_location)
    else:
        try:
            weights_path = Path(_download_with_retries(repo_id, "model.safetensors"))
        except Exception:
            weights_path = Path(_download_with_retries(repo_id, "pytorch_model.bin"))
        state = _load_state_dict(weights_path, map_location)

    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        logger.warning("Missing weights for %s: %s", repo_id, missing[:8])
    if unexpected:
        logger.warning("Unexpected weights for %s: %s", repo_id, unexpected[:8])
    model.eval()
    return model


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

        # Prefer local models downloaded via scripts/download-kronos.ps1
        if _local_model_dir(tokenizer_id) is None or _local_model_dir(model_id) is None:
            logger.warning(
                "Local Kronos weights not found under %s. "
                "If Hub download fails, run: .\\scripts\\download-kronos.ps1 -Model base",
                _LOCAL_MODELS,
            )

        tokenizer = load_hub_model(KronosTokenizer, tokenizer_id, map_location="cpu")
        model = load_hub_model(Kronos, model_id, map_location="cpu")
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
                    mean_df[col] = np.stack(
                        [r[col].to_numpy() for r in runs], axis=0
                    ).mean(axis=0)

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
