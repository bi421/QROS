"""
Deep Learning Models for XAUUSD Prediction — Pure NumPy Implementation.

Implements LSTM, GRU, Transformer (attention), and TCN from scratch
using only numpy, enabling research without PyTorch/TensorFlow dependencies.

Architecture:
    - All models accept (batch, seq_len, features) input
    - All models support Monte Carlo dropout for uncertainty quantification
    - All models are deterministic given the same weights and seed
"""

from __future__ import annotations

import math
from typing import Any, Literal, cast

import numpy as np

# ──────────────────────────────────────────────────────────────
# 1. Activations and utilities
# ──────────────────────────────────────────────────────────────


def sigmoid(x: np.ndarray) -> np.ndarray:
    return cast(np.ndarray, 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500))))


def tanh(x: np.ndarray) -> np.ndarray:
    return cast(np.ndarray, np.tanh(x))


def relu(x: np.ndarray) -> np.ndarray:
    return cast(np.ndarray, np.maximum(0, x))


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    e = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return cast(np.ndarray, e / np.sum(e, axis=axis, keepdims=True))


def dropout(x: np.ndarray, rate: float, rng: np.random.Generator, training: bool = True) -> np.ndarray:
    if not training or rate <= 0.0:
        return x
    mask = rng.binomial(1, 1.0 - rate, size=x.shape).astype(np.float32)
    return x * mask / (1.0 - rate)


def xavier_init(shape: tuple[int, ...], rng: np.random.Generator) -> np.ndarray:
    """Xavier/Glorot initialization."""
    if len(shape) == 2:
        fan_in, fan_out = shape
    else:
        fan_in = shape[0]
        fan_out = shape[-1]
    limit = math.sqrt(6.0 / (fan_in + fan_out))
    return rng.uniform(-limit, limit, size=shape).astype(np.float32)


def orthogonal_init(shape: tuple[int, ...], rng: np.random.Generator) -> np.ndarray:
    """Orthogonal initialization for recurrent weights."""
    if len(shape) == 2:
        rows, cols = shape
    else:
        rows = shape[0]
        cols = shape[-1]
    flat = rng.normal(0.0, 1.0, size=(rows, cols)).astype(np.float32)
    u, _, vt = np.linalg.svd(flat, full_matrices=False)
    if rows > cols:
        W = u
    else:
        W = vt
    return W.reshape(shape)


# ──────────────────────────────────────────────────────────────
# 2. LSTM
# ──────────────────────────────────────────────────────────────


