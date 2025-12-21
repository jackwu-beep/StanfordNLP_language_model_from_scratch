#!/usr/bin/env python3
"""Debug pair counting"""
import regex as re
from collections import Counter

test_text = "aaaa bb"
PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""
pat = re.compile(PAT)

vocab = {i: bytes([i]) for i in range(256)}
word_tokens = {}
word_counts = Counter()

for match in pat.finditer(test_text):
    word_str = match.group()
    word_counts[word_str] += 1
    if word_str not in word_tokens:
        word_tokens[word_str] = list(word_str.encode('utf-8'))

print("Initial state:")
for word_str, token_ids in word_tokens.items():
    print(f"  {word_str!r}: {token_ids}")

# 统计初始pair
pair_cnt = Counter()
for word_str, token_ids in word_tokens.items():
    count = word_counts[word_str]
    for i in range(len(token_ids) - 1):
        pair = (token_ids[i], token_ids[i + 1])
        pair_cnt[pair] += count

print("\nInitial pair counts:")
for pair, cnt in sorted(pair_cnt.items(), key=lambda x: -x[1]):
    print(f"  {pair} ({vocab[pair[0]]!r}, {vocab[pair[1]]!r}): {cnt}")

# 模拟第一次合并
print("\n--- After merging (97, 97) -> 256 ---")
token_a, token_b = 97, 97
new_token_id = 256
vocab[256] = b'aa'

for word_str, token_ids in word_tokens.items():
    count = word_counts[word_str]
    i = 0
    new_token_ids = []
    
    print(f"\nProcessing {word_str!r}: {token_ids}")
    
    while i < len(token_ids):
        if i < len(token_ids) - 1 and token_ids[i] == token_a and token_ids[i + 1] == token_b:
            print(f"  Match at i={i}: ({token_ids[i]}, {token_ids[i+1]})")
            
            # 删除旧pair
            if i > 0:
                old_left = (token_ids[i - 1], token_a)
                print(f"    Remove left pair: {old_left}")
                pair_cnt[old_left] -= count
            if i + 2 < len(token_ids):
                old_right = (token_b, token_ids[i + 2])
                print(f"    Remove right pair: {old_right}")
                pair_cnt[old_right] -= count
            pair_cnt[(token_a, token_b)] -= count
            print(f"    Remove center pair: {(token_a, token_b)}")
            
            new_token_ids.append(new_token_id)
            
            # 添加新pair
            if len(new_token_ids) > 1:
                new_left = (new_token_ids[-2], new_token_id)
                print(f"    Add new left pair: {new_left}")
                pair_cnt[new_left] += count
            if i + 2 < len(token_ids):
                new_right = (new_token_id, token_ids[i + 2])
                print(f"    Add new right pair: {new_right}")
                pair_cnt[new_right] += count
            
            i += 2
        else:
            new_token_ids.append(token_ids[i])
            i += 1
    
    print(f"  New tokens: {new_token_ids}")
    word_tokens[word_str] = new_token_ids

print("\nPair counts after merge:")
for pair, cnt in sorted(pair_cnt.items(), key=lambda x: -x[1]):
    if cnt > 0:
        a_bytes = vocab.get(pair[0], f"token_{pair[0]}".encode())
        b_bytes = vocab.get(pair[1], f"token_{pair[1]}".encode())
        print(f"  {pair} ({a_bytes!r}, {b_bytes!r}): {cnt}")
