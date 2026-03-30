# A股交易日历 (A-Share Trading Calendar)

精确判断中国A股市场交易日的 Python 工具库。

**纯标准库，零依赖，单文件，复制即用。**

## 为什么需要这个？

写量化策略、数据分析代码时，经常遇到：
- "取上个交易日的收盘价" — 上个交易日是哪天？周五？还是因为节假日要往前推更多天？
- "国庆后第一个交易日" — 10月8号？9号？还是别的？
- "这个月有多少个交易日" — 需要排除周末、春节、国庆...

这些问题的核心是同一个：**某天是不是A股交易日？**

本模块帮你处理好全部细节：周末、法定节假日（元旦/春节/清明/劳动节/端午/中秋/国庆）、调休补班日（周末但开市）。你只需要调用一个函数。

## 快速开始

### 安装

把 `trading_calendar.py` 下载到你的项目目录，直接 import：

```bash
# 方式1：直接下载
curl -O https://raw.githubusercontent.com/yuchenaaa/a-share-trading-calendar/main/trading_calendar.py

# 方式2：克隆仓库
git clone https://github.com/yuchenaaa/a-share-trading-calendar.git
cp a-share-trading-calendar/trading_calendar.py your_project/
```

### 使用

```python
from trading_calendar import *

# 判断是否交易日
is_trading_day("2025-10-01")        # False（国庆节）
is_trading_day("2025-10-11")        # True（调休补班日，周六但开市）

# 上个交易日（最常用）
prev_trading_day("2025-10-09")      # 2025-09-30（跳过国庆7天）

# 下个交易日
next_trading_day("2025-09-30")      # 2025-10-09

# 最近有数据的交易日（今天是交易日就返回今天，否则返回上个交易日）
today_or_prev("2025-10-01")         # 2025-09-30
```

## API 参考

所有日期参数都支持多种格式：

```python
is_trading_day(date(2025, 10, 1))     # date 对象
is_trading_day("2025-10-01")          # 字符串
is_trading_day("20251001")            # 无分隔符字符串
is_trading_day("2025/10/01")          # 斜杠分隔
is_trading_day((2025, 10, 1))         # 元组
```

### 核心函数

| 函数 | 说明 | 示例 |
|------|------|------|
| `is_trading_day(d)` | 判断是否交易日 | `is_trading_day("2025-10-01")` → `False` |
| `prev_trading_day(d)` | 上一个交易日（不含当天） | `prev_trading_day("2025-10-09")` → `9月30日` |
| `next_trading_day(d)` | 下一个交易日（不含当天） | `next_trading_day("2025-09-30")` → `10月9日` |
| `today_or_prev(d)` | 当天是交易日返回当天，否则返回上个交易日 | 取"最近有数据的日期" |
| `offset_trading_day(d, n)` | 偏移 N 个交易日（正=往后，负=往前） | T+3 结算日 |
| `count_trading_days(start, end)` | 区间内交易日数量 | 统计月/季度交易日 |
| `list_trading_days(start, end)` | 区间内交易日列表 | 回测日期序列 |
| `nth_trading_day(year, month, n)` | 某月第 N 个交易日 | 月初/月末交易日 |

> `d` 参数默认为今天，可以省略：`prev_trading_day()` = 今天的上个交易日。

### 实用场景

```python
from trading_calendar import *

# 场景1：计算涨跌幅
last_td = prev_trading_day()
change = today_close / get_close(last_td) - 1

# 场景2：只在交易日执行策略
if is_trading_day():
    run_strategy()

# 场景3：T+3 结算日
settle = offset_trading_day("2025-03-20", 3)

# 场景4：回溯20个交易日
start = offset_trading_day("2025-03-20", -20)
days = list_trading_days(start, "2025-03-20")

# 场景5：某月第1个和最后1个交易日
first = nth_trading_day(2025, 10, 1)   # 10月第1个交易日 → 10月9日
last = list_trading_days("2025-10-01", "2025-10-31")[-1]

# 场景6：2025年Q1有多少个交易日
n = count_trading_days("2025-01-01", "2025-03-31")
```

## 数据覆盖

| 年份 | 状态 |
|------|------|
| 2025 | 完整（含全部节假日+调休） |
| 2026 | 完整（含全部节假日+调休） |
| 其他年份 | 仅排除周末，不含节假日 |

数据来源：[上海证券交易所休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/)

### 更新年度数据

每年底上交所发布下一年休市安排后，编辑 `trading_calendar.py` 中的两个字典：

```python
# 1. HOLIDAYS — 法定节假日休市日（只列非周末的部分）
HOLIDAYS = {
    2027: [
        (1, 1),                        # 元旦
        (1, 29), (1, 30), (1, 31),     # 春节
        ...
    ],
}

# 2. MAKEUP_WORKDAYS — 调休补班日（周末但开市）
MAKEUP_WORKDAYS = {
    2027: [
        (1, 25),   # 周日，春节调休
        ...
    ],
}
```

欢迎通过 PR 提交新年份的数据。

## 许可证

MIT License
