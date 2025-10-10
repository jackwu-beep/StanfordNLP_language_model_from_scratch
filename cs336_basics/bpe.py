import os
import multiprocessing as mp
from collections import defaultdict, Counter
from typing import List, Tuple, BinaryIO

# 第三方库
import regex
import re
from tqdm import tqdm



PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""


def find_chunk_boundaries(
    file: BinaryIO, 
    desired_num_chunks: int, 
    split_special_token: bytes
) -> list[int]:
    """
    Chunk the file into parts that can be counted independently.
    May return fewer chunks if the boundaries end up overlapping.
    """
    assert isinstance(split_special_token, bytes), (
        "Must represent special token as a bytestring"
    )

    # Get total file size in bytes
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    chunk_size = file_size // desired_num_chunks

    # Initial guesses for chunk boundary locations, uniformly spaced
    # Chunks start on previous index, don't include last index
    chunk_boundaries = [i * chunk_size for i in range(desired_num_chunks + 1)]
    chunk_boundaries[-1] = file_size

    mini_chunk_size = 4096  # Read ahead by 4k bytes at a time

    for bi in range(1, len(chunk_boundaries) - 1):
        initial_position = chunk_boundaries[bi]
        file.seek(initial_position)  # Start at boundary guess
        while True:
            mini_chunk = file.read(mini_chunk_size)  # Read a mini chunk

            # If EOF, this boundary should be at the end of the file
            if mini_chunk == b"":
                chunk_boundaries[bi] = file_size
                break

            # Find the special token in the mini chunk
            found_at = mini_chunk.find(split_special_token)
            if found_at != -1:
                chunk_boundaries[bi] = initial_position + found_at
                break
            initial_position += mini_chunk_size

    # Make sure all boundaries are unique, but might be fewer than desired_num_chunks
    return sorted(set(chunk_boundaries))


