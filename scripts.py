import pickle

def find_bytes_not_decoded() -> bytes:
    """
        A simple function to iterate bytes sequence and find a
        combination that is not able to be decoded to utf-8
    """
    for i in range(0, 256):
        for j in range(0, 256):
            b = bytes([i, j])
            try:
                b.decode("utf-8")
            except Exception:
                return b
    
    raise ValueError("Not found")


def load_vocab(path):
    with open(path, 'rb') as file:
        vocab = pickle.load(file)
    return vocab


if __name__ == "__main__":
    vocab = load_vocab("/Users/yangpei/Desktop/side-projects/cs336/cs336-assignment1-basics/result/vocab-owt.pkl")
    
    items = list(vocab.items())
    items = sorted(items, key=lambda x: len(x[1]))
    print(items[-1])