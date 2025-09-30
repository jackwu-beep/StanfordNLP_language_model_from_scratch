import torch
from jaxtyping import Float


def softmax(x: Float[torch.Tensor, " ..."], dim: int) -> Float[torch.Tensor, " ..."]:
    # subtract max for numerical stability
    x = torch.subtract(x, torch.max(x, dim=dim, keepdim=True).values)

    # softmax
    exp = torch.exp(x)
    return torch.div(exp, torch.sum(exp, dim=dim, keepdim=True))