class BPE:
    def __init__(self, ):
        self.vocab = {}
        self.bytes_to_id = {}
        self.merges = []
        self.next_id = 0

    def _init_bpe(self, special_tokens: List[str] = None):
        for i in range(256):
            byte_token = bytes([i])
            if byte_token not in self.bytes_to_id:  # Avoid duplicating special token bytes
                self.vocab[self.next_id] = byte_token
                self.bytes_to_id[byte_token] = self.next_id
                self.next_id += 1

        self.special_tokens = special_tokens or ["<|endoftext|>"]
        for token in self.special_tokens:
            byte_token = token.encode('utf-8')
            self.vocab[self.next_id] = byte_token
            self.bytes_to_id[byte_token] = self.next_id
            self.next_id += 1

        self._special_token_pattern = re.compile("|".join(re.escape(t) for t in self.special_tokens))

    def _process_part(self, part: str) -> Counter:
        """Process a string segment into Counter of id tuples"""
        part_word_freqs = Counter()
        temp_counts = {}

        for match in regex.finditer(PAT, part, flags=regex.UNICODE):
            pretoken = match.group()               # 获取匹配字符串
            id_tuple = tuple(b for b in pretoken.encode('utf-8'))  # 转成 bytes tuple
            temp_counts[id_tuple] = temp_counts.get(id_tuple, 0) + 1
        part_word_freqs.update(temp_counts)
        return part_word_freqs
    
    def _split_special_tokens(self, text: str) -> list[str]:
        """Split text by special tokens, remove empty strings"""
        if not self.special_tokens:
            list_text = [text]
        else:
            list_text = [seg for seg in re.split(self._special_token_pattern, text) if seg]

        word_freqs = Counter()
        for part in list_text:
            word_freqs.update(self._process_part(part))
        return word_freqs
    
    def _process_sub_text(self, args) -> Counter:
        """Worker function for multiprocessing"""
        file_path, start, end = args
        word_freqs = Counter()
        with open(file_path, "rb") as f:
            f.seek(start)
            text = f.read(end - start).replace(b'\r', b'').decode('utf-8')
            word_freqs = self._split_special_tokens(text)
        return word_freqs

    def _pre_tokenization(self, file_path: str) -> Counter:
        """Main pre-tokenization entry"""
        word_freqs = Counter()
        size_bytes = os.path.getsize(file_path)
        # Small file: read entirely
        if size_bytes < 1024 * 100:
            with open(file_path, "rb") as f:
                chunk = f.read().replace(b'\r', b'').decode('utf-8')
                word_freqs = self._split_special_tokens(chunk)
        else:
            # Large file: split by boundaries, parallel processing
            num_process = mp.cpu_count() - 1
            with open(file_path, "rb") as f:
                boundaries = find_chunk_boundaries(f, num_process, "<|endoftext|>".encode("utf-8"))
            boundaries_pairs = list(zip(boundaries[:-1], boundaries[1:]))
            args_iterable = ((file_path, start, end) for start, end in boundaries_pairs)
            num_workers = max(1, num_process)
            with mp.Pool(num_workers) as pool:
                for token_counts in pool.imap_unordered(self._process_sub_text, args_iterable):
                    word_freqs.update(token_counts)

        words = []
        freqs = []
        for seq, freq in word_freqs.items():
            words.append(list(seq))
            freqs.append(freq)

        return words, freqs

    def _init_count_pairs(self, words: list[list[int]], freqs: list[int]) -> Counter:
        pair_counts = Counter()

        for word, freq in zip(words, freqs):
            for pair in zip(word, word[1:]):
                pair_counts[pair] += freq

        return pair_counts
    
    def _get_most_frequent_pair(self, pair_counts):
        max_freq = max(pair_counts.values())
        candidates = [pair for pair, freq in pair_counts.items() if freq == max_freq]
        
        max_pair = max(
            candidates,
            key=lambda p: (self.vocab[p[0]], self.vocab[p[1]])
        )

        return max_pair

     
    def _merge_pair(self, words: list[list[int]], freqs: list[int], pair_counts, pair: Tuple[int, int], merge_id: int):
        """Merge a specific pair in a word"""
        old_pairs = defaultdict(int)
        new_pairs = defaultdict(int)

        pair_counts.pop(pair, None)
        p0, p1 = pair

        candidate_indices = [i for i, w in enumerate(words) if p0 in w and p1 in w]
        for index in candidate_indices:
            word = words[index]
            freq = freqs[index]

            new_word = []
            new_word_append = new_word.append

            i = 0
            length = len(word)
            while i < length:
                if i < length - 1 and word[i] == p0 and word[i + 1] == p1:
                    # 左邻居
                    if i > 0:
                        left = word[i - 1]
                        old_pairs[(left, p0)] += freq
                        new_pairs[(left, merge_id)] += freq
                    # 右邻居
                    if i + 2 < length:
                        right = word[i + 2]
                        old_pairs[(p1, right)] += freq
                        new_pairs[(merge_id, right)] += freq

                    new_word_append(merge_id)
                    i += 2
                else:
                    new_word_append(word[i])
                    i += 1
            words[index] = new_word

        for old_pair, old_freq in old_pairs.items():
            if old_pair in pair_counts:
                pair_counts[old_pair] -= old_freq
                if pair_counts[old_pair] <= 0:
                    del pair_counts[old_pair]
            # 如果 pair 不存在，则无需操作

        # 加上 new_pairs
        for new_pair, new_freq in new_pairs.items():
            pair_counts[new_pair] = pair_counts.get(new_pair, 0) + new_freq

        return words, freqs, pair_counts
        
        
    def train(self, input_path, vocab_size, special_tokens):
        self._init_bpe(special_tokens)

        words, freqs = self._pre_tokenization(input_path)
        
        pair_counts = self._init_count_pairs(words, freqs)
        
        # pbar = tqdm(total=vocab_size, desc="Training BPE", unit="new token")
        while self.next_id < vocab_size:
            if not pair_counts:
                break

            most_frequent_pair = self._get_most_frequent_pair(pair_counts)
            bytes1, bytes2 = self.vocab[most_frequent_pair[0]], self.vocab[most_frequent_pair[1]]
            new_token = bytes1 + bytes2
 
            if new_token not in self.bytes_to_id:
                self.vocab[self.next_id] = new_token
                self.bytes_to_id[new_token] = self.next_id
                self.merges.append((bytes1, bytes2))
                merge_id = self.next_id
                self.next_id += 1
                # pbar.update(1)
            else:
                merge_id = self.bytes_to_id[new_token]

            words, freqs, pair_counts = self._merge_pair(words, freqs, pair_counts, most_frequent_pair, merge_id)
        # pbar.close()
        return self.vocab, self.merges


def main():
    file_path: str = "./data/TinyStoriesV2-GPT4-train.txt"
    vocab_size = 10000
    special_tokens=["<|endoftext|>"]

    bpe1 = BPE()
    vocab1, merges1 = bpe1.train(file_path, vocab_size, special_tokens)


import cProfile
import pstats
if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()

    main()  # 你的主函数

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats("tottime")  # 按函数自身耗时排序
    stats.print_stats(20)        # 打印前 20 个耗时函数
