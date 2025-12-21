#!/usr/bin/env python
"""Test tie-breaking logic"""
from collections import Counter

# Test case: same frequency pairs
pair_cnt = Counter()
pair_cnt[(32, 116)] = 100  # b' t' -> (b' ', b't')
pair_cnt[(32, 97)] = 100   # b' a' -> (b' ', b'a')
pair_cnt[(104, 101)] = 100 # b'he' -> (b'h', b'e')

print("Pairs with same frequency:")
for pair, freq in sorted(pair_cnt.items()):
    print(f"  {pair} (freq={freq}) -> {(bytes([pair[0]]), bytes([pair[1]]))}")

# Method 1: tie-break by token-id tuple
print("\nMethod 1: max with (freq, token_id_pair)")
selected1 = max(pair_cnt.items(), key=lambda kv: (kv[1], kv[0]))
print(f"  Selected: {selected1[0]} -> {(bytes([selected1[0][0]]), bytes([selected1[0][1]]))}")

# Method 2: tie-break by bytes tuple
print("\nMethod 2: max with (freq, bytes_pair)")
vocab = {i: bytes([i]) for i in range(256)}
selected2 = max(pair_cnt.items(), key=lambda kv: (kv[1], (vocab[kv[0][0]], vocab[kv[0][1]])))
print(f"  Selected: {selected2[0]} -> {(vocab[selected2[0][0]], vocab[selected2[0][1]])}")

# Check expected order from test
print("\nExpected order from test:")
expected = [(b' ', b't'), (b' ', b'a'), (b'h', b'e')]
for e in expected:
    print(f"  {e}")
print(f"  -> This suggests: {expected[0]} should be selected first")
