"""
A股交易日历模块
精确判断某一天是否为A股交易日，考虑：
  1. 周末非交易日
  2. 法定节假日非交易日
  3. 调休补班日为交易日（虽然是周末）

纯标准库，零依赖。别人直接 import 即可使用：

    from trading_calendar import (
        is_trading_day,        # 判断是否交易日
        next_trading_day,      # 下一个交易日
        prev_trading_day,      # 上一个交易日（最常用：取"上个交易日的数据"）
        count_trading_days,    # 区间内交易日数量
        list_trading_days,     # 区间内交易日列表
        nth_trading_day,       # 某月第N个交易日
        offset_trading_day,    # 向前/向后偏移N个交易日
    )

每年底自动从上交所休市安排页面（https://www.sse.com.cn/disclosure/dealinstruc/closed/）
抓取下一年数据并更新 HOLIDAYS 和 MAKEUP_WORKDAYS。
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Union
import json
import os
import urllib.request
import urllib.error

# 支持传入 date / datetime / str / tuple
DateLike = Union[date, datetime, str, tuple]

__all__ = [
    'is_trading_day',
    'next_trading_day',
    'prev_trading_day',
    'today_or_prev',
    'offset_trading_day',
    'count_trading_days',
    'list_trading_days',
    'nth_trading_day',
    'find_check_date',
    'is_today_check_date',
]

# ══════════════════════════════════════════════════════
# 自动更新配置
# ══════════════════════════════════════════════════════

_REMOTE_URL = (
    'https://raw.githubusercontent.com/yuchenaaa/'
    'a-share-trading-calendar/main/holiday_data.json'
)
_CACHE_DIR = os.path.join(os.path.expanduser('~'), '.trading_calendar')
_CACHE_FILE = os.path.join(_CACHE_DIR, 'holiday_data.json')
_CHECK_INTERVAL_DAYS = 7  # 每7天检查一次远程更新

# ══════════════════════════════════════════════════════
# 内置节假日数据（作为兜底，无网络时使用）
# ══════════════════════════════════════════════════════

# 法定节假日休市日期（只列非周末的部分，周末本身已默认休市）
# 格式：年份 -> [月日元组列表]
_BUILTIN_HOLIDAYS = {
    2025: [
        # 元旦 1月1日(周三)
        (1, 1),
        # 春节 1月28日(周二)-2月4日(周二)
        (1, 28), (1, 29), (1, 30), (1, 31),
        (2, 3), (2, 4),
        # 清明节 4月4日(周五)
        (4, 4),
        # 劳动节 5月1日(周四)-5月5日(周一)
        (5, 1), (5, 2), (5, 5),
        # 端午节 5月31日(周六已默认休)-6月2日(周一)
        (6, 2),
        # 中秋+国庆 10月1日(周三)-10月8日(周三)
        (10, 1), (10, 2), (10, 3), (10, 6), (10, 7), (10, 8),
    ],
    2026: [
        # 元旦 1月1日(周四)-1月2日(周五)
        (1, 1), (1, 2),
        # 春节 2月16日(周一)-2月20日(周五)  (除夕2月16日)
        (2, 16), (2, 17), (2, 18), (2, 19), (2, 20),
        # 清明节 4月5日(周日已默认休)-4月6日(周一)
        (4, 6),
        # 劳动节 5月1日(周五)
        (5, 1),
        # 端午节 6月19日(周五)
        (6, 19),
        # 中秋节 9月25日(周五)
        (9, 25),
        # 国庆节 10月1日(周四)-10月8日(周四)
        (10, 1), (10, 2), (10, 5), (10, 6), (10, 7), (10, 8),
    ],
}

# 调休补班日（周末但需要上班/交易的日期）
_BUILTIN_MAKEUP_WORKDAYS = {
    2025: [
        (1, 26),   # 周日，春节调休
        (2, 8),    # 周六，春节调休
        (4, 27),   # 周日，劳动节调休
        (9, 28),   # 周日，国庆调休
        (10, 11),  # 周六，国庆调休
    ],
    2026: [
        (2, 14),   # 周六，春节调休
        (2, 28),   # 周六，春节调休
        (10, 10),  # 周六，国庆调休
    ],
}


# ══════════════════════════════════════════════════════
# 自动更新机制
# 从 GitHub 拉取最新节假日数据，本地缓存，7天检查一次
# 无网络时自动回退到内置数据，不影响使用
# ══════════════════════════════════════════════════════

def _load_remote_data():
    """从 GitHub 下载最新的节假日数据并缓存到本地。"""
    try:
        req = urllib.request.Request(_REMOTE_URL, headers={'User-Agent': 'trading-calendar'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = json.loads(resp.read().decode('utf-8'))

        # 写入本地缓存
        os.makedirs(_CACHE_DIR, exist_ok=True)
        cache = {
            'updated': date.today().isoformat(),
            'data': raw,
        }
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        return raw
    except Exception:
        return None


def _load_cached_data():
    """读取本地缓存的节假日数据。返回 (data_dict, needs_refresh)。"""
    if not os.path.exists(_CACHE_FILE):
        return None, True
    try:
        with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        last_update = date.fromisoformat(cache['updated'])
        age_days = (date.today() - last_update).days
        return cache['data'], age_days >= _CHECK_INTERVAL_DAYS
    except Exception:
        return None, True


def _parse_data(raw):
    """将 JSON 数据转为 HOLIDAYS / MAKEUP_WORKDAYS 字典格式。"""
    holidays = {}
    makeup = {}
    for year_str, info in raw.items():
        year = int(year_str)
        holidays[year] = [tuple(x) for x in info.get('holidays', [])]
        makeup[year] = [tuple(x) for x in info.get('makeup_workdays', [])]
    return holidays, makeup


def _init_data():
    """初始化节假日数据：优先用缓存/远程，兜底用内置。"""
    global HOLIDAYS, MAKEUP_WORKDAYS

    # 先用内置数据
    HOLIDAYS = dict(_BUILTIN_HOLIDAYS)
    MAKEUP_WORKDAYS = dict(_BUILTIN_MAKEUP_WORKDAYS)

    # 尝试加载缓存
    cached, needs_refresh = _load_cached_data()

    if cached:
        remote_h, remote_m = _parse_data(cached)
        HOLIDAYS.update(remote_h)
        MAKEUP_WORKDAYS.update(remote_m)

    # 需要刷新时，后台尝试拉取（不阻塞主流程）
    if needs_refresh:
        try:
            import threading
            def _bg_refresh():
                global HOLIDAYS, MAKEUP_WORKDAYS
                raw = _load_remote_data()
                if raw:
                    remote_h, remote_m = _parse_data(raw)
                    HOLIDAYS.update(remote_h)
                    MAKEUP_WORKDAYS.update(remote_m)
            t = threading.Thread(target=_bg_refresh, daemon=True)
            t.start()
        except Exception:
            pass


# 模块加载时初始化
HOLIDAYS = {}
MAKEUP_WORKDAYS = {}
_init_data()


def _normalize(d: DateLike) -> date:
    """将各种日期格式统一转为 date 对象。

    支持:
        date(2025, 10, 1)
        datetime(2025, 10, 1, 14, 30)
        "2025-10-01" / "20251001" / "2025/10/01"
        (2025, 10, 1)
    """
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        s = d.strip().replace('/', '-')
        if len(s) == 8 and s.isdigit():
            s = f'{s[:4]}-{s[4:6]}-{s[6:8]}'
        parts = s.split('-')
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    if isinstance(d, (tuple, list)):
        return date(*d)
    raise TypeError(f'不支持的日期类型: {type(d)}')


def is_trading_day(d: DateLike) -> bool:
    """
    判断某一天是否为A股交易日。

    Args:
        d: 支持 date / datetime / str("2025-10-01") / tuple((2025,10,1))

    Returns:
        bool: 是否为交易日

    Examples:
        >>> is_trading_day("2025-10-01")   # 国庆节
        False
        >>> is_trading_day("2025-10-11")   # 调休补班日
        True
        >>> is_trading_day(date(2025, 1, 2))
        True
    """
    d = _normalize(d)
    year = d.year

    # 1. 检查是否为调休补班日（周末但交易）
    makeup = MAKEUP_WORKDAYS.get(year, [])
    if (d.month, d.day) in [(m, dy) for m, dy in makeup]:
        return True

    # 2. 周末默认休市
    if d.weekday() >= 5:  # 5=周六, 6=周日
        return False

    # 3. 检查是否为法定节假日
    holidays = HOLIDAYS.get(year, [])
    if (d.month, d.day) in [(m, dy) for m, dy in holidays]:
        return False

    # 4. 工作日且不在节假日列表中 → 交易日
    return True


# ══════════════════════════════════════════════════════
# 常用便捷函数
# ══════════════════════════════════════════════════════

def next_trading_day(d: DateLike = None) -> date:
    """
    获取 d 之后的下一个交易日（不含 d 本身）。
    d 默认为今天。

    Examples:
        >>> next_trading_day("2025-09-30")  # 国庆前
        date(2025, 10, 9)                   # 国庆后第一个交易日
    """
    d = _normalize(d) if d is not None else date.today()
    cur = d + timedelta(days=1)
    for _ in range(60):
        if is_trading_day(cur):
            return cur
        cur += timedelta(days=1)
    raise ValueError(f'{d} 之后60天内找不到交易日（请检查节假日数据是否完整）')


def prev_trading_day(d: DateLike = None) -> date:
    """
    获取 d 之前的上一个交易日（不含 d 本身）。
    d 默认为今天。

    最常用场景：取"上一个交易日的收盘价/数据"。

    Examples:
        >>> prev_trading_day("2025-10-09")  # 国庆后第一天
        date(2025, 9, 30)                   # 国庆前最后一个交易日
    """
    d = _normalize(d) if d is not None else date.today()
    cur = d - timedelta(days=1)
    for _ in range(60):
        if is_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    raise ValueError(f'{d} 之前60天内找不到交易日')


def offset_trading_day(d: DateLike = None, n: int = 0) -> date:
    """
    从 d 开始，向前(n>0)或向后(n<0)偏移 n 个交易日。
    n=0 时：若 d 是交易日返回 d，否则返回下一个交易日。

    Examples:
        >>> offset_trading_day("2025-01-02", -1)   # 前1个交易日
        date(2024, 12, 31)
        >>> offset_trading_day("2025-01-02", 3)    # 后3个交易日
        date(2025, 1, 7)
        >>> offset_trading_day("2025-10-01", 0)    # 国庆节 → 下一个交易日
        date(2025, 10, 9)
    """
    d = _normalize(d) if d is not None else date.today()

    if n == 0:
        if is_trading_day(d):
            return d
        return next_trading_day(d)

    step = 1 if n > 0 else -1
    remaining = abs(n)
    cur = d
    for _ in range(abs(n) * 10 + 60):
        cur += timedelta(days=step)
        if is_trading_day(cur):
            remaining -= 1
            if remaining == 0:
                return cur
    raise ValueError(f'偏移 {n} 个交易日失败')


def count_trading_days(start: DateLike, end: DateLike) -> int:
    """
    统计 [start, end] 闭区间内的交易日数量。

    Examples:
        >>> count_trading_days("2025-01-01", "2025-01-31")
        19
    """
    start, end = _normalize(start), _normalize(end)
    if start > end:
        start, end = end, start
    count = 0
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count


def list_trading_days(start: DateLike, end: DateLike) -> List[date]:
    """
    列出 [start, end] 闭区间内的所有交易日。

    Examples:
        >>> list_trading_days("2025-10-01", "2025-10-15")
        [date(2025,10,9), date(2025,10,10), date(2025,10,11), date(2025,10,13), ...]
    """
    start, end = _normalize(start), _normalize(end)
    if start > end:
        start, end = end, start
    days = []
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def nth_trading_day(year: int, month: int, n: int = 1) -> Optional[date]:
    """
    获取某月第 n 个交易日（n 从 1 开始）。

    Examples:
        >>> nth_trading_day(2025, 1, 1)   # 1月第1个交易日
        date(2025, 1, 2)                  # 1号是元旦
        >>> nth_trading_day(2025, 10, 1)  # 10月第1个交易日
        date(2025, 10, 9)                # 国庆长假后
    """
    import calendar
    _, last_day = calendar.monthrange(year, month)
    count = 0
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        if is_trading_day(d):
            count += 1
            if count == n:
                return d
    return None


def today_or_prev(d: DateLike = None) -> date:
    """
    若 d 是交易日则返回 d，否则返回上一个交易日。
    d 默认为今天。

    最常用场景：获取"最近一个有数据的交易日"。

    Examples:
        >>> today_or_prev("2025-10-01")  # 国庆节
        date(2025, 9, 30)               # 返回节前最后交易日
        >>> today_or_prev("2025-10-09")  # 正常交易日
        date(2025, 10, 9)               # 返回当天
    """
    d = _normalize(d) if d is not None else date.today()
    if is_trading_day(d):
        return d
    return prev_trading_day(d)


def find_check_date(year, month):
    """
    根据规则找到本月的检查日：
    - 若15号为交易日，检查日为15号
    - 若15号不为交易日，优先往后找最近交易日，找不到则往前找

    Args:
        year: 年
        month: 月

    Returns:
        date: 检查日
    """
    target = date(year, month, 15)

    if is_trading_day(target):
        return target

    # 先往后找（16, 17, ...），再往前找（14, 13, ...）
    for offset in range(1, 10):
        after = target + timedelta(days=offset)
        if after.month == month and is_trading_day(after):
            return after

    for offset in range(1, 10):
        before = target - timedelta(days=offset)
        if before.month == month and is_trading_day(before):
            return before

    # 兜底：返回15号
    return target


def is_today_check_date():
    """判断今天是否为本月的检查日"""
    today = date.today()
    check = find_check_date(today.year, today.month)
    return today == check, check


if __name__ == '__main__':
    # 测试：打印当月及接下来几个月的检查日
    from datetime import date
    today = date.today()
    print(f"今天: {today} ({'交易日' if is_trading_day(today) else '非交易日'})")

    is_check, check_date = is_today_check_date()
    print(f"本月检查日: {check_date} {'(就是今天!)' if is_check else ''}")

    # 打印未来6个月的检查日
    print("\n未来6个月检查日：")
    y, m = today.year, today.month
    for _ in range(6):
        cd = find_check_date(y, m)
        weekday_names = ['一', '二', '三', '四', '五', '六', '日']
        print(f"  {y}年{m:02d}月 → {cd} (周{weekday_names[cd.weekday()]})")
        m += 1
        if m > 12:
            m = 1
            y += 1
