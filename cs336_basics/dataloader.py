import grain.python as grain
import glob

import numpy as np
import torch


class ToTrainingExamples(grain.experimental.FlatMapTransform):
    max_fan_out = 1_000_000

    def __init__(self, context_length):
        self.context_length = context_length

    def flat_map(self, elem):
        tokens = np.frombuffer(elem, dtype=np.uint16)
        for i in range(0, len(tokens) - self.context_length, self.context_length):

            # adjust starting positions based on last token so that we always have context_length tokens
            last_target = max(i + self.context_length + 1, len(tokens))
            first_target = last_target - self.context_length
            last_input = last_target - 1
            first_input = first_target - 1

            inputs = tokens[first_input : last_input]
            targets = tokens[first_target : last_target]

            yield (inputs, targets)


def get_data_loader_lazy(dataset_path, sequence_length: int = 1024, batch_size: int = 1, num_epochs: int = 1, seed: int = 43):
    index_sampler = grain.IndexSampler(
        num_records=1,
        num_epochs=num_epochs,
        shuffle=True,
        seed=seed,
    )

    def _get_data_loader():
        return grain.DataLoader(
            data_source=grain.ArrayRecordDataSource(glob.glob(dataset_path)),
            operations=[
                ToTrainingExamples(sequence_length),
                grain.Batch(batch_size=batch_size, drop_remainder=True),
            ],
            sampler=index_sampler,
            worker_count=1,
        )
    return _get_data_loader
