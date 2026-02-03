import regex as re
from collections import defaultdict

from cs336_basics.pretokenization_example import find_chunk_boundaries


PRETOKENIZER_PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""


class BPETokenizer:
    def __init__(self, special_tokens, num_processes=4):
        self.special_tokens = special_tokens
        self.dictionary = [bytes([i]) for i in range(256)]
        self.dictionary.extend(special_tokens)

        self.num_processes = num_processes

    
    def _pretokenize_chunk(self, chunk: str) -> dict[str, int]:
        split_regex = "|".join(re.escape(el) for el in self.special_tokens)
        ret = defaultdict(lambda:0)

        for doc in re.split(split_regex, chunk):
            for pre_token in re.finditer(PRETOKENIZER_PAT, doc):
                ret[pre_token.group()] += 1
        
        return ret
    
    def pretokenize(self, file_name):
        with open(file_name, "rb") as f:
            boundaries = find_chunk_boundaries(f, self.num_processes, b"<|endoftext|>")

            # The following is a serial implementation, but you can parallelize this
            # by sending each start/end pair to a set of processes.
            for start, end in zip(boundaries[:-1], boundaries[1:]):
                f.seek(start)
                chunk = f.read(end - start).decode("utf-8", errors="ignore")
                # Run pre-tokenization on your chunk and store the counts for each pre-token

                pretoken_counts = self._pretokenize_chunk(chunk)
                print(pretoken_counts)
