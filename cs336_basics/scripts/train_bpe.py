# Write a function that, given a path to an input text file, trains a (byte-level) BPE tokenizer.

# Your BPE training function should handle (at least) the following input parameters:
# input_path: str Path to a text file with BPE tokenizer training data.
# vocab_size: int A positive integer that defines the maximum final vocabulary size (including the
#             initial byte vocabulary, vocabulary items produced from merging, and any special tokens).
# special_tokens: list[str] A list of strings to add to the vocabulary, which do not otherwise affect BPE training.

# Your BPE training function should return the resulting vocabulary and merges:
# vocab: dict[int, bytes] The tokenizer vocabulary, a mapping from int (token ID in the vocabulary) to bytes (token bytes).
# merges: list[tuple[bytes, bytes]] A list of BPE merges produced from training. Each list item is a tuple of bytes (<token1>, <token2>), 
#         representing that <token1> was merged with <token2>. The merges should be ordered by order of creation.

# To test your BPE training function against our provided tests, you will first need to implement the
# test adapter at [adapters.run_train_bpe]. Then, run uv run pytest tests/test_train_bpe.py.
# Your implementation should be able to pass all tests. Optionally (this could be a large time-investment),
import os
import sys
import pickle
import pathlib
import time
import psutil
from tests.adapters import run_train_bpe
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

data_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "data"
input_path = os.path.join(data_dir, "TinyStoriesV2-GPT4-train.txt")

# where to store tokenizer
tokenizer_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "tokenizer"
vocab_path = os.path.join(tokenizer_dir, "TinyStoriesV2-bpe-vocab.pkl")
merges_path = os.path.join(tokenizer_dir, "TinyStoriesV2-bpe-merges.pkl")

# training parameters
vocab_size = 10_000
special_tokens = ["<|endoftext|>"]

process = psutil.Process(os.getpid())
start_mem = process.memory_info().rss / 1024 ** 2  # MB
start_time = time.time()

vocab, merges = run_train_bpe(input_path=input_path, 
                              vocab_size=vocab_size,
                              special_tokens=special_tokens)

end_time = time.time()
end_mem = process.memory_info().rss / 1024 ** 2  # MB

# write the vocab and merges
os.makedirs(tokenizer_dir, exist_ok=True)
with open(vocab_path, "wb") as f:
    pickle.dump(vocab, f)
with open(merges_path, "wb") as f:
    pickle.dump(merges, f)

longest_token = max(vocab.values(), key=len)
print("longest token:", longest_token, "with length", len(longest_token))
elapsed_hours = (end_time - start_time) / 3600
used_memory = end_mem - start_mem
print(f"Training took {elapsed_hours:.4f} hours (~{(elapsed_hours*60):.2f} minutes)")
print(f"Memory used: {used_memory:.2f} MB")