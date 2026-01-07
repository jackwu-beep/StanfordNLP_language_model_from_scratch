# Byte-pair encoding is a trade-off between the vocab size and the encoded sequence length.
# Larger vocab sizes can lead to shorter encoded sequences but may increase memory usage.
# This trade-off affects both compression ratio and computational efficiency.

def decode_utf8_bytes_to_str_wrong(bytestring: bytes):
    return "".join([bytes([b]).decode("utf-8") for b in bytestring])

def decode_utf8_bytes_to_str_correct(bytestring: bytes) -> str:
    return bytestring.decode("utf-8")


# GPT-2 tokenizer
PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""
import regex as re

print(re.findall(PAT, "some text that i'll pre-tokenize"))
print(re.findall(PAT, "Hello,  world!"))

for tok in re.finditer(PAT, "hangjian li"):
    print(tok.group().strip())

# if __name__ == "__main__":
#     test_bytes = "hello world 🌍".encode("utf-8")
#     result = decode_utf8_bytes_to_str_correct(test_bytes)
#     print(f"Input: {test_bytes}")
#     print(f"Output: {result}")
#     print(f"Expected: hello world 🌍")
#     print(f"Match: {result == 'hello world 🌍'}")
    
#     # Test with a multi-byte sequence
#     multi_byte = "café".encode("utf-8")
#     result2 = decode_utf8_bytes_to_str_correct(multi_byte)
#     print(f"\nMulti-byte test:")
#     print(f"Input: {multi_byte}")
#     print(f"Output: {result2}")
#     print(f"Expected: café")
#     print(f"Match: {result2 == 'café'}")
