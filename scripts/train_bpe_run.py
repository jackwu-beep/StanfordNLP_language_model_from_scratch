#!/usr/bin/env python3
"""
train_bpe_run.py

Standalone script to train a byte-level BPE tokenizer (simple, pedagogical implementation)
on a corpus and visualize training progress.

Features:
- Train on an input text file with a given `vocab_size` and `special_tokens`.
- Records per-merge metrics (time, selected pair freq, vocab size).
- Saves `vocab` (as JSON-like mapping with bytes hex encoding) and `merges` (bytes pairs) to `out_dir`.
- Produces PNG plots showing progress (most-common frequency vs merges, time vs merges).

Notes:
- This script purposely implements a simple (clear) version of the BPE training loop similar to the working implementation in `tests/adapters.py`.
- For large corpora (OpenWebText, TinyStories full) CPU+memory/time can be large; use sample files or ensure sufficient RAM.

Example usage:
python3 scripts/train_bpe_run.py \
    --input data/TinyStoriesV2-GPT4-train.txt \
    --vocab-size 10000 \
    --special-tokens "<|endoftext|>" \
    --out-dir outputs/tinystories_10k \
    --plot

python3 scripts/train_bpe_run.py --input data/owt_train.txt --vocab-size 32000 --out-dir outputs/owt_32k --plot

"""

from __future__ import annotations

import argparse
import os
import time
import json
from collections import Counter
import regex as re
from collections import defaultdict
from typing import Dict, List, Tuple
import multiprocessing as mp
import gzip

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None

try:
    import psutil
except Exception:
    psutil = None


def split_by_special_tokens(text: str, special_tokens: List[str]) -> List[str]:
    if not special_tokens:
        return [text]
    escaped_tokens = [re.escape(token) for token in special_tokens]
    escaped_tokens.sort(key=len, reverse=True)
    pattern = '(' + '|'.join(escaped_tokens) + ')'
    # keep special tokens as separate parts
    parts = re.split(pattern, text)
    return parts


PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""
pat = re.compile(PAT)


def _count_chunk(chunk_text: str, special_tokens: List[str]) -> Counter:
    """Top-level helper for multiprocessing: count pretokenized words in a text chunk."""
    cnt = Counter()
    parts = split_by_special_tokens(chunk_text, special_tokens)
    for part in parts:
        for m in pat.finditer(part):
            cnt[m.group()] += 1
    return cnt


