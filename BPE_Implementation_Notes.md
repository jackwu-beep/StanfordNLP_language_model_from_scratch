# BPE 训练实现笔记

## 核心算法流程

### 1. 初始化阶段
```python
# 1.1 构建初始词表
vocab = {i: bytes([i]) for i in range(256)}  # 0-255: 单字节token
for token in special_tokens:
    vocab[len(vocab)] = token.encode('utf-8')  # 添加特殊token

# 1.2 预处理文本
text_parts = split_by_special_tokens(text, special_tokens)  # 按特殊token切分
PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""
pat = re.compile(PAT)  # GPT-2风格的预分词正则
```

### 2. Token化与计数
```python
# 2.1 将每个word表示为token-id列表
word_tokens = {}  # word_str -> list[token_id]
word_counts = Counter()  # word_str -> 出现次数

for text_part in text_parts:
    for match in pat.finditer(text_part):
        word_str = match.group()
        word_counts[word_str] += 1
        if word_str not in word_tokens:
            # 初始化: 每个字节对应token id (0..255)
            word_tokens[word_str] = list(word_str.encode('utf-8'))

# 2.2 统计相邻token-id对的频率
pair_cnt = Counter()
for word_str, token_ids in word_tokens.items():
    count = word_counts[word_str]
    for i in range(len(token_ids) - 1):
        pair = (token_ids[i], token_ids[i + 1])
        pair_cnt[pair] += count
```

### 3. 迭代合并
```python
while len(vocab) < vocab_size:
    # 3.1 选择最高频pair (tie-break规则见下)
    most_common_pair, freq = max(
        pair_cnt.items(), 
        key=lambda kv: (kv[1], (vocab[kv[0][0]], vocab[kv[0][1]]))
    )
    
    # 3.2 创建新token
    token_a, token_b = most_common_pair
    new_token_id = len(vocab)
    vocab[new_token_id] = vocab[token_a] + vocab[token_b]
    merges.append((vocab[token_a], vocab[token_b]))
    
    # 3.3 替换并更新计数 (见下节)
```

---

## 关键实现细节

### 问题1: Tie-Breaking规则

**❌ 错误理解1**: 拼接后比较字典序
```python
# 错误: 直接拼接bytes再比较
key=lambda kv: (kv[1], vocab[kv[0][0]] + vocab[kv[0][1]])
```

**❌ 错误理解2**: 按token-id数值比较
```python
# 错误: 按(token_a_id, token_b_id)数值比较
key=lambda kv: (kv[1], kv[0])
```

**✅ 正确做法**: 按 `(bytes_a, bytes_b)` tuple字典序比较
```python
# 正确: 先比第一个bytes,相同再比第二个bytes
key=lambda kv: (kv[1], (vocab[kv[0][0]], vocab[kv[0][1]]))
```

**示例说明**:
```python
# 同频的两个pair:
pair1 = (97, 97)   # (b'a', b'a')
pair2 = (32, 98)   # (b' ', b'b')

# 错误方法1 (拼接): b'aa' vs b' b' → b'aa' > b' b' (因为'a'>'')
# 错误方法2 (数值): (97,97) vs (32,98) → (97,97) > (32,98)
# 正确方法 (tuple): (b'a', b'a') vs (b' ', b'b') → 先比b'a' vs b' ' → b'a' 更大 ✓
```

---

### 问题2: 非重叠贪心匹配

**场景**: 对于连续重复字符 `aaaaa`，合并 `(a,a)` 时如何处理？

**❌ 错误做法**: 重叠匹配
```python
# 从 [a, a, a, a, a] 重叠匹配 → [aa, aa, aa] (错误!)
```

