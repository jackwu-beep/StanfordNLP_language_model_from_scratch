import math
import torch
from torch import Tensor
from jaxtyping import Float


def softmax(x: Float[Tensor, " ..."], dim: int) -> Float[Tensor, " ..."]:
    # subtract max for numerical stability
    x = torch.subtract(x, torch.max(x, dim=dim, keepdim=True).values)

    # softmax
    exp = torch.exp(x)
    return torch.div(exp, torch.sum(exp, dim=dim, keepdim=True))


def scaled_dot_product_attention(
    Q: Float[Tensor, " ... queries d_k"],
    K: Float[Tensor, " ... keys d_k"],
    V: Float[Tensor, " ... values d_v"],
    mask: Float[Tensor, " ... queries keys"] | None = None,
) -> Float[Tensor, " ... queries d_v"]:
    d_k = Q.shape[-1]
    qk = torch.div(torch.einsum("...Qk,...Kk->...QK", Q, K), math.sqrt(d_k))

    if mask is not None:
        qk = torch.masked_fill(
            qk,
            mask=~mask,
            value=-torch.inf,
        )
    return torch.einsum("...QV,...Vv->...Qv", softmax(qk, dim=-1), V)
