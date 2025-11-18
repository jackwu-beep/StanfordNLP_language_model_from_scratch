import torch
from jaxtyping import Float

from cs336_basics.model.linear import Linear


# TODO: d_ff = 8/3 d_model


class SwigluFFN(torch.nn.Module):
    def __init__(
        self,
        d_model: int,
        d_ff: int,
        device: torch.device | None = None,
        dtype: torch.dtype | None = None,
    ):
        super().__init__()
        self.w1 = Linear(d_model, d_ff, dtype=dtype, device=device)
        self.w2 = Linear(d_ff, d_model, dtype=dtype, device=device)
        self.w3 = Linear(d_model, d_ff, dtype=dtype, device=device)

    def forward(
        self, x: Float[torch.Tensor, " batch seq d_model"]
    ) -> Float[torch.Tensor, " ... batch seq d_model"]:
        inner = self.w1(x)
        return self.w2(inner * torch.sigmoid(inner) * (self.w3(x)))
