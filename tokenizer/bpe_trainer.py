import os
from pathlib import Path
import regex as re


def find_max_bp(pretokenized_count):
    # Count byte pairs
    bp_counter = {}
    for bytes_tuple, count in pretokenized_count.items():
        for i in range(len(bytes_tuple) - 1):
            bp = (bytes_tuple[i], bytes_tuple[i+1])
            bp_counter[bp] = bp_counter.get(bp, 0) + count
    max_bp, max_count = (0, 0), 0
    for bp, bp_count in bp_counter.items():
        if bp_count > max_count:
            max_bp = bp
            max_count = bp_count
        if bp_count == max_count and bp > max_bp:
            max_bp = bp
            max_count = bp_count
    return max_bp, max_count


def concat_merge(merge):
    part1 = bytes([merge[0]]) if isinstance(merge[0], int) else merge[0]
    part2 = bytes([merge[1]]) if isinstance(merge[1], int) else merge[1]
    return part1 + part2


def merge_bp(pretokenized_count: dict[tuple[bytes], int], merge):
    new_pretokenized_count = {}
    merged_bytes = concat_merge(merge)
    for pt, count in pretokenized_count.items():
        new_pt = []
        i = 0
        while i < len(pt):
            if i < len(pt) - 1 and (pt[i], pt[i+1]) == merge:
                new_pt.append(merged_bytes)
                i = i + 2
            else:
                new_pt.append(pt[i])
                i = i + 1
        new_pretokenized_count[tuple(new_pt)] = count
    return new_pretokenized_count


def remove_special_tokens(content: str, special_tokens: list[str]) -> list[str]:
    pattern = '|'.join(re.escape(d) for d in special_tokens)
    return re.split(pattern, content)


PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""


def pretokenizer(content: str, special_tokens: list[str]) -> dict[tuple[bytes], int]:
    docs = remove_special_tokens(content, special_tokens)
    counter = {}
    for doc in docs:
        matches = re.finditer(PAT, doc)

        for match in matches:
            text = tuple(match.group().encode('utf8'))
            counter[text] = counter.get(text, 0) + 1
    return counter


def init_vocab(special_tokens: list[str]) -> dict[int, bytes]:
    vocab = {}
    for i in range(256):
        vocab[i] = bytes([i])
    for st in special_tokens:
        idx = len(vocab)
        vocab[idx] = st.encode('utf8')
    return vocab


def train_bpe(
        input_path: str | os.PathLike,
        vocab_size: int,
        special_tokens: list[str]
) -> tuple[dict[int, bytes], list[tuple[bytes, bytes]]]:
    vocab = init_vocab(special_tokens)
    merges = []

    path = Path(input_path)
    content = ''
    with path.open('+r') as f:
        content = f.read()
    pretokenized_count = pretokenizer(content, special_tokens)
    for _ in range(6):
        max_bp, max_count = find_max_bp(pretokenized_count)
        # only merge and update when max_count > 1.
        if max_count > 1:
            vocab_size = len(vocab)
            vocab[vocab_size] = concat_merge(max_bp)
            merges.append(max_bp)
            pretokenized_count = merge_bp(pretokenized_count, max_bp)
        else:
            break
    return vocab, merges


if __name__ == "__main__":
    # input_path = './data/TinyStoriesV2-GPT4-valid.txt'
    input_path = './tokenizer/bpe_example.txt'
    special_tokens = ['<|endoftext|>']
    vocab_size = 1000
    vocab, merges = train_bpe(input_path, vocab_size, special_tokens)
    print(vocab)
    print(merges)