def save_word_counts_file(word_counts: Counter, out_path: str) -> None:
    """Save word counts to a gzip JSON-lines file. Each line: [word, count]"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, 'wt', encoding='utf-8') as f:
        for w, c in word_counts.items():
            json.dump([w, c], f, ensure_ascii=False)
            f.write('\n')


def load_word_counts_file(in_path: str) -> Counter:
    """Load word counts from gzip JSON-lines file into a Counter."""
    cnt = Counter()
    with gzip.open(in_path, 'rt', encoding='utf-8') as f:
        for line in f:
            try:
                w, c = json.loads(line)
                cnt[w] = c
            except Exception:
                continue
    return cnt


def train_bpe_with_progress(
    input_path: str,
    vocab_size: int,
    special_tokens: List[str],
    max_iters: int | None = None,
    workers: int | None = None,
    word_counts: Counter | None = None,
):
    """Train BPE and return (vocab, merges, metrics)

    metrics: list of dicts per merge with keys: iter, elapsed, freq, vocab_size
    """
    t0 = time.time()

    # initial vocab: 0..255 -> single-byte
    vocab: Dict[int, bytes] = {i: bytes([i]) for i in range(256)}
    for token in special_tokens:
        vocab[len(vocab)] = token.encode('utf-8')
    merges: List[Tuple[bytes, bytes]] = []
    # build word_counts (pretokenize) using multiprocessing over file chunks
    CHUNK_LINES = 5000
    if word_counts is None:
        word_counts = Counter()
        if workers is None:
            workers = max(1, (mp.cpu_count() or 1) - 1)

        # stream file and process in chunks
        if workers <= 1:
            # single-process
            with open(input_path, 'r', encoding='utf-8') as f:
                buf_lines = []
                for line in f:
                    buf_lines.append(line)
                    if len(buf_lines) >= CHUNK_LINES:
                        chunk_text = ''.join(buf_lines)
                        word_counts.update(_count_chunk(chunk_text, special_tokens))
                        buf_lines = []
                if buf_lines:
                    word_counts.update(_count_chunk(''.join(buf_lines), special_tokens))
        else:
            pool = mp.Pool(processes=workers)
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    buf_lines = []
                    async_results = []
                    for line in f:
                        buf_lines.append(line)
                        if len(buf_lines) >= CHUNK_LINES:
                            chunk_text = ''.join(buf_lines)
                            async_results.append(pool.apply_async(_count_chunk, (chunk_text, special_tokens)))
                            buf_lines = []
                    if buf_lines:
                        async_results.append(pool.apply_async(_count_chunk, (''.join(buf_lines), special_tokens)))

                    for r in async_results:
                        word_counts.update(r.get())
            finally:
                pool.close()
                pool.join()

    # build word_tokens from unique pretokenized words
    word_tokens: Dict[str, List[int]] = {}
    for w in word_counts.keys():
        word_tokens[w] = list(w.encode('utf-8'))

    # initial pair counts (token-id pairs)
    pair_cnt: Counter = Counter()
    for w, tokens in word_tokens.items():
        c = word_counts[w]
        for i in range(len(tokens) - 1):
            pair = (tokens[i], tokens[i + 1])
            pair_cnt[pair] += c

    metrics = []
    it = 0
    start = time.time()
    
    # guard for repeated selection of same pair
    last_selected = None
    repeat_count = 0
    REPEAT_THRESHOLD = 8
    # main loop
    while len(vocab) < vocab_size:
        if max_iters is not None and it >= max_iters:
            break
        if not pair_cnt:
            break

        # choose most frequent pair; break ties by (bytes_a, bytes_b) tuple lexicographic (largest)
        most_common_pair, freq = max(
            pair_cnt.items(), key=lambda kv: (kv[1], (vocab[kv[0][0]], vocab[kv[0][1]]))
        )
        if freq == 0:
            break

        token_a, token_b = most_common_pair
        new_id = len(vocab)
        vocab[new_id] = vocab[token_a] + vocab[token_b]
        merges.append((vocab[token_a], vocab[token_b]))

        # record metric before modifications
        elapsed = time.time() - start
        metrics.append({
            'iter': it,
            'elapsed': elapsed,
            'freq': int(freq),
            'vocab_size': len(vocab),
            'most_common_pair': (token_a, token_b),
        })

        # detect repeated selection of the same pair; if it repeats many times
        # this likely indicates our incremental update drifted — rebuild counts
        if last_selected == most_common_pair:
            repeat_count += 1
        else:
            repeat_count = 0
        last_selected = most_common_pair
        if repeat_count >= REPEAT_THRESHOLD:
            # rebuild pair_cnt from current word_tokens to correct drift
            pair_cnt = Counter()
            for w, tokens in word_tokens.items():
                c = word_counts[w]
                for i in range(len(tokens) - 1):
                    pair_cnt[(tokens[i], tokens[i + 1])] += c
            # reset repeat guard
            repeat_count = 0
        # replace in each word (non-overlap greedy left-to-right) and update counts
        for w, token_ids in list(word_tokens.items()):
            c = word_counts[w]
            i = 0
            new_token_ids = []
            while i < len(token_ids):
                if i < len(token_ids) - 1 and token_ids[i] == token_a and token_ids[i + 1] == token_b:
                    # remove old pairs counts
                    if i > 0:
                        old_left = (token_ids[i - 1], token_a)
                        pair_cnt[old_left] -= c
                    if i + 2 < len(token_ids):
                        old_right = (token_b, token_ids[i + 2])
                        pair_cnt[old_right] -= c
                    pair_cnt[most_common_pair] -= c

                    # add new pairs
                    if i > 0:
                        new_left = (token_ids[i - 1], new_id)
                        pair_cnt[new_left] += c
                    if i + 2 < len(token_ids):
                        new_right = (new_id, token_ids[i + 2])
                        pair_cnt[new_right] += c

                    new_token_ids.append(new_id)
                    i += 2
                else:
                    new_token_ids.append(token_ids[i])
                    i += 1
            word_tokens[w] = new_token_ids
        # clean up non-positive counts to avoid clutter and accidental selection
        to_delete = [p for p, v in list(pair_cnt.items()) if v <= 0]
        for p in to_delete:
            pair_cnt.pop(p, None)
        
        it += 1

    total_time = time.time() - t0

    # summary
    summary = {
        'total_time': total_time,
        'total_merges': len(merges),
        'final_vocab_size': len(vocab),
        'longest_token_len': max((len(b) for b in vocab.values()), default=0),
    }

    # optional memory
    if psutil is not None:
        p = psutil.Process()
        summary['rss_bytes'] = p.memory_info().rss

    return vocab, merges, metrics, summary


def save_vocab_and_merges(vocab: Dict[int, bytes], merges: List[Tuple[bytes, bytes]], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    # save vocab as json mapping id -> hex string for bytes (easier to inspect)
    vocab_out = {str(k): v.hex() for k, v in vocab.items()}
    with open(os.path.join(out_dir, 'vocab.json'), 'w', encoding='utf-8') as f:
        json.dump(vocab_out, f, indent=2, ensure_ascii=False)

    # save merges as newline-separated byte-hex pairs
    with open(os.path.join(out_dir, 'merges.txt'), 'w', encoding='utf-8') as f:
        for a, b in merges:
            f.write(a.hex() + ' ' + b.hex() + '\n')


def plot_metrics(metrics: List[dict], out_dir: str):
    if plt is None:
        print('matplotlib not available; skipping plots')
        return
    if not metrics:
        print('no metrics to plot')
        return
    iters = [m['iter'] for m in metrics]
    freqs = [m['freq'] for m in metrics]
    vocab_sizes = [m['vocab_size'] for m in metrics]
    elapsed = [m['elapsed'] for m in metrics]

    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(iters, freqs, label='most_common_freq', color='C0')
    ax1.set_xlabel('merge iteration')
    ax1.set_ylabel('most common pair freq', color='C0')
    ax1.tick_params(axis='y', labelcolor='C0')

    ax2 = ax1.twinx()
    ax2.plot(iters, vocab_sizes, label='vocab_size', color='C1')
    ax2.set_ylabel('vocab size', color='C1')
    ax2.tick_params(axis='y', labelcolor='C1')

    fig.tight_layout()
    plt.title('BPE training progress')
    plt.savefig(os.path.join(out_dir, 'progress_freq_vocab.png'))
    plt.close(fig)

    # time plot
    fig2, ax = plt.subplots(figsize=(10, 4))
    ax.plot(iters, elapsed)
    ax.set_xlabel('merge iteration')
    ax.set_ylabel('elapsed seconds')
    ax.set_title('Elapsed time per merge iteration')
    fig2.tight_layout()
    plt.savefig(os.path.join(out_dir, 'progress_time.png'))
    plt.close(fig2)


def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='Path to input text file')
    parser.add_argument('--vocab-size', type=int, required=True)
    parser.add_argument('--special-tokens', nargs='*', default=[], help='List of special tokens (literal strings)')
    parser.add_argument('--out-dir', default='outputs/bpe_run')
    parser.add_argument('--plot', action='store_true')
    parser.add_argument('--max-iters', type=int, default=None, help='Optional cap on merges for quick runs')
    parser.add_argument('--workers', type=int, default=None, help='Number of worker processes for pretokenization')
    parser.add_argument('--save-word-counts', default=None, help='Path to save pretokenized word counts (gzip jsonl) and exit')
    parser.add_argument('--load-word-counts', default=None, help='Path to load pretokenized word counts (gzip jsonl) and skip pretokenization')
    args = parser.parse_args()

    print('Starting BPE training')
    print('input=', args.input)
    print('vocab_size=', args.vocab_size)
    print('special_tokens=', args.special_tokens)
    print('out_dir=', args.out_dir)

    # If requested, pretokenize and save counts then exit
    if args.save_word_counts:
        print('Pretokenizing and saving word counts to', args.save_word_counts)
        CHUNK_LINES = 5000
        workers = args.workers if args.workers is not None else max(1, (mp.cpu_count() or 1) - 1)
        word_counts = Counter()
        if workers <= 1:
            with open(args.input, 'r', encoding='utf-8') as f:
                buf_lines = []
                for line in f:
                    buf_lines.append(line)
                    if len(buf_lines) >= CHUNK_LINES:
                        word_counts.update(_count_chunk(''.join(buf_lines), args.special_tokens))
                        buf_lines = []
                if buf_lines:
                    word_counts.update(_count_chunk(''.join(buf_lines), args.special_tokens))
        else:
            pool = mp.Pool(processes=workers)
            try:
                with open(args.input, 'r', encoding='utf-8') as f:
                    buf_lines = []
                    async_results = []
                    for line in f:
                        buf_lines.append(line)
                        if len(buf_lines) >= CHUNK_LINES:
                            chunk_text = ''.join(buf_lines)
                            async_results.append(pool.apply_async(_count_chunk, (chunk_text, args.special_tokens)))
                            buf_lines = []
                    if buf_lines:
                        async_results.append(pool.apply_async(_count_chunk, (''.join(buf_lines), args.special_tokens)))

                    for r in async_results:
                        word_counts.update(r.get())
            finally:
                pool.close()
                pool.join()

        save_word_counts_file(word_counts, args.save_word_counts)
        print('Saved word counts to', args.save_word_counts)
        return

    # If load-word-counts provided, load and pass to trainer
    load_counts = None
    if args.load_word_counts:
        print('Loading pretokenized word counts from', args.load_word_counts)
        load_counts = load_word_counts_file(args.load_word_counts)

    vocab, merges, metrics, summary = train_bpe_with_progress(
        args.input, args.vocab_size, args.special_tokens, max_iters=args.max_iters, workers=args.workers, word_counts=load_counts
    )

    print('\nTraining summary:')
    for k, v in summary.items():
        print(f'  {k}: {v}')

    save_vocab_and_merges(vocab, merges, args.out_dir)
    print(f'Saved vocab+merges to {args.out_dir}')

    if args.plot:
        plot_metrics(metrics, args.out_dir)
        print('Saved progress plots')


if __name__ == '__main__':
    main()
