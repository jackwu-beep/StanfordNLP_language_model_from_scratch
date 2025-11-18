from einops import rearrange
import torch
from torch import Tensor
from jaxtyping import Int, Float


def cross_entropy_loss(
    inputs: Float[Tensor, "batch_size seq_len vocab_size"],
    targets: Int[Tensor, "batch_size seq_len"],
) -> Float[Tensor, ""]:
    """Given a tensor of inputs and targets, compute the average cross-entropy
    loss across examples.

    Args:
        inputs (Float[Tensor, "batch_size vocab_size"]): inputs[i][j] is the
            unnormalized logit of jth class for the ith example.
        targets (Int[Tensor, "batch_size"]): Tensor of shape (batch_size,) with the index of the correct class.
            Each value must be between 0 and `num_classes - 1`.

    Returns:
        Float[Tensor, ""]: The average cross-entropy loss across examples.
    """

    # subtract max for numerical stability
    inputs = torch.subtract(inputs, torch.max(inputs, dim=-1, keepdim=True).values)

    # for each batch, select the target
    inputs_flat = rearrange(inputs, "... vocab -> (...) vocab")
    targets_flat = rearrange(targets, "... -> (...)")
    selected = inputs_flat[torch.arange(inputs_flat.size(0)), targets_flat]

    # return avg cross entropy
    loss = torch.log(torch.sum(torch.exp(inputs_flat), dim=-1)) - selected
    return torch.mean(loss)
