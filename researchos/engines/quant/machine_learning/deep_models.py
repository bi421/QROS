        self.dilation = dilation

    def _layer_norm(self, x: np.ndarray, gain: np.ndarray, bias: np.ndarray) -> np.ndarray:
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return np.asarray(gain * (x - mean) / np.sqrt(var + 1e-6) + bias)

    def forward(self, x: np.ndarray, training: bool = True, dropout_rate: float = 0.0) -> np.ndarray:
        res = x
