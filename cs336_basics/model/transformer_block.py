import torch
from jaxtyping import Float

from cs336_basics.model.multi_head_self_attn import MultiHeadSelfAttention, RopeConfig
from cs336_basics.model.rms_norm import RmsNorm
from cs336_basics.model.swiglu_ffn import SwigluFFN


class TransformerBlock(torch.nn.Module):
    def __init__(
        self,
        d_model: int,
        num_heads: int,
        d_ff: int,
        max_seq_len: int,
        rope_theta: float,
        device: torch.device | None = None,
        dtype: torch.dtype | None = None,
    ) -> None:
        super().__init__()

        self.ln1 = RmsNorm(d_model, device=device, dtype=dtype)
        self.attn = MultiHeadSelfAttention(
            d_model, num_heads, RopeConfig(rope_theta, max_seq_len), device=device, dtype=dtype
        )

        self.ln2 = RmsNorm(d_model, device=device, dtype=dtype)
        self.ffn = SwigluFFN(d_model, d_ff, device, dtype)

    def forward(
        self,
        x: Float[torch.Tensor, "batch seq d_model"],
    ) -> Float[torch.Tensor, "batch seq d_model"]:
        batches, seq_len = x.shape[0], x.shape[1]

        # generate token positions per batch
        token_positions = torch.arange(1, seq_len + 1).repeat(batches, 1)

        # multi-head attention with pre-norm
        y = x + self.attn.forward(self.ln1(x), token_positions)

        # feed-forward with pre-norm
        return y + self.ffn.forward(self.ln2(y))
