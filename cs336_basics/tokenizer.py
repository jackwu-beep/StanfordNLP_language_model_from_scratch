from typing import List, Tuple, Dict
import regex

# GPT-2 style pre-tokenization pattern
PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""

class Tokenizer:
    def __init__(self, vocab: Dict[int, bytes], merges: List[Tuple[bytes, bytes]], special_tokens: List[str] = None):
        self.vocab = dict(vocab)
        self.merges = list(merges)
        self.special_tokens = special_tokens or []
        self.bytes_to_id = {token_bytes: token_id for token_id, token_bytes in self.vocab.items()}

        if special_tokens:
            for special_token in special_tokens:
                special_bytes = special_token.encode('utf-8')
                if special_bytes not in self.bytes_to_id:
                    # Add new special token to vocabulary
                    new_id = len(self.vocab)
                    self.vocab[new_id] = special_bytes
                    self.bytes_to_id[special_bytes] = new_id
        self.merge_rules = {}
        for i, (a, b) in enumerate(self.merges):
            self.merge_rules[(a, b)] = i
        
        # Create special token pattern for pre-tokenization if we have special tokens
        if self.special_tokens:
            # Sort special tokens by length (descending) to ensure greedy matching
            sorted_tokens = sorted(self.special_tokens, key=len, reverse=True)
            # Escape special characters in tokens and join with |
            escaped_tokens = [regex.escape(token) for token in sorted_tokens]
            pattern = '(' + '|'.join(escaped_tokens) + ')'
            self.special_token_pattern = regex.compile(pattern)
        else:
            self.special_token_pattern = None

    @classmethod
    def from_files(cls, vocab_filepath: str, merges_filepath: str, special_tokens: List[str] = None):
        """
        Create a tokenizer from saved vocabulary and merges files.
        
        Args:
            vocab_filepath: Path to the pickled vocabulary file
            merges_filepath: Path to the pickled merges file  
            special_tokens: Optional list of special tokens
            
        Returns:
            Tokenizer instance
        """
        import pickle
        
        with open(vocab_filepath, 'rb') as f:
            vocab = pickle.load(f)
            
        with open(merges_filepath, 'rb') as f:
            merges = pickle.load(f)
            
        return cls(vocab, merges, special_tokens)
    
    def _apply_bpe(self, word_bytes: bytes) -> List[bytes]:
        """
        Apply BPE merges to a sequence of bytes representing a single pre-token.
        
        Args:
            word_bytes: Byte sequence for a single pre-token
            
        Returns:
            List of byte sequences after applying BPE merges
        """
        if len(word_bytes) <= 1:
            return [word_bytes]
        
        # Start with individual bytes
        pairs = []
        word = [bytes([b]) for b in word_bytes]
        
        # Repeatedly find and apply the highest priority merge
        while True:
            # Find all adjacent pairs
            pairs = []
            for i in range(len(word) - 1):
                pairs.append((word[i], word[i + 1], i))
            
            if not pairs:
                break
                
            # Find the pair with the highest merge priority (lowest index in merges list)
            best_pair = None
            best_merge_idx = float('inf')
            
            for a, b, pos in pairs:
                if (a, b) in self.merge_rules:
                    merge_idx = self.merge_rules[(a, b)]
                    if merge_idx < best_merge_idx:
                        best_merge_idx = merge_idx
                        best_pair = (a, b, pos)
            
            if best_pair is None:
                break
                
            # Apply the best merge
            a, b, pos = best_pair
            new_word = []
            i = 0
            while i < len(word):
                if i == pos:
                    new_word.append(a + b)
                    i += 2  # Skip the next element since we merged
                else:
                    new_word.append(word[i])
                    i += 1
            word = new_word
        
        return word
    
    def encode(self, text: str) -> List[int]:
        if not text:
            return []
        
        if self.special_token_pattern:
            # Split text on special tokens, keeping the delimiters
            parts = regex.split(self.special_token_pattern, text)
        else:
            parts = [text]

        token_ids = []
        for part in parts:
            if not part:  # Skip empty parts
                continue
                
            # Check if this part is a special token
            if part in self.special_tokens:
                special_bytes = part.encode('utf-8')
                if special_bytes in self.bytes_to_id:
                    token_ids.append(self.bytes_to_id[special_bytes])
                continue
            
            # Pre-tokenize this part using GPT-2 style regex
            pre_tokens = regex.findall(PAT, part)
            
            for pre_token in pre_tokens:
                # Convert to UTF-8 bytes
                pre_token_bytes = pre_token.encode('utf-8')
                
                # Apply BPE to get list of byte sequences
                bpe_tokens = self._apply_bpe(pre_token_bytes)
                
                # Convert each byte sequence to token ID
                for token_bytes in bpe_tokens:
                    if token_bytes in self.bytes_to_id:
                        token_ids.append(self.bytes_to_id[token_bytes])
                    else:
                        # If we can't find the token, this shouldn't happen with proper BPE
                        # But handle gracefully by encoding individual bytes
                        for byte_val in token_bytes:
                            single_byte = bytes([byte_val])
                            if single_byte in self.bytes_to_id:
                                token_ids.append(self.bytes_to_id[single_byte])
        
        return token_ids
    
    def decode(self, ids: List[int]) -> str:
        """
        Decode a sequence of token IDs back to text.
        
        Args:
            ids: List of token IDs to decode
            
        Returns:
            Decoded text string
        """
        if not ids:
            return ""
        
        # Concatenate all byte sequences
        byte_sequence = b""
        for token_id in ids:
            if token_id in self.vocab:
                byte_sequence += self.vocab[token_id]
            # If token_id not in vocab, skip it (could be invalid input)
        
        # Decode bytes to UTF-8 string, replacing invalid sequences
        try:
            return byte_sequence.decode('utf-8', errors='replace')
        except Exception:
            # Fallback if something goes wrong
            return byte_sequence.decode('utf-8', errors='replace')
        

    def encode_iterable(self, iterable):
        """
        Memory-efficient encoding of an iterable of strings.
        
        This method processes text chunks one at a time to avoid loading
        large files entirely into memory.
        
        Args:
            iterable: Iterable of strings (e.g., file handle, list of strings)
            
        Yields:
            Token IDs one at a time
        """
        for text_chunk in iterable:
            if isinstance(text_chunk, str):
                # Encode this chunk and yield each token ID
                token_ids = self.encode(text_chunk)
                for token_id in token_ids:
                    yield token_id
            else:
                # Handle bytes or other types by converting to string first
                try:
                    text_chunk = text_chunk.decode('utf-8', errors='replace')
                    token_ids = self.encode(text_chunk)
                    for token_id in token_ids:
                        yield token_id
                except AttributeError:
                    # If it's already a string or doesn't have decode method
                    token_ids = self.encode(str(text_chunk))
                    for token_id in token_ids:
                        yield token_id