class LSTMCell:
    def __init__(self, input_dim: int, hidden_dim: int, rng: np.random.Generator):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.rng = rng
        scale = math.sqrt(1.0 / (input_dim + hidden_dim))
        self.W_i = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.W_f = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.W_o = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.W_c = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.U_i = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.U_f = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.U_o = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.U_c = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.b_i = np.zeros(hidden_dim, dtype=np.float32)
        self.b_f = np.zeros(hidden_dim, dtype=np.float32)
        self.b_o = np.zeros(hidden_dim, dtype=np.float32)
        self.b_c = np.zeros(hidden_dim, dtype=np.float32)

    def forward(self, x: np.ndarray, h_prev: np.ndarray, c_prev: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        i = sigmoid(x @ self.W_i + h_prev @ self.U_i + self.b_i)
        f = sigmoid(x @ self.W_f + h_prev @ self.U_f + self.b_f)
        o = sigmoid(x @ self.W_o + h_prev @ self.U_o + self.b_o)
        c_tilde = tanh(x @ self.W_c + h_prev @ self.U_c + self.b_c)
        c = f * c_prev + i * c_tilde
        h = o * tanh(c)
        return h, c

    def get_params(self) -> list[np.ndarray]:
        return [self.W_i, self.W_f, self.W_o, self.W_c, self.U_i, self.U_f, self.U_o, self.U_c, self.b_i, self.b_f, self.b_o, self.b_c]


class LSTM:
    def __init__(self, input_dim: int, hidden_dim: int, rng: np.random.Generator):
        self.cell = LSTMCell(input_dim, hidden_dim, rng)
        self.hidden_dim = hidden_dim

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        batch_size, seq_len, _ = x.shape
        h = np.zeros((batch_size, self.hidden_dim), dtype=np.float32)
        c = np.zeros((batch_size, self.hidden_dim), dtype=np.float32)
        outputs = []
        for t in range(seq_len):
            h, c = self.cell.forward(x[:, t, :], h, c)
            h = dropout(h, dropout_rate, self.cell.rng, training)
            outputs.append(h)
        return np.stack(outputs, axis=1)


# ──────────────────────────────────────────────────────────────
# 3. GRU
# ──────────────────────────────────────────────────────────────


class GRUCell:
    def __init__(self, input_dim: int, hidden_dim: int, rng: np.random.Generator):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.rng = rng
        scale = math.sqrt(1.0 / (input_dim + hidden_dim))
        self.W_z = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.W_r = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.W_h = rng.normal(0, scale, (input_dim, hidden_dim)).astype(np.float32)
        self.U_z = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.U_r = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.U_h = orthogonal_init((hidden_dim, hidden_dim), rng)
        self.b_z = np.zeros(hidden_dim, dtype=np.float32)
        self.b_r = np.zeros(hidden_dim, dtype=np.float32)
        self.b_h = np.zeros(hidden_dim, dtype=np.float32)

    def forward(self, x: np.ndarray, h_prev: np.ndarray) -> np.ndarray:
        z = sigmoid(x @ self.W_z + h_prev @ self.U_z + self.b_z)
        r = sigmoid(x @ self.W_r + h_prev @ self.U_r + self.b_r)
        h_tilde = tanh(x @ self.W_h + (r * h_prev) @ self.U_h + self.b_h)
        h = (1 - z) * h_prev + z * h_tilde
        return cast(np.ndarray, h)


class GRU:
    def __init__(self, input_dim: int, hidden_dim: int, rng: np.random.Generator):
        self.cell = GRUCell(input_dim, hidden_dim, rng)
        self.hidden_dim = hidden_dim

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        batch_size, seq_len, _ = x.shape
        h = np.zeros((batch_size, self.hidden_dim), dtype=np.float32)
        outputs = []
        for t in range(seq_len):
            h = self.cell.forward(x[:, t, :], h)
            h = dropout(h, dropout_rate, self.cell.rng, training)
            outputs.append(h)
        return np.stack(outputs, axis=1)


# ──────────────────────────────────────────────────────────────
# 4. Transformer (attention + feed-forward)
# ──────────────────────────────────────────────────────────────


class SelfAttention:
    def __init__(self, d_model: int, n_heads: int, rng: np.random.Generator):
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"
        self.W_q = xavier_init((d_model, d_model), rng)
        self.W_k = xavier_init((d_model, d_model), rng)
        self.W_v = xavier_init((d_model, d_model), rng)
        self.W_o = xavier_init((d_model, d_model), rng)
        self.rng = rng

    def forward(self, x: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        batch_size, seq_len, _ = x.shape
        Q = x @ self.W_q
        K = x @ self.W_k
        V = x @ self.W_v
        Q = Q.reshape(batch_size, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)
        K = K.reshape(batch_size, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)
        V = V.reshape(batch_size, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)
        scores = Q @ K.transpose(0, 1, 3, 2) / math.sqrt(self.d_k)
        if mask is not None:
            scores = np.where(mask == 0, -1e9, scores)
        attn = softmax(scores, axis=-1)
        attn = dropout(attn, 0.1, self.rng, True)
        context = attn @ V
        context = context.transpose(0, 2, 1, 3).reshape(batch_size, seq_len, self.d_model)
        return cast(np.ndarray, context @ self.W_o)


class FeedForward:
    def __init__(self, d_model: int, d_ff: int, rng: np.random.Generator):
        self.W1 = xavier_init((d_model, d_ff), rng)
        self.W2 = xavier_init((d_ff, d_model), rng)
        self.b1 = np.zeros(d_ff, dtype=np.float32)
        self.b2 = np.zeros(d_model, dtype=np.float32)
        self.rng = rng

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        x = relu(x @ self.W1 + self.b1)
        x = dropout(x, dropout_rate, self.rng, training)
        return cast(np.ndarray, x @ self.W2 + self.b2)


class TransformerBlock:
    def __init__(self, d_model: int, n_heads: int, d_ff: int, rng: np.random.Generator):
        self.attn = SelfAttention(d_model, n_heads, rng)
        self.ff = FeedForward(d_model, d_ff, rng)
        self.ln1_gain = np.ones(d_model, dtype=np.float32)
        self.ln1_bias = np.zeros(d_model, dtype=np.float32)
        self.ln2_gain = np.ones(d_model, dtype=np.float32)
        self.ln2_bias = np.zeros(d_model, dtype=np.float32)
        self.rng = rng

    def _layer_norm(self, x: np.ndarray, gain: np.ndarray, bias: np.ndarray) -> np.ndarray:
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return cast(np.ndarray, gain * (x - mean) / np.sqrt(var + 1e-6) + bias)

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        attn_out = self.attn.forward(x)
        x = self._layer_norm(x + attn_out, self.ln1_gain, self.ln1_bias)
        ff_out = self.ff.forward(x, training, dropout_rate)
        x = self._layer_norm(x + ff_out, self.ln2_gain, self.ln2_bias)
        return x


class Transformer:
    def __init__(self, input_dim: int, d_model: int, n_heads: int, d_ff: int, n_layers: int, rng: np.random.Generator):
        self.input_proj = xavier_init((input_dim, d_model), rng)
        self.blocks = [TransformerBlock(d_model, n_heads, d_ff, rng) for _ in range(n_layers)]
        self.rng = rng

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        x = x @ self.input_proj
        for block in self.blocks:
            x = block.forward(x, training, dropout_rate)
        return x


# ──────────────────────────────────────────────────────────────
# 5. TCN (Temporal Convolutional Network)
# ──────────────────────────────────────────────────────────────


class CausalConv1D:
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int, rng: np.random.Generator):
        self.kernel_size = kernel_size
        self.W = xavier_init((kernel_size, in_channels, out_channels), rng)
        self.b = np.zeros(out_channels, dtype=np.float32)
        self.rng = rng

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        batch_size, seq_len, in_channels = x.shape
        out_channels = self.W.shape[-1]
        padding = self.kernel_size - 1
        x_padded = np.pad(x, ((0, 0), (padding, 0), (0, 0)), mode="constant")
        out = np.zeros((batch_size, seq_len, out_channels), dtype=np.float32)
        for t in range(seq_len):
            window = x_padded[:, t : t + self.kernel_size, :]
            out[:, t, :] = np.tensordot(window, self.W, axes=([1, 2], [0, 1])) + self.b
        return dropout(out, dropout_rate, self.rng, training)


class TCNBlock:
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int, dilation: int, rng: np.random.Generator):
        self.conv1 = CausalConv1D(in_channels, out_channels, kernel_size, rng)
        self.conv2 = CausalConv1D(out_channels, out_channels, kernel_size, rng)
        self.ln1_gain = np.ones(out_channels, dtype=np.float32)
        self.ln1_bias = np.zeros(out_channels, dtype=np.float32)
        self.ln2_gain = np.ones(out_channels, dtype=np.float32)
        self.ln2_bias = np.zeros(out_channels, dtype=np.float32)
        self.rng = rng
        self.kernel_size = kernel_size
        self.dilation = dilation

    def _layer_norm(self, x: np.ndarray, gain: np.ndarray, bias: np.ndarray) -> np.ndarray:
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return gain * (x - mean) / np.sqrt(var + 1e-6) + bias

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        res = x
        x = self.conv1.forward(x, training, dropout_rate)
        x = relu(x)
        x = self._layer_norm(x, self.ln1_gain, self.ln1_bias)
        x = self.conv2.forward(x, training, dropout_rate)
        x = relu(x)
        x = self._layer_norm(x, self.ln2_gain, self.ln2_bias)
        if res.shape[-1] != x.shape[-1]:
            res = res @ xavier_init((res.shape[-1], x.shape[-1]), self.rng)
        return cast(np.ndarray, x + res)


