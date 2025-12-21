import numpy as np
import random

# 定义动作映射
ACTIONS = [(-1, 0), (0, 1), (1, 0), (0, -1), (0, 0)]  # 动作对应的坐标偏移
ACTION_SYMBOLS = ['↑', '→', '↓', '←', '○']  # 用于可视化的动作符号


# 初始化图1中的四种策略（根据网格箭头方向定义5x5矩阵）
# 策略1（左上表格）
policy1_matrix = [
    [1, 1, 1, 2, 2],  
    [0, 0, 1, 2, 2],  
    [0, 3, 2, 1, 2],  
    [0, 1, 4, 3, 2],  
    [0, 1, 0, 3, 3]   
]


# 策略2（右上表格）
policy2_matrix = [
    [1, 1, 1, 1, 2],  
    [0, 0, 1, 1, 2],  
    [0, 3, 2, 1, 2],  
    [0, 1, 4, 3, 2],  
    [0, 1, 0, 3, 3]   
]


# 策略3（左下表格）
policy3_matrix = [
    [1, 1, 1, 1, 1],  
    [1, 1, 1, 1, 1],  
    [1, 1, 1, 1, 1],  
    [1, 1, 1, 1, 1],  
    [1, 1, 1, 1, 1]  
]


# 策略4（右下表格，随机策略）
policy4_matrix = [[random.randint(0, 4) for _ in range(5)] for _ in range(5)]

forbidden_list = [(1, 1), (1, 2), (2, 2), (3, 1, (3, 3), (4, 1))]  # 表格禁止区域坐标列表(四个都一样)
goal_idx = (3, 2)  # 目标表格坐标

class GridWord:
    def __init__(self, strategy_grid, forbidden_list, goal_idx, size=5, r_boundary=-1, r_forbidden=-1, r_goal=1, r_other=0):
        """
        初始化网格世界
        strategy_grid : 策略网格，格式为二维列表
        forbidden_list : 禁止区域列表，格式为 [(x1, y1), (x2, y2), ...]
        goal_idx : 目标表格索引（整数）
        size : 网格大小（默认为5x5）
        r_boundary : 碰到边界的奖励值
        r_forbidden : 进入禁止区域的奖励值
        r_goal : 到达目标的奖励值
        r_other : 其他情况的奖励值
        """
        self.strategy_grid = strategy_grid  # 存储策略网格
        self.forbidden_list = forbidden_list  # 存储禁止区域
        self.goal_idx = goal_idx    # 存储目标表格索引
        self.size = size
        # 奖励设置
        self.r_boundary = r_boundary
        self.r_forbidden = r_forbidden
        self.r_goal = r_goal
        self.r_other = r_other
        
    def get_reward(self, row, col):
        """根据位置获取奖励值"""
        if (row, col) in self.forbidden_list:
            return self.r_forbidden
        if (row, col) == self.goal_idx:
            return self.r_goal
        if not (0 <= row < self.size and 0 <= col < self.size):
            return self.r_boundary
        return self.r_other
    
    def get_next_state(self, row, col):
        """根据当前状态和策略获取下一个状态"""
        action_idx = self.strategy_grid[row][col]
        action = ACTIONS[action_idx]
        next_row, next_col = row + action[0], col + action[1]
        # 检查边界
        if not (0 <= next_row < self.size and 0 <= next_col < self.size):
            return row, col  # 保持在原地
        return next_row, next_col

    #使⽤两种⽅法求解贝尔曼⽅程：解析式求解法和迭代法。
#（1）解析式求解法
def matrix_solution(gridworld, discount_factor=0.9):
    size = gridworld.size
    num_states = size * size
    A = np.zeros((num_states, num_states))
    b = np.zeros(num_states)

    for row in range(size):
        for col in range(size):
            state_idx = row * size + col
            action_idx = gridworld.strategy_grid[row][col]
            action = ACTIONS[action_idx]
            next_row, next_col = gridworld.get_next_state(row, col)
            next_state_idx = next_row * size + next_col
            reward = gridworld.get_reward(next_row, next_col)

            A[state_idx, state_idx] = 1
            A[state_idx, next_state_idx] -= discount_factor
            b[state_idx] = reward

    V_flat = np.linalg.solve(A, b)
    V = V_flat.reshape((size, size))
    return V
#（2）迭代法
def value_iteration(gridworld, theta=1e-6, discount_factor=0.9): 
    size = gridworld.size
    V = np.zeros((size, size))  # 初始化状态值函数为零矩阵

    while True:
        delta = 0
        for row in range(size):
            for col in range(size):
                v = V[row, col]
                action_idx = gridworld.strategy_grid[row][col]
                action = ACTIONS[action_idx]
                next_row, next_col = gridworld.get_next_state(row, col)
                reward = gridworld.get_reward(next_row, next_col)
                V[row, col] = reward + discount_factor * V[next_row, next_col]
                delta = max(delta, abs(v - V[row, col]))
        if delta < theta:
            break
    return V    

# 对四种策略分别求解
strategies = [
    ("策略1", policy1_matrix),
    ("策略2", policy2_matrix),
    ("策略3", policy3_matrix),
    ("策略4", policy4_matrix)
]
for i, (title, policy) in enumerate(strategies):
    # 创建GridWord对象
    grid = GridWord(strategy_grid=policy, forbidden_list=forbidden_list, goal_idx=goal_idx)
    # 解析式求解
    V_matrix = matrix_solution(grid)
    # 迭代法求解
    V_iter = value_iteration(grid)
    # 打印出策略矩阵，使用对应符号替换
    policy_symbols = [[ACTION_SYMBOLS[policy[r][c]] for c in range(grid.size)] for r in range(grid.size)]
    print(f"{title} 策略矩阵:")
    for row in policy_symbols:
        print(" ".join(row))
    print("解析式求解的状态值函数 V:")
    print(V_matrix)
    print("迭代法求解的状态值函数 V:")
    print(V_iter)
    print("\n")

     
