# PagedAttention Demo 设计文档

## 目标

实现一个独立的教学模块，复现 vLLM 论文中 PagedAttention 的核心机制，用纯 PyTorch 模拟 CUDA kernel 的逻辑。目的是巩固对 vLLM 论文的理解，不修改现有代码。

## 参数

- `block_size = 4`
- 仅支持 MHA（Multi-Head Attention），不实现 GQA。统一使用 `num_heads`，不区分 `num_kv_heads`
- 支持多 sequence batch
- CoW（Copy-on-Write）为必做项
- 验证方式：对比标准 attention 的输出（`torch.allclose`）

## 架构概览

```
BlockAllocator (纯 ID 管理)
    ↕ allocate / free / ref_count
KVCache (持有 K/V tensor)
    ↕ write / copy_block
BlockTable (per-sequence logical→physical 映射)
    ↕ append_token / fork
paged_attention_decode (loop-based + online softmax)
```

## vLLM 中 CUDA vs Python 的对应关系

| 组件 | vLLM 实现层 | 本 demo |
|---|---|---|
| BlockAllocator | Python | Python（基本等价） |
| BlockTable / BlockSpaceManager | Python | Python（基本等价） |
| KV cache 写入 (`reshape_and_cache`) | CUDA kernel | PyTorch tensor 赋值 |
| Attention 计算 (`paged_attention_v1/v2`) | CUDA kernel | PyTorch loop + online softmax |
| Prefill attention | CUDA kernel (标准 attention) | 复用现有 `scaled_dot_product_attention` |
| Scheduler / 调度 | Python | 不实现（手动构造输入） |

vLLM 的 CUDA kernel 直接在非连续的物理 block 上原地迭代计算 attention，不做 gather。
本 demo 用 Python loop 模拟这一行为。

## 组件设计

### 1. BlockAllocator

纯 ID 管理器，不持有任何 tensor。

**数据结构：**
- `num_blocks: int`
- `free_blocks: List[int]` — 初始化为 `[0, 1, ..., num_blocks-1]`
- `ref_count: Dict[int, int]` — 已分配 block 的引用计数

**接口：**
- `allocate() -> int`：从 free list 弹出一个 block，ref_count 设 1
- `free(block_id: int)`：ref_count -1，到 0 时回收到 free list
- `increase_ref(block_id: int)`：ref_count +1
- `needs_cow(block_id: int) -> bool`：ref_count > 1
- `num_free_blocks -> int`

### 2. KVCache

持有实际的 KV tensor，提供读写接口。

**数据结构：**
- `key_cache: Tensor [num_blocks, block_size, num_heads, head_dim]`
- `value_cache: Tensor [num_blocks, block_size, num_heads, head_dim]`

**接口：**
- `write(block_id: int, slot: int, k: Tensor, v: Tensor)` — 写入单个 token
- `copy_block(src: int, dst: int)` — CoW 数据拷贝

注意：不提供 `read_blocks` 批量读接口。decode loop 里逐 block 迭代，直接 `kv_cache.key_cache[block_id]` 索引即可。

### 3. BlockTable

维护单个 sequence 的 logical block → physical block 映射。

**数据结构：**
- `block_ids: List[int]` — 物理 block ID 列表
- `num_tokens: int` — 已写入的 token 数
- `block_size: int`

**接口：**
- `append_token(allocator, kv_cache) -> Tuple[int, int]`：
  - `slot = num_tokens % block_size`
  - slot == 0 且 num_tokens > 0 时分配新 block
  - 如果当前 block 的 ref_count > 1，触发 CoW
  - 返回 `(physical_block_id, slot)`
- `get_physical_blocks() -> List[int]`
- `fork(allocator) -> BlockTable`：CoW fork，共享 block IDs，increase_ref

### 4. paged_attention_decode

Loop-based + online softmax，逐 block 计算 attention。

**签名：**
```python
def paged_attention_decode(
    q: Tensor,              # (batch_size, num_heads, 1, head_dim) — decode 时 seq_len=1
    kv_cache: KVCache,
    block_tables: List[List[int]],
    context_lens: List[int],
) -> Tensor:                # (batch_size, num_heads, 1, head_dim)
```

**算法（对每个 sequence）：**
```
output = zeros(num_heads, head_dim)
running_max = -inf    # (num_heads,)
running_sum = zeros   # (num_heads,)

for each block_id in block_table:
    k_block = kv_cache.key_cache[block_id]    # (block_size, num_heads, head_dim)
    v_block = kv_cache.value_cache[block_id]  # (block_size, num_heads, head_dim)
    截断最后一个 block 的无效 token

    scores = q @ k_block^T / sqrt(d_k)     # (num_heads, valid_tokens)

    # Online softmax
    block_max = scores.max(dim=-1)
    new_max = max(running_max, block_max)
    correction = exp(running_max - new_max)

    output *= correction
    running_sum *= correction

    weights = exp(scores - new_max)
    output += weights @ v_block
    running_sum += weights.sum(dim=-1)

    running_max = new_max

output /= running_sum
```

### 5. Prefill 策略

Prefill 阶段不走 paged attention：
1. 用标准 `scaled_dot_product_attention` 计算 prompt 的 attention
2. 将 K/V 逐 token 写入 paged cache（分配 block、填充 slot）
3. 之后的 decode 阶段走 `paged_attention_decode`

### 6. Copy-on-Write 流程

场景：parallel sampling（同一 prompt 生成 N 个 completion）

1. Prompt prefill 完成后，`block_table.fork()` 创建 N 个副本，共享物理 blocks
2. Decode 时，`append_token` 检测到 ref_count > 1，触发 CoW：
   - 分配新 block
   - `kv_cache.copy_block(old, new)`
   - 替换 block_table 中的 old → new
   - old block ref_count -1
3. 关键观察：CoW 只在 prompt 最后一个 block 上触发（之前的 block 已满，不会再写入）

## 文件结构

```
cs336_basics/
  paged_attention.py          # BlockAllocator, KVCache, BlockTable, paged_attention_decode

scripts/
  test_paged_attention.py     # 对比测试脚本
```

## 验证方案

1. 构造小规模输入（batch=2, num_heads=4, head_dim=8, block_size=4, seq_len≈10）
2. 随机 Q/K/V，先用标准 attention 算 ground truth
3. 同样的 K/V 写入 paged cache，用 paged_attention_decode 计算
4. `torch.allclose` 验证一致性
5. CoW 测试：fork sequence，各自 decode，验证共享 block ID 相同、输出正确
