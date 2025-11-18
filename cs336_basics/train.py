import glob
import os
from pathlib import Path
import torch
from cs336_basics.model.checkpointing import load_checkpoint, save_checkpoint
from cs336_basics.model.loss import cross_entropy_loss
from cs336_basics.model.misc import gradient_clipping


def training_loop(
    tokenizer,
    model,
    optimizer,
    data_loader,
    iterations,
    gradient_clip_max_l2_norm: float | None,
    checkpoint_dir,
    checkpoint_interval,
    run,
):
    device = next(model.parameters()).device
    data_iterator = iter(data_loader)

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

    while iteration < iterations:
        print(f"iter={iteration}")
        optimizer.zero_grad()

        # load batch
        inputs, targets = next(data_iterator)
        inputs = torch.from_numpy(inputs).to(torch.int32).to(device=device)

        # step
        outputs = model(inputs)
        loss = cross_entropy_loss(outputs, targets)
        loss.backward()
        run.log({"loss": loss.item()})
        if gradient_clip_max_l2_norm is not None:
            gradient_clipping(model.parameters(), max_l2_norm=gradient_clip_max_l2_norm)
        optimizer.step()

        # checkpoint
        if iteration % checkpoint_interval == 0:
            save_checkpoint(
                model,
                optimizer,
                iteration,
                os.path.join(checkpoint_dir, f"checkpoint_{iteration:06d}"),
            )

        iteration += 1

    # checkpoint last
    save_checkpoint(
        model,
        optimizer,
        iteration,
        os.path.join(checkpoint_dir, f"checkpoint_{iteration:06d}"),
    )

    run.finish()
