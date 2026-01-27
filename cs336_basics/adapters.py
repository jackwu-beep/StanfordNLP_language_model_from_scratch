import regex as re
from multiprocessing import Pool

# from pretokenization_example import find_chunk_boundaries

PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""

def bpe_tokenizer(input_path: str, vocab_size: int, special_tokens: list[str]):
    
    # max vocab size 10k = max merges = 9.7k
    
    # 0. init vocab size 256 (bytes)
    # 1. pre-tokenization
        # corpus --> chunks (with removed special token)
            # get regex for special tokens to not include
            # split on your special tokens (e.g. Doc 1 <end of text> Doc 2 --> Doc1 and Doc2 pretokenized separately)
        # chunks --> pre-tokenization --> pre-tokenized chunks
        # combine chunks into one corpus
    # 2. merge
        # while we can still merge
            # find max_pair + add to vocab/merges
            # for every chunk
                # check for the max pair chunk (skip if not)
                # if at max_pair chunk:
                    # if token on left:
                        # decrement count of left pair
                        # increment count of new pair
                    # if token on right:
                        # decrement count of right pair
                        # increment count of new pair
                    # replace with new token (len(vocab) - 1)
        
    
    
    # 0. INITIALIZE BYTE VOCABULARY (token int : bytes)
    vocab: dict[int, bytes] = {}
    merges: list[tuple[bytes, bytes]] = []
    byte_vocab_size = 256
    
    for i in range(byte_vocab_size):
        vocab[i] = bytes([i])
        
    # add special tokens
    next_id = byte_vocab_size
    for token in special_tokens:
        vocab[next_id] = token.encode('utf-8')
        next_id += 1
            
    # 1. PRE-TOKENIZATION
    with open(input_path, 'rb') as f:
        # num_processes = 4
        # boundaries = find_chunk_boundaries(f, num_processes, b"<|endoftext|>")
        corpus_text = f.read().decode("utf-8")
        
        # split on special tokens
        pattern = "|".join(re.escape(token) for token in special_tokens)
        chunks = re.split(pattern, corpus_text)
        
        chunk_token_ids = []
        # pre-tokenize each chunk with regex
        for chunk in chunks:
            if not chunk: continue
            
            pretok_chunk_iter = re.finditer(PAT, chunk)
            for pretok in pretok_chunk_iter:
                # text --> pretok --> bytes --> token ids
                chunk_pretok = pretok.group() 
                chunk_pretok_bytes = chunk_pretok.encode('utf-8')
                chunk_token_ids.append(list(chunk_pretok_bytes))
            
    # 2. MERGE
    # create byte pair dict over entire corpus
    token_pair_count: dict[tuple[int, int], int] = {} # token id pairs : count
    merges: list[tuple[bytes, bytes]]
    max_merges = vocab_size - len(vocab)    

        
    # get initial token pair dictionary
    for chunk in chunk_token_ids:
        for i in range(len(chunk) - 1):
            token_pair = (chunk[i], chunk[i + 1])
            if token_pair not in token_pair_count: 
                token_pair_count[token_pair] = 1
            else:
                token_pair_count[token_pair] += 1
    

    while len(merges) < max_merges:
        # get lexographically largest pair
        max_pair = get_max_pair(token_pair_count)
        
        # add to vocab and merges
        new_token_id = len(vocab)
        vocab[new_token_id] = vocab[max_pair[0]] + vocab[max_pair[1]]
        merges.append((vocab[max_pair[0]], vocab[max_pair[1]]))
        
        for chunk in chunk_token_ids:
            i = 0

            while i < len(chunk) - 1:
                token_pair = (chunk[i], chunk[i + 1])
                
                if token_pair != max_pair: 
                    i += 1 
                    continue
                
                # search left
                if i > 0:
                    old_left_pair = (chunk[i - 1], chunk[i])
                    new_left_pair = (chunk[i - 1], new_token_id)
                    
                    # decrement old pair
                    token_pair_count[old_left_pair] -= 1
                    if token_pair_count[old_left_pair] == 0:
                        del token_pair_count[old_left_pair]
                    
                    # increment new pair
                    token_pair_count[new_left_pair] = token_pair_count.get(new_left_pair, 0) + 1
                    
                # search right
                if i + 2 < len(chunk):
                    old_right_pair = (chunk[i + 1], chunk[i + 2])
                    new_right_pair = (new_token_id, chunk[i + 2])
                    
                    # decrement old pair
                    token_pair_count[old_right_pair] -= 1
                    if token_pair_count[old_right_pair] == 0:
                        del token_pair_count[old_right_pair]
                    
                    # increment new pair
                    token_pair_count[new_right_pair] = token_pair_count.get(new_right_pair, 0) + 1
                    
                # replace with new token
                chunk[i] = new_token_id
                del chunk[i + 1]
        
        del token_pair_count[max_pair]
        
    return vocab, merges
    

def pretokenize_chunk_worker(args):
    """Worker function to pre-tokenize a single chunk"""
    chunk_text, special_tokens = args
    
    # split on special tokens
    pattern = "|".join(re.escape(token) for token in special_tokens)
    sub_chunks = re.split(pattern, chunk_text)
    
    # pre-tokenize each sub-chunk
    result = []
    for sub_chunk in sub_chunks:
        if not sub_chunk:
            continue
        
        for match in re.finditer(PAT, sub_chunk):
            pretok_bytes = match.group().encode('utf-8')
            result.append(list(pretok_bytes))
    
    return result
                
        
def get_max_pair(token_pair_count):
    if not token_pair_count: 
        return None
    
    max_list = []
    max_count = 0
    for pair in token_pair_count:
        cnt = token_pair_count[pair]
        # new max
        if cnt > max_count:
            max_count = cnt
            max_list = [pair]
        elif cnt == max_count:
            max_list.append(pair)
    
    max_pair = max(max_list) 
    return max_pair
        
    
    
    