**✅ 正确做法**: 从左到右非重叠贪心匹配
```python
while i < len(token_ids):
    if i < len(token_ids) - 1 and token_ids[i] == token_a and token_ids[i + 1] == token_b:
        new_token_ids.append(new_token_id)
        i += 2  # ← 关键: 跳过2个位置,避免重叠
    else:
        new_token_ids.append(token_ids[i])
        i += 1

# 从 [97, 97, 97, 97, 97] → [new_id, new_id, 97] ✓
# 位置0-1合并, 2-3合并, 4单独
```

---

### 问题3: 增量更新pair计数

**核心难点**: 合并后需要删除旧pair、添加新pair

**完整更新逻辑**:
```python
# 在所有词中替换 (token_a, token_b) -> new_token_id 并更新pair计数
        for word_str, token_ids in word_tokens.items():
            count = word_counts[word_str]
            i = 0
            new_token_ids = []
            
            while i < len(token_ids):
                # 非重叠贪心匹配
                if i < len(token_ids) - 1 and token_ids[i] == token_a and token_ids[i + 1] == token_b:
                    # 找到匹配,更新计数
                    # 删除旧pair的计数
                    if i > 0:
                        old_left_pair = (token_ids[i - 1], token_a)
                        pair_cnt[old_left_pair] -= count
                    if i + 2 < len(token_ids):
                        old_right_pair = (token_b, token_ids[i + 2])
                        pair_cnt[old_right_pair] -= count
                    pair_cnt[most_common_pair] -= count
                    
                    # 添加新token到结果
                    new_token_ids.append(new_token_id)
                    
                    # 添加新pair的计数（使用new_token_ids中的左邻居）
                    if len(new_token_ids) > 1:
                        new_left_pair = (new_token_ids[-2], new_token_id)
                        pair_cnt[new_left_pair] += count
                    if i + 2 < len(token_ids):
                        new_right_pair = (new_token_id, token_ids[i + 2])
                        pair_cnt[new_right_pair] += count
                    
                    i += 2  # 跳过已合并的两个token
                else:
                    new_token_ids.append(token_ids[i])
                    i += 1
            
            word_tokens[word_str] = new_token_ids
```

**图示 (合并 `(a,b)` → `ab` 在序列 `[x, a, b, y]` 中)**:
```
Before: [x, a, b, y]
        pairs: (x,a), (a,b), (b,y)

After:  [x, ab, y]
        pairs: (x,ab), (ab,y)

删除: (x,a), (a,b), (b,y)
添加: (x,ab), (ab,y)
```

---

### 问题4: 连续合并的边界情况

**场景**: `aaaa` 合并 `(a,a)` → `[aa, aa]`，需要正确处理新pair `(aa, aa)`

**❌ 常见错误**: 使用旧token_ids来获取左邻居
```python
# 错误: i=2时, token_ids[i-1]还是97,而不是新生成的256
if i > 0:
    old_left_pair = (token_ids[i - 1], token_a)  # 错误!
```

**✅ 正确做法**: 从新构建的列表获取左邻居
```python
if i > 0:
    # 用旧列表的i-1位置获取左邻居(因为还没遍历到)
    old_left_pair = (token_ids[i - 1], token_a)
    pair_cnt[old_left_pair] -= count
    
    # 添加新pair时也用旧列表(此时new_token_ids[-1]就是左边刚加的新token)
    new_left_pair = (token_ids[i - 1], new_token_id)
    pair_cnt[new_left_pair] += count
```

**为什么可以这样?**
- 我们是从左到右遍历，`i-1` 位置**要么已经被合并(跳过了)**，**要么没匹配到(保持原值)**
- 关键是 `token_ids[i-1]` 在遍历到 `i` 时还没被修改，保存的是正确的左邻居token

---

## Debug思路总结

### 1. 单步验证策略
```python
# 在循环中打印前几轮合并信息
if len(merges) < 5:
    print(f"Merge {len(merges)}: selected {most_common_pair}")
    print(f"  → {vocab[token_a]!r} + {vocab[token_b]!r} = {vocab[new_token_id]!r}")
```