class TCN:
    def __init__(self, input_dim: int, channels: list[int], kernel_size: int, rng: np.random.Generator):
        self.blocks = []
        in_ch = input_dim
        for i, out_ch in enumerate(channels):
            dilation = 2**i
            self.blocks.append(TCNBlock(in_ch, out_ch, kernel_size, dilation, rng))
            in_ch = out_ch
        self.final_gain = np.ones(channels[-1], dtype=np.float32)
        self.final_bias = np.zeros(channels[-1], dtype=np.float32)
        self.rng = rng

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        for block in self.blocks:
            x = block.forward(x, training, dropout_rate)
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return cast(np.ndarray, self.final_gain * (x - mean) / np.sqrt(var + 1e-6) + self.final_bias)


# ──────────────────────────────────────────────────────────────
# 6. Prediction heads
# ──────────────────────────────────────────────────────────────


class RegressionHead:
    def __init__(self, input_dim: int, output_dim: int, rng: np.random.Generator):
        self.W = xavier_init((input_dim, output_dim), rng)
        self.b = np.zeros(output_dim, dtype=np.float32)

    def forward(self, x: np.ndarray) -> np.ndarray:
        return cast(np.ndarray, x @ self.W + self.b)


class ClassificationHead:
    def __init__(self, input_dim: int, n_classes: int, rng: np.random.Generator):
        self.W = xavier_init((input_dim, n_classes), rng)
        self.b = np.zeros(n_classes, dtype=np.float32)

    def forward(self, x: np.ndarray) -> np.ndarray:
        return softmax(x @ self.W + self.b, axis=-1)


