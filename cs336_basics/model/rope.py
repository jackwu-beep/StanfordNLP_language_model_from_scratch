import numpy as np
import torch
from jaxtyping import Float, Int


class RotaryPositionalEmbedding(torch.nn.Module):
    def __init__(self, theta: float, d_k: int, max_seq_len: int, device=None):
        super().__init__()

        # compute rotation matrixes
        assert d_k % 2 == 0, "d_k must be a multiple of 2"
        k = np.arange(1, (d_k // 2) + 1)
        cosines, sines = (
            np.empty((max_seq_len, d_k), dtype=np.float32),
            np.empty((max_seq_len, d_k), dtype=np.float32),
        )
        for position in range(0, max_seq_len):
            angles = position / np.pow(theta, (2 * (k - 1)) / d_k)
            cosines[position] = np.repeat(np.cos(angles), 2)
            sines[position] = np.repeat(np.sin(angles), 2)

        # register rotation matrices
        self.register_buffer(
            "rotation_cos",
            torch.from_numpy(cosines).to(device),
            persistent=False,
        )
        self.register_buffer(
            "rotation_sin",
            torch.from_numpy(sines).to(device),
            persistent=False,
        )

    def forward(
        self,
        x: Float[torch.Tensor, " ... seq d_k"],
        token_positions: Int[torch.Tensor, " ... seq"],
    ) -> Float[torch.Tensor, " ... seq d_k"]:
        """
        Run RoPE for a given input tensor.

        Args:
            x: input
            token_positions (Int[Tensor, "... sequence_length"]): Tensor of shape (batch_size, sequence_length) with the token positions
        Returns:
            Float[Tensor, " ... sequence_length d_k"]: Tensor with RoPEd input.
        """
        x_flipped = x.reshape(*x.shape[:-1], -1, 2)[..., [1, 0]].flatten(-2)
        x_flipped[..., 0::2] *= -1

        cos = self.rotation_cos[token_positions]
        sin = self.rotation_sin[token_positions]
        return x * cos + x_flipped * sin
