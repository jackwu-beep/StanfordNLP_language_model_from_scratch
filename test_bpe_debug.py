#!/usr/bin/env python3
"""Debug BPE implementation"""
import regex as re
from collections import Counter
from tests.adapters import run_train_bpe

# 创建一个超小的测试文件
test_text = "aaaa bb cc"
test_file = "/tmp/test_bpe_tiny.txt"
with open(test_file, 'w', encoding='utf-8') as f:
    f.write(test_text)

print(f"Test text: {test_text!r}")
print("\nRunning BPE training with vocab_size=260...")

vocab, merges = run_train_bpe(test_file, vocab_size=260, special_tokens=[])

print(f"\nVocab size: {len(vocab)}")
print(f"Number of merges: {len(merges)}")
print("\nFirst 10 merges:")
for i, (a, b) in enumerate(merges[:10]):
    combined = a + b
    print(f"  {i}: {a!r} + {b!r} = {combined!r}")

# 验证手动计算
print("\n--- Manual verification ---")
print("Initial tokens for 'aaaa': [97, 97, 97, 97]")
print("Initial pairs: (97,97) appears 3 times")
print("After merge 0: vocab[256] = b'aa'")
print("  'aaaa' becomes [256, 256] (2 'aa' tokens)")
print("  New pair: (256, 256) appears 1 time")
print("\nExpected merge sequence:")
print("  0: (97, 97) -> b'aa'")
print("  1: (256, 256) -> b'aaaa'")
print("  2: (98, 98) -> b'bb'")
print("  3: (99, 99) -> b'cc'")