# ──────────────────────────────────────────────────────────────
# 7. Full models
# ──────────────────────────────────────────────────────────────


class SequenceModel:
    """Unified interface for all sequence models."""

    def __init__(self, model_type: str, input_dim: int, seq_len: int, hidden_dim: int = 64, rng_seed: int = 42):
        self.rng = np.random.default_rng(rng_seed)
        self.model_type = model_type
        self.seq_len = seq_len
        self.hidden_dim = hidden_dim

        if model_type == "lstm":
            self.backbone: Any = LSTM(input_dim, hidden_dim, self.rng)
        elif model_type == "gru":
            self.backbone = GRU(input_dim, hidden_dim, self.rng)
        elif model_type == "transformer":
            self.backbone = Transformer(input_dim, hidden_dim, n_heads=4, d_ff=hidden_dim * 4, n_layers=2, rng=self.rng)
        elif model_type == "tcn":
            self.backbone = TCN(input_dim, channels=[hidden_dim, hidden_dim * 2], kernel_size=3, rng=self.rng)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        # Use last time step output for prediction
        final_dim = hidden_dim if model_type in ("lstm", "gru") else (hidden_dim if model_type == "tcn" else hidden_dim)
        self.head = RegressionHead(final_dim, 1, self.rng)

    def forward(self, x: np.ndarray, training: bool = True, mc_dropout: bool = False) -> np.ndarray:
        dropout_rate = 0.1 if (training or mc_dropout) else 0.0
        backbone_out = self.backbone.forward(x, training or mc_dropout, dropout_rate)
        last_step = backbone_out[:, -1, :] if backbone_out.ndim == 3 else backbone_out
        return self.head.forward(last_step).flatten()

    def predict_with_uncertainty(self, x: np.ndarray, n_samples: int = 100) -> tuple[np.ndarray, np.ndarray]:
        """Monte Carlo dropout for uncertainty quantification."""
        preds: list[np.ndarray] = []
        for _ in range(n_samples):
            pred = self.forward(x, training=False, mc_dropout=True)
            preds.append(pred)
        preds_array = np.stack(preds)
        mean = np.mean(preds_array, axis=0)
        std = np.std(preds_array, axis=0)
        return mean, std


# ──────────────────────────────────────────────────────────────
# 8. Training utilities
# ──────────────────────────────────────────────────────────────


def mse_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    return float(np.mean((y_pred - y_true) ** 2))


def mae_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    return float(np.mean(np.abs(y_pred - y_true)))


