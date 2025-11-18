from collections.abc import Callable
import torch


class AdamW(torch.optim.Optimizer):
    def __init__(self, params, lr: float, weight_decay: float, betas: tuple[int, int], eps=1e-8):
        if lr < 0:
            raise ValueError(f"Invalid learning rate: {lr}")
        defaults = {"lr": lr, "weight_decay": weight_decay, "betas": betas, "eps": eps}
        super().__init__(params, defaults)

    def step(self, closure: Callable | None = None):
        loss = None if closure is None else closure()
        for group in self.param_groups:
            lr, weight_decay, (b1, b2), eps = (
                group["lr"],
                group["weight_decay"],
                group["betas"],
                group["eps"],
            )
            for p in group["params"]:
                if p.grad is None:
                    continue

                state = self.state[p]  # Get state associated with p.

                # update moments
                m, v = state.get("m", 0), state.get("v", 0)
                m = b1 * m + (1 - b1) * p.grad.data
                v = b2 * v + (1 - b2) * torch.pow(p.grad.data, 2)
                state["m"], state["v"] = m, v

                t = state.get("t", 1)
                state["t"] = t + 1
                bias_correction1 = 1 - (b1 ** t)
                bias_correction2 = 1 - (b2 ** t)
                lr_adjusted = lr * (bias_correction2 ** 0.5) / bias_correction1

                # parameter update
                p.data = p.data - lr_adjusted * m / (torch.sqrt(v) + eps)

                # weight decay
                p.data = p.data - lr * weight_decay * p.data
            return loss
