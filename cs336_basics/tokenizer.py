import regex as re
from typing import Iterable, Iterator, Protocol


# reference: https://github.com/openai/tiktoken/pull/234/files
GPT2_PRE_TOKENIZER_REGEX = re.compile(r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+""")


def split_text_to_words(text: str) -> list[str]:
    return GPT2_PRE_TOKENIZER_REGEX.findall(text)


def word_to_bytes(word: str) -> list[bytes]:
    return list(bytes([b]) for b in word.encode("utf-8"))


class Tokenizer(Protocol):
    def encode(self, string: str) -> list[int]:
        """
        Encode a string into tokens.

        Args:
            string (str): the orginal string.

        Returns:
            list[int]: tokens encoded from the original string.
        """
        ...
    
    def encode_iterable(self, iterable: Iterable[str]) -> Iterator[int]:
        """
        Encode a string into tokens, optimized for memory efficiency by yielding as a generator.

        Args:
            iterable (Iterable[str]): the orginal string.

        Yields:
            Iterator[int]: tokens encoded from the original string.
        """
        ...
    
    def decode(self, tokens: list[int]) -> str:
        """
        Decode a list of tokens to a string.

        Args:
            indices (list[int]): tokens to decode.

        Returns:
            str: decoded string.
        """
        ...


class BPETokenizer(Tokenizer):
    """
    Byte-Pair Encoding Tokenizer.
    """
    def __init__(self, vocab: dict[int, bytes], merges: list[tuple[bytes, bytes]], special_tokens: list[str] | None):
        self._vocab: dict[int, bytes] = vocab # index -> bytes
        self._merges: set[tuple[bytes, bytes]] = set(merges)  # (byte_1, byte_2) to merge
        self._special_tokens: list[str] = sorted(special_tokens, key=len, reverse=True) if special_tokens else [] # special tokens from longest to shortest
        self._bytes_to_token: dict[bytes, int] = {byte: index for index, byte in vocab.items()} # bytes -> index reverse look-up
    
    def _split_string_by_special_tokens(self, string: str) -> list[str]:
        """
        Split a full text into segments separated by special tokens.
        Special tokens themselves are treated as segments too.

        Example:
            imagine <|endoftext|> as a special token (that we don't want to merge with other tokens),
            running this method on "Héllò hôw <|endoftext|>are ü? 🙃<|endoftext|>" should give us
            ["Héllò hôw ", "<|endoftext|>", "are ü? 🙃", "<|endoftext|>"]

        Args:
            string (str): the original text string.

        Returns:
            list[str]: the string segmented by split by special tokens.
        """
        if not self._special_tokens:
            return [string]

        pattern = "|".join(re.escape(special_token) for special_token in self._special_tokens)
        return [c for c in re.compile( f"({pattern})").split(string) if c]  # remove empty strings

    def _merge_bytes(self, string: str) -> list[bytes]:
        """
        Convert a text string into bytes that are recognized by BPE vocabulary.

        Args:
            string (_type_): the text string.

        Returns:
            list[bytes]: merged bytes.
        """
        merged_bytes_list: list[bytes] = []
        word_list: list[str] = split_text_to_words(string) # split the string into pre-tokenized words
        
        for word in word_list:
            merged_word_bytes = word_to_bytes(word)
            while True:
                min_merged_token = float('inf')
                index_to_merge = -1
                merged_bytes = None
                for i in range(len(merged_word_bytes) - 1):
                    if (merged_word_bytes[i], merged_word_bytes[i+1]) in self._merges:
                        merged_token = self._bytes_to_token[merged_word_bytes[i] + merged_word_bytes[i+1]]
                        if merged_token < min_merged_token: # prefer smaller merged token (for tie-breaking)
                            min_merged_token = merged_token
                            index_to_merge = i
                            merged_bytes = merged_word_bytes[i] + merged_word_bytes[i+1]
                
                if index_to_merge != -1: # if some tokens are merged during the iteration, we update the bytes list
                    merged_word_bytes = merged_word_bytes[:index_to_merge] + [merged_bytes] + merged_word_bytes[index_to_merge + 2:]
                else:
                    break
            
            merged_bytes_list.extend(merged_word_bytes)

        return merged_bytes_list

    def encode(self, string: str) -> list[int]:
        segments: list[str] = self._split_string_by_special_tokens(string)
        merged_tokens: list[int] = []
        for segment in segments:
            if segment in set(self._special_tokens):
                merged_tokens.append(self._bytes_to_token[segment.encode('utf-8')])
            else:
                merged_segment_bytes = self._merge_bytes(segment)
                merged_tokens.extend([self._bytes_to_token[token_bytes] for token_bytes in merged_segment_bytes])

        return merged_tokens

    def encode_iterable(self, iterable: Iterable[str]) -> Iterator[str]:
        for chunk in iterable:
            yield from self.encode(chunk)

    def decode(self, tokens: list[int]) -> str:
        bytes_list = [self._vocab[token] for token in tokens]
        return b"".join(bytes_list).decode("utf-8", errors='replace')
