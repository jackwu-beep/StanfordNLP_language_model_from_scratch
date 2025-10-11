import os
import multiprocessing as mp
from collections import defaultdict, Counter
from typing import List, Tuple, BinaryIO
import re
import regex
from tqdm import tqdm

PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""
PAT_RE = None
_SPLIT_RE = None
_SPLIT_TOKENS = None


import mmap
def find_chunk_boundaries(file_path: str, num_chunks: int, split_special_token: bytes) -> list[int]:
    with open(file_path, "rb") as file:
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        chunk_size = max(1, file_size // num_chunks)
        boundaries = [0]
        with mmap.mmap(file.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
            for i in range(1, num_chunks):
                pos = i * chunk_size
                if pos >= file_size:
                    break
                # 往后找最近的 special token
                found = mm.find(split_special_token, pos)
                boundaries.append(found if found != -1 else file_size)
            boundaries.append(file_size)
        # 去重（已递增，无需排序）
        uniq = [boundaries[0]]
        for b in boundaries[1:]:
            if b != uniq[-1]:
                uniq.append(b)
    return uniq


def worker_init(pat: str, special_tokens: list[str]):
    global _PAT_RE, _SPLIT_TOKENS, _SPLIT_RE
    _PAT_RE = regex.compile(pat, flags=regex.UNICODE)
    _SPLIT_TOKENS = special_tokens or []
    if len(_SPLIT_TOKENS) > 1:
        _SPLIT_RE = re.compile("|".join(re.escape(t) for t in _SPLIT_TOKENS))
    else:
        _SPLIT_RE = None


def split_special_tokens(text: str) -> Counter:
    """Split text by special tokens, remove empty strings"""
    if not _SPLIT_TOKENS:
        parts = [text]
    elif len(_SPLIT_TOKENS) == 1:
        parts = text.split(_SPLIT_TOKENS[0])
    else:
        parts = [seg for seg in _SPLIT_RE.split(text) if seg]

    c = Counter()
    update = c.update
    findall = _PAT_RE.findall
    for part in parts:
        update(findall(part))
    return c


def word_to_bytes(word_freqs: dict[str, int]):
    bytes_seq = []
    freqs = []

    bytes_seq_append = bytes_seq.append
    freqs_append = freqs.append
    for word, freq in word_freqs.items():
        bytes_seq_append(tuple(word.encode('utf-8')))
        freqs_append(freq)
    
    return bytes_seq, freqs


def process_sub_text(args) -> Counter:
    """Worker function for multiprocessing"""
    file_path, start, end = args
    word_freqs = Counter()
    with open(file_path, "rb") as f:
        f.seek(start)
        text = f.read(end - start).replace(b'\r', b'').decode('utf-8')
        word_freqs = split_special_tokens(text)
    return word_freqs


class BPE:
    def __init__(self, ):
        self.vocab = {}
        self.bytes_to_id = {}
        self.merges = []
        self.next_id = 0

    def _init_bpe(self, special_tokens: List[str] = None):
        for i in range(256):
            byte_token = bytes([i])
            self.vocab[self.next_id] = byte_token
            self.bytes_to_id[byte_token] = self.next_id
            self.next_id += 1
                
        self.special_tokens = special_tokens or ["<|endoftext|>"]
        for token in self.special_tokens:
            if token not in self.bytes_to_id:
                byte_token = token.encode('utf-8')
                self.vocab[self.next_id] = byte_token
                self.bytes_to_id[byte_token] = self.next_id
                self.next_id += 1
            

    def _pre_tokenization(self, file_path: str, special_tokens: list[str]) -> Counter:
        """Main pre-tokenization entry"""
        word_freqs = Counter()
        size_bytes = os.path.getsize(file_path)
        # Small file: read entirely
        if size_bytes < 1024 * 1024:
            with open(file_path, "rb") as f:
                chunk = f.read().replace(b'\r', b'').decode('utf-8')
                worker_init(PAT, special_tokens)
                word_freqs = split_special_tokens(chunk)
        else:
            # Large file: split by boundaries, parallel processing
            num_process = mp.cpu_count() - 1
            
            boundaries = find_chunk_boundaries(file_path, 4*num_process, "<|endoftext|>".encode("utf-8"))
            boundaries_pairs = list(zip(boundaries[:-1], boundaries[1:]))

            args_iterable = ((file_path, start, end) for start, end in boundaries_pairs)
            num_workers = max(1, num_process)
            with mp.Pool(
                num_workers,
                initializer=worker_init,
                initargs=(PAT, special_tokens)  # 把模式与特殊 token 传给子进程做一次初始化
            ) as pool:
                for word_counts in pool.imap_unordered(process_sub_text, args_iterable, chunksize=1):
                    word_freqs.update(word_counts)

        bytes_seq, freqs = word_to_bytes(word_freqs)
        from array import array
        bytes_seq = [array('H', seq) for seq in bytes_seq]

        return bytes_seq, freqs
    

    def _init_count_pairs(self, words: list[list[int]], freqs: list[int]) -> Counter:
        pair_counts = Counter()
        self.pair_to_idxs = defaultdict(set)
        for i, (w, f) in enumerate(zip(words, freqs)):
            for a, b in zip(w, w[1:]):
                p = (a, b)
                pair_counts[p] += f
                self.pair_to_idxs[p].add(i)
        return pair_counts
    
    def _get_most_frequent_pair(self, pair_counts):
        max_freq = max(pair_counts.values())
        candidates = [pair for pair, freq in pair_counts.items() if freq == max_freq]
        
        max_pair = max(
            candidates,
            key=lambda p: (self.vocab[p[0]], self.vocab[p[1]])
        )

        return max_pair

     
    def _merge_pair(self, words, freqs, pair_counts, pair, merge_id):
        old_pairs = defaultdict(int); new_pairs = defaultdict(int)
        p0, p1 = pair
        pair_counts.pop(pair, None)

        idxs = list(self.pair_to_idxs.pop(pair, ()))
        # changed_pairs = Counter()

        for idx in idxs:
            word, freq = words[idx], freqs[idx]

            # 从倒排表里移除该词旧 pair
            for a,b in zip(word, word[1:]):
                s = self.pair_to_idxs.get((a,b))
                if s is not None:
                    s.discard(idx)
                    if not s: self.pair_to_idxs.pop((a,b), None)

            # 实际合并
            new_word = []
            append = new_word.append
            i = 0; L = len(word)
            while i < L:
                if i+1 < L and word[i]==p0 and word[i+1]==p1:
                    if i > 0:
                        left = word[i-1]
                        old_pairs[(left,p0)] += freq
                        new_pairs[(left,merge_id)] += freq
                    if i+2 < L:
                        right = word[i+2]
                        old_pairs[(p1,right)] += freq
                        new_pairs[(merge_id,right)] += freq
                    append(merge_id); i += 2
                else:
                    append(word[i]); i += 1

            words[idx] = new_word
            # 把新词的 pair 放回倒排表
            for a,b in zip(new_word, new_word[1:]):
                self.pair_to_idxs[(a,b)].add(idx)

        # 更新 pair_counts（先减旧，再加新），并收集 changed_pairs
        for p,f in old_pairs.items():
            if p in pair_counts:
                pair_counts[p] -= f
                if pair_counts[p] <= 0: del pair_counts[p]
            # if p in pair_counts: changed_pairs[p] = pair_counts[p]

        for p,f in new_pairs.items():
            pair_counts[p] = pair_counts.get(p,0)+f
            # changed_pairs[p] = pair_counts[p]

        return words, freqs, pair_counts
        
        
    def train(self, input_path, vocab_size, special_tokens):
        self._init_bpe(special_tokens)

        words, freqs = self._pre_tokenization(input_path, special_tokens)
        
        pair_counts = self._init_count_pairs(words, freqs)
        
        # pbar = tqdm(total=vocab_size - self.next_id, desc="Training BPE", unit="new token")
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
    stats.print_stats(10)
