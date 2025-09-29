import math
import torch
from jaxtyping import Float


# TODO: d_ff = 8/3 d_model


class Swiglu(torch.nn.Module):
    def __init__(
        self,
        d_model: int,
        d_ff: int,
        device: torch.device | None = None,
        dtype: torch.dtype | None = None,
    ):
        super().__init__()

        initialization_std = math.sqrt(2 / (d_model + d_ff))
        self.w1 = torch.nn.Parameter(
            torch.nn.init.trunc_normal_(
                torch.empty(d_ff, d_model, dtype=dtype, device=device),
                mean=0,
                std=initialization_std,
                a=-3 * initialization_std,
                b=3 * initialization_std,
            ),
        )
        self.w2 = torch.nn.Parameter(
            torch.nn.init.trunc_normal_(
                torch.empty(d_model, d_ff, dtype=dtype, device=device),
                mean=0,
                std=initialization_std,
                a=-3 * initialization_std,
                b=3 * initialization_std,
            ),
        )
        self.w3 = torch.nn.Parameter(
            torch.nn.init.trunc_normal_(
                torch.empty(d_ff, d_model, dtype=dtype, device=device),
                mean=0,
                std=initialization_std,
                a=-3 * initialization_std,
                b=3 * initialization_std,
            ),
        )

    def forward(
        self, x: Float[torch.Tensor, " batch seq d_model"]
    ) -> Float[torch.Tensor, " ... batch seq d_model"]:
        inner = x @ self.w1.T
        return (inner * torch.sigmoid(inner) * (x @ self.w3.T)) @ self.w2.T