### 2. 构造最小测试用例
```python
# 测试连续字符: "aaaa bbbb"
# 预期: 第一轮合并(a,a)和(b,b)都是频率2
# tie-break: (b'b', b'b') > (b'a', b'a') → 应该选(b'b', b'b')
```

### 3. 对比输出差异
```bash
# 运行测试查看第一个失败点
uv run pytest tests/test_train_bpe.py::test_train_bpe -vv 2>&1 | head -100

# 关注 "At index X diff" 信息
# 例如: At index 31 diff: (b' ', b'd') != (b' a', b'nd')
```

### 4. 验证tie-break逻辑
```python
# 手动测试Python的bytes tuple比较
>>> (b'a', b'a') > (b' ', b'b')
True
>>> (b'a', b'a') > (b'a', b'b')
False  # 第一个相同,比第二个
```

---

## 常见陷阱与注意事项

### ⚠️ 陷阱1: 混淆"字节"与"token"
- **字节 (byte)**: 0-255的原始数值,存储在 `vocab` 中的 `bytes` 对象
- **Token-id**: 词表中的索引,初始0-255对应单字节,后续256+对应合并token
- **必须用token-id作为pair_cnt的key**, 而不是bytes

### ⚠️ 陷阱2: 忘记non-overlap原则
```python
# 错误: 可能重复计数
for i in range(len(token_ids) - 1):
    if (token_ids[i], token_ids[i+1]) == most_common_pair:
        # 替换后继续 i+=1 会导致重叠
```

### ⚠️ 陷阱3: 提前清零pair_cnt
```python
# 错误: 先清零导致后续减法出错
pair_cnt[most_common_pair] = 0  # ❌

# 正确: 在遍历每个匹配时逐次减
pair_cnt[most_common_pair] -= count  # ✓
```

### ⚠️ 陷阱4: 忽略edge case
- **单字符word**: `len(byte_seq) < 2` 时没有pair,跳过
- **空pair_cnt**: 所有pair都被合并完,提前退出
- **频率为0**: 所有pair计数减到0,提前退出

---

## 性能优化建议

### 可选优化1: 使用heap选择最大频率pair
```python
# 当前实现: O(N) 每轮找max
max(..., key=lambda kv: (kv[1], ...))

# 优化: 维护最大堆 (适合vocab_size很大的情况)
# 但对作业规模(~500 vocab_size),简单方法已足够
```

### 可选优化2: 增量更新而非全量重建
- 当前实现已经是增量更新pair_cnt
- 可进一步维护 `pair -> affected_words` 映射,只更新受影响的词

### 实测性能 (TinyStories数据集片段)
- 简单方法: ~3-4秒训练500 vocab
- **结论**: 对作业规模无需复杂优化

---

## 测试checklist

- [x] `test_train_bpe_speed`: 性能要求 (< 10秒)
- [x] `test_train_bpe`: 基本功能,验证merges和vocab正确性
- [x] `test_train_bpe_special_tokens`: 特殊token处理

**关键验证点**:
1. Tie-break规则: 同频时按 `(bytes_a, bytes_b)` tuple字典序选**最大**
2. 非重叠匹配: 连续字符合并后token数正确
3. 增量更新: pair_cnt在每轮合并后保持一致

---

## 相关资源

- **GPT-2 Tokenizer**: https://github.com/openai/gpt-2/blob/master/src/encoder.py
- **HuggingFace Tokenizers**: https://github.com/huggingface/tokenizers
- **正则表达式 `regex` 库**: 支持 `\p{L}` (Unicode字母类)

---

## 总结

BPE训练的核心是:
1. **表示正确**: 用token-id而非bytes做pair key
2. **匹配正确**: 非重叠贪心从左到右
3. **更新正确**: 删除旧pair+添加新pair的边界处理
4. **选择正确**: tuple字典序tie-break

理解这四点后,剩下的就是细心的边界条件处理和充分的单元测试验证。