def directional_accuracy(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    correct = np.sum((y_pred > 0) == (y_true > 0))
    return float(correct / len(y_true))


class SimpleTrainer:
    """Minimal SGD trainer with early stopping (no backprop framework)."""

    def __init__(self, model: SequenceModel, learning_rate: float = 1e-3):
        self.model = model
        self.lr = learning_rate
        self.rng = np.random.default_rng(42)

    def _get_all_params(self) -> list[np.ndarray]:
        params: list[np.ndarray] = []

        def collect(module: Any) -> None:
            if hasattr(module, "get_params"):
                params.extend(module.get_params())
            if hasattr(module, "cell"):
                collect(module.cell)
            if hasattr(module, "blocks"):
                for b in module.blocks:
                    collect(b)
            if hasattr(module, "backbone"):
                collect(module.backbone)
            if hasattr(module, "W1"):
                params.extend([module.W1, module.W2, module.b1, module.b2])
            if hasattr(module, "W"):
                params.extend([module.W, module.b])
            if hasattr(module, "W_q"):
                params.extend([module.W_q, module.W_k, module.W_v, module.W_o])
            if hasattr(module, "W_i"):
                params.extend([module.W_i, module.W_f, module.W_o, module.W_c, module.U_i, module.U_f, module.U_o, module.U_c, module.b_i, module.b_f, module.b_o, module.b_c])
            if hasattr(module, "W_z"):
                params.extend([module.W_z, module.W_r, module.W_h, module.U_z, module.U_r, module.U_h, module.b_z, module.b_r, module.b_h])
            if hasattr(module, "W1"):
                params.extend([module.W1, module.W2, module.b1, module.b2])
            if hasattr(module, "input_proj"):
                params.append(module.input_proj)

        collect(self.model)
        return params

    def train_epoch(self, X: np.ndarray, y: np.ndarray, batch_size: int = 32) -> float:
        params = self._get_all_params()
        indices = self.rng.permutation(len(X))
        total_loss = 0.0
        n_batches = 0

        for start in range(0, len(X), batch_size):
            batch_idx = indices[start : start + batch_size]
            xb = X[batch_idx]
            yb = y[batch_idx]

            # Forward
            y_pred = self.model.forward(xb, training=True)
            loss = mse_loss(y_pred, yb)
            total_loss += loss
            n_batches += 1

            # Numerical gradient (finite difference) — slow but framework-independent
            eps = 1e-4
            for p in params:
                grad = np.zeros_like(p)
                it = np.nditer(p, flags=["multi_index"], op_flags=cast(list[Literal["readwrite"]], ["readwrite"]))
                while not it.finished:
                    ix = it.multi_index
                    old_val = p[ix]
                    p[ix] = old_val + eps
                    y_pred_plus = self.model.forward(xb, training=False)
                    loss_plus = mse_loss(y_pred_plus, yb)
                    p[ix] = old_val - eps
                    y_pred_minus = self.model.forward(xb, training=False)
                    loss_minus = mse_loss(y_pred_minus, yb)
                    p[ix] = old_val
                    grad[ix] = (loss_plus - loss_minus) / (2 * eps)
                    it.iternext()
                p -= self.lr * grad

        return total_loss / max(n_batches, 1)

    def fit(self, X: np.ndarray, y: np.ndarray, X_val: np.ndarray, y_val: np.ndarray, epochs: int = 50, batch_size: int = 32, patience: int = 5) -> dict[str, float]:
        best_val_loss = float("inf")
        best_params: list[np.ndarray] | None = None
        wait = 0

        for epoch in range(epochs):
            self.train_epoch(X, y, batch_size)
            val_pred = self.model.forward(X_val, training=False)
            val_loss = mse_loss(val_pred, y_val)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_params = [p.copy() for p in self._get_all_params()]
                wait = 0
            else:
                wait += 1
                if wait >= patience:
                    break

        if best_params is not None:
            params = self._get_all_params()
            for p, bp in zip(params, best_params):
                p[:] = bp

        return {"best_val_loss": best_val_loss}


class MLPRegressor:
    """Small NumPy MLP retained for the legacy ML comparison surface."""

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        output_dim: int = 1,
        dropout_rate: float = 0.0,
        random_state: int = 42,
    ) -> None:
        if input_dim <= 0 or hidden_dim <= 0 or output_dim <= 0:
            raise ValueError("MLP dimensions must be positive")
        self.dropout_rate = dropout_rate
        rng = np.random.default_rng(random_state)
        self.W1 = xavier_init((input_dim, hidden_dim), rng)
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)
        self.W2 = xavier_init((hidden_dim, output_dim), rng)
        self.b2 = np.zeros(output_dim, dtype=np.float32)

    def forward(self, X: np.ndarray, training: bool = False) -> np.ndarray:
        inputs = np.asarray(X, dtype=np.float32)
        hidden = np.maximum(inputs @ self.W1 + self.b1, 0.0)
        if training and self.dropout_rate > 0.0:
            keep = 1.0 - self.dropout_rate
            hidden = hidden * (np.random.default_rng(0).random(hidden.shape) < keep) / keep
        return hidden @ self.W2 + self.b2

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 50, batch_size: int = 32, learning_rate: float = 1e-3) -> None:
        inputs = np.asarray(X, dtype=np.float32)
        targets = np.asarray(y, dtype=np.float32).reshape(-1, 1)
        if len(inputs) != len(targets):
            raise ValueError("X and y must have equal sample counts")
        for _ in range(max(0, epochs)):
            for start in range(0, len(inputs), max(1, batch_size)):
                xb = inputs[start : start + max(1, batch_size)]
                yb = targets[start : start + max(1, batch_size)]
                z1 = xb @ self.W1 + self.b1
                h = np.maximum(z1, 0.0)
                pred = h @ self.W2 + self.b2
                error = pred - yb
                scale = 2.0 / max(1, len(xb))
                grad_w2 = scale * h.T @ error
                grad_b2 = scale * error.sum(axis=0)
                grad_h = error @ self.W2.T
                grad_z1 = grad_h * (z1 > 0.0)
                grad_w1 = scale * xb.T @ grad_z1
                grad_b1 = scale * grad_z1.sum(axis=0)
                self.W2 -= learning_rate * grad_w2
                self.b2 -= learning_rate * grad_b2
                self.W1 -= learning_rate * grad_w1
                self.b1 -= learning_rate * grad_b1

    fit = train
