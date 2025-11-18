from dataclasses import dataclass
import torch
from jaxtyping import Float, Int

from cs336_basics.model.linear import Linear
from cs336_basics.model.misc import scaled_dot_product_attention
from cs336_basics.model.rope import RotaryPositionalEmbedding

# TODO: As a stretch goal, try combining the key, query, and value projections into a single weight matrix so you only need a single matrix multiply.


@dataclass
class RopeConfig:
    theta: float
    max_seq_len: int


class MultiHeadSelfAttention(torch.nn.Module):
    """
    Given the key, query, and value projection weights of a naive unbatched
    implementation of multi-head attention, return the output of an optimized batched
    implementation. This implementation should handle the key, query, and value projections
    for all heads in a single matrix multiply.
    This function should not use RoPE.
    See section 3.2.2 of Vaswani et al., 2017.

    Args:
        d_model (int): Dimensionality of the feedforward input and output.
        num_heads (int): Number of heads to use in multi-headed attention.
        q_proj_weight (Float[Tensor, "d_k d_in"]): Weights for the Q projection
        k_proj_weight (Float[Tensor, "d_k d_in"]): Weights for the K projection
        v_proj_weight (Float[Tensor, "d_k d_in"]): Weights for the V projection
        o_proj_weight (Float[Tensor, "d_model d_v"]): Weights for the output projection
        in_features (Float[Tensor, "... sequence_length d_in"]): Tensor to run your implementation on.

    Returns:
        Float[Tensor, " ... sequence_length d_out"]: Tensor with the output of running your optimized, batched multi-headed attention
        implementation with the given QKV projection weights and input features.
    """

    def __init__(
        self,
        d_model: int,
        num_heads: int,
        rope_config: RopeConfig | None = None,
        device: torch.device | None = None,
        dtype: torch.dtype | None = None,
    ):
        super().__init__()
        assert d_model % num_heads == 0
        self.d_k = int(d_model / num_heads)
        self.d_model = d_model
        self.num_heads = num_heads
        d_v = self.d_k
        self.q_proj = Linear(self.d_k * num_heads, d_model, device, dtype)
        self.k_proj = Linear(self.d_k * num_heads, d_model, device, dtype)
        self.v_proj = Linear(d_model, d_v * num_heads, device, dtype)
        self.output_proj = Linear(d_model, d_v * num_heads, device, dtype)
        self.device = device

        # rope
        self._rope: RotaryPositionalEmbedding | None = None
        if rope_config:
            self._rope = RotaryPositionalEmbedding(
                rope_config.theta, self.d_k, max_seq_len=rope_config.max_seq_len, device=device
            )

    def forward(
        self,
        x: Float[torch.Tensor, " ... sequence_length in_features"],
        token_positions: Int[torch.Tensor, " ... sequence_length"] | None = None,
    ) -> Float[torch.Tensor, " ... sequence_length features_out"]:
        attention_heads = []

        # causal mask
        seq_len = x.shape[-2]
        mask = torch.triu(
            torch.ones((seq_len, seq_len), dtype=torch.bool, device=self.device), diagonal=0
        ).T

        # project q, k, v
        q_proj = self.q_proj(x)
        k_proj = self.k_proj(x)
        v_proj = self.v_proj(x)

        # dot product for each head
        for q, k, v in zip(
            q_proj.split(self.d_k, -1),
            k_proj.split(self.d_k, -1),
            v_proj.split(self.d_k, -1),
        ):
            if token_positions is not None and self._rope is not None:
                q = self._rope(q, token_positions)
                k = self._rope(k, token_positions)
            attention_heads.append(scaled_dot_product_attention(q, k, v, mask=mask))

        # concatenate and project
        return self.output_proj(torch.cat(attention_heads, dim=-1))
