class Tokenizer:
    def __init__(
        self, 
        vocab: dict[int, bytes],
        merges: list[tuple[bytes, bytes]],
        special_tokens: list[str] | None = None,
    ) -> None:
        self.vocab = vocab
        self.merges = merges
        self.special_tokens = special_tokens if special_tokens else []
        
        
    
    def from_files(cls, vocab_filepath, merges_filepath, special_tokens=None):

    def encode(self, text: str) -> list[int]:

    def encode(self, text: str) -> list[int]:

    def decode(self, ids: list[int]) -> str: