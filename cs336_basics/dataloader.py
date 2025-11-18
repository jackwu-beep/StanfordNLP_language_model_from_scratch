import grain.python as grain
import glob

import numpy as np


class ToTrainingExamples(grain.experimental.FlatMapTransform):
    max_fan_out = 1_000_000

    def __init__(self, context_length):
        self.context_length = context_length

    def flat_map(self, elem):
        tokens = np.frombuffer(elem, dtype=np.uint16)
        for i in range(0, len(tokens) - self.context_length):
            inputs = tokens[i : i + self.context_length]
            targets = tokens[i + 1 : i + self.context_length + 1]
            yield (inputs, targets)


def get_data_loader(dataset_path, sequence_length: int = 1024, batch_size: int = 1):
    index_sampler = grain.IndexSampler(
        num_records=1,
        num_epochs=2,
        shard_options=grain.ShardOptions(shard_index=0, shard_count=1, drop_remainder=True),
        shuffle=True,
        seed=0,
    )

    data_loader = grain.DataLoader(
        data_source=grain.ArrayRecordDataSource(glob.glob(dataset_path)),
        operations=[
            ToTrainingExamples(sequence_length),
            grain.Batch(batch_size=batch_size, drop_remainder=True),
        ],
        sampler=index_sampler,
        worker_count=1,
    )
    return data_loader
