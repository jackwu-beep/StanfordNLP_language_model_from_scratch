import glob
import math
import os
from pathlib import Path
import torch
from tqdm import tqdm
from cs336_basics.model.checkpointing import load_checkpoint, save_checkpoint
from cs336_basics.model.loss import cross_entropy_loss
from cs336_basics.model.misc import gradient_clipping


def training_loop(
    tokenizer,
    model,
    optimizer,
    data_loader,
    validation_data_loader,
    iterations,
    gradient_clip_max_l2_norm: float | None,
    checkpoint_dir,
    checkpoint_interval,
    learning_rate_schedule,
    run,
):
    device = next(model.parameters()).device
    if "mps" in str(device):
        model = torch.compile(model, backend="aot_eager")
    else:
        model = torch.compile(model)
    data_iterator = iter(data_loader())

    # start from last checkpoint
    iteration = 0
    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    checkpoints = sorted(glob.glob(os.path.join(checkpoint_dir, "checkpoint_*")))
    if len(checkpoints):
        iteration = load_checkpoint(checkpoints[-1], model, optimizer)
        print(f"Loading previous checkpoint at iter={iteration}")

        # Skip already processed batches
        print(f"Skipping {iteration} batches...")
        for _ in range(iteration):
            next(data_iterator)
        print(f"Done skipping {iteration} batches...")

    training_bar = tqdm(total=iterations, desc="train")
    training_bar.update(iteration)

    model.train()
    ema_loss = None
    ema_alpha = 0.05
    while iteration < iterations:

        lr = learning_rate_schedule.update_lr(iteration, optimizer)

        optimizer.zero_grad()

        # load batch
        try:
            inputs, targets = next(data_iterator)
        except StopIteration:
            raise Exception(f"out of data at iteration {iteration}!")
        inputs = torch.from_numpy(inputs).to(torch.int32).to(device=device)

        # step
        outputs = model(inputs)
        loss = cross_entropy_loss(outputs, targets)

        # update EMA loss
        if ema_loss is None:
            ema_loss = loss.item()
        else:
            ema_loss = ema_alpha * loss.item() + (1-ema_alpha) * ema_loss

        loss.backward()
        gradient_norm = gradient_clipping(model.parameters(), max_l2_norm=gradient_clip_max_l2_norm)

        optimizer.step()

        # checkpointing and metrics reporting
        if iteration != 0 and (iteration % checkpoint_interval == 0 or iteration == iterations - 1):
            save_checkpoint(
                model,
                optimizer,
                iteration,
                os.path.join(checkpoint_dir, f"checkpoint_{iteration:06d}"),
            )

            # calculate validation loss
            model.eval()
            val_loss, val_loss_per_token = _get_validation_loss(model, validation_data_loader, device)
            model.train()

            run.log({
                "train/loss": ema_loss,
                "val/loss": val_loss,
                "val/loss_per_token": val_loss_per_token,
                "val/perplexity": math.exp(val_loss),
                "val/perplexity_per_token": math.exp(val_loss_per_token),
                "learning_rate": lr,
                "grad_norm": gradient_norm
            }, step=iteration)

        # report training losses more frequently
        elif iteration != 0 and iteration % 100 == 0:
            run.log({
                "train/loss": ema_loss,
                "learning_rate": lr,
                "grad_norm": gradient_norm
            }, step=iteration)


        iteration += 1
        training_bar.update(1)
    training_bar.close()

    run.finish()


def _get_validation_loss(model, data_loader, device) -> float:
    seq_count = 0
    token_count = 0
    val_loss = 0.0
    validation_data = data_loader()
    with torch.no_grad():
        for batch in tqdm(validation_data, desc="validation"):
            inputs, targets = batch
            inputs = torch.from_numpy(inputs).to(torch.int32).to(device=device)
            logits = model(inputs)
            loss = cross_entropy_loss(logits, targets)
            val_loss += loss.item()
            seq_count += inputs.size(0)
            token_count += (inputs.size(0) * inputs.size(1))
    return val_loss / seq_count, val_loss / token_count
