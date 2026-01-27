import regex as re
from multiprocessing import Pool

from pretokenization_example import find_chunk_boundaries

PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""

def train_bpe(input_path: str, vocab_size: int, special_tokens: list[str], num_processes: int = 4):
    """Trains a BPE tokenizer with parallelized pre-tokenization process, and byte pair merging to create a vocab of size vocab_size."""
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
        boundaries = find_chunk_boundaries(f, num_processes, b"<|endoftext|>")
        
        chunks_data = []
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            f.seek(start)
            chunk_bytes = f.read(end - start)
            chunk_text = chunk_bytes.decode("utf-8", errors="ignore")
            chunks_data.append((chunk_text, special_tokens))
    
    # parallelize pre-tokenization process
    with Pool(num_processes) as pool:
        results = pool.map(pretokenize_chunk_worker, chunks_data)
    
    chunk_token_ids = []
    for result in results:
        chunk_token_ids.extend(result)
            
    # 2. MERGE
    # create byte pair dict over entire corpus
    token_pair_count: dict[tuple[int, int], int] = {} # token id pairs : count
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
        
        if max_pair is None:
            break
        
        # add to vocab and merges
        new_token_id = len(vocab)
        vocab[new_token_id] = vocab[max_pair[0]] + vocab[max_pair[1]]
        merges.append((vocab[max_pair[0]], vocab[max_pair[1]]))
        
        for chunk in chunk_token_ids:
            i = 0

            chunk_len = len(chunk)
            while i < chunk_len - 1:
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
                if i + 2 < chunk_len:
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
    """Return the most common, lexigraphically largest token pair"""
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
        
    
if __name__ == "__main__":
    import cProfile
    import pstats
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    input_path = "/Users/johnkim/Developer/cs336/assignment1-basics/data/TinyStoriesV2-GPT4-valid.txt"
    vocab_size = 10000
    special_tokens = ["<|endoftext|>"]
    num_processes = 4
    
    vocab, merges = train_bpe(input_path, vocab_size, special_tokens, num_processes)
    
       
    profiler.disable()
    
    # Print results
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(30)  # Top 30 functions
    
    # print(vocab)
    # print(merges)
    print(f"Trained tokenizer with {len(vocab)} tokens and {len(merges)} merges")

