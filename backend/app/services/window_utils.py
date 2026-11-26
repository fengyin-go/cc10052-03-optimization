"""指标窗口公共工具：时间解析、左闭右开切窗、确认结果与补算状态定位。

指标查询服务负责把查询区间裁成一个个调度窗口；指标计算作业在补算时也复用
同一套窗口步长与调度窗口标识，保证"缺段"与"作业轮次"能对得上同一个调度窗口。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterator

from app.store import store

CONFIRMED = "已确认"
MISSING = "缺段"
RUNNING = "未算完"
RESULT_STATUSES = (CONFIRMED, MISSING, RUNNING)


def parse_datetime(value: Any) -> datetime:
    """解析前端传来的时间：支持日期、分钟精度和秒精度三种写法。"""
    text = str(value or "").strip().replace(" ", "T")
    if not text:
        raise ValueError("时间不能为空")
    if len(text) == 10:
        text += "T00:00:00"
    elif len(text) == 16:
        text += ":00"
    return datetime.fromisoformat(text)


def format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def window_label(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return f"{start:%H:%M}-{end:%H:%M}"
    return f"{start:%m-%d %H:%M}-{end:%m-%d %H:%M}"


def plan_for_metric(metric_code: str) -> dict[str, Any] | None:
    """找到该指标登记的调度计划，缺段靠它定位到具体调度窗口。"""
    plans = [p for p in store.rows("window_scheduler") if p.get("指标编码") == metric_code]
    return plans[0] if plans else None


def window_step(metric_code: str) -> timedelta:
    plan = plan_for_metric(metric_code)
    grain = str(plan.get("窗口粒度", "")) if plan else ""
    if "日" in grain:
        return timedelta(days=1)
    if "15" in grain or "刻" in grain:
        return timedelta(minutes=15)
    if "30" in grain:
        return timedelta(minutes=30)
    return timedelta(hours=1)


def enumerate_windows(
    start: datetime, end: datetime, step: timedelta
) -> Iterator[tuple[datetime, datetime, datetime, datetime]]:
    """按调度网格切窗并裁到查询区间，产出 (调度开始, 调度结束, 区间开始, 区间结束)。

    窗口锚定在调度网格上（小时窗锚在整点），保证每个窗口都能定位到真实的调度窗口；
    查询区间按左闭右开与其求交：首尾窗口可能被裁短，但不越过区间右端。
    """
    if step <= timedelta(0):
        step = timedelta(hours=1)
    # 把查询起点对齐到网格边界。
    epoch = datetime(1970, 1, 1)
    offset = (start - epoch).total_seconds()
    aligned = epoch + timedelta(seconds=(offset // step.total_seconds()) * step.total_seconds())
    cursor = aligned
    while cursor < end:
        natural_end = cursor + step
        if natural_end <= start:
            cursor = natural_end
            continue
        clip_start = max(cursor, start)
        clip_end = min(natural_end, end)
        if clip_start < clip_end:
            yield cursor, natural_end, clip_start, clip_end
        cursor = natural_end


def window_ref(plan_id: Any, start: datetime) -> str:
    return f"WS-{plan_id or 'NA'}-{start:%Y%m%d%H%M}"


def scheduling_window_identity(metric_code: str, start: datetime) -> dict[str, str]:
    """缺段也要能定位到调度窗口：返回计划、窗口粒度和窗口标识。"""
    plan = plan_for_metric(metric_code)
    return {
        "调度窗口": window_ref(plan.get("id") if plan else None, start),
        "计划名称": str(plan.get("计划名称", "")) if plan else "",
        "窗口粒度": str(plan.get("窗口粒度", "")) if plan else "小时窗口",
    }


def latest_confirmed(exp_code: str, metric_code: str, start: datetime) -> dict[str, Any] | None:
    """同一实验、同一指标、同一窗口下版本号最大的已确认结果。"""
    key = format_datetime(start)
    rows = [
        r for r in store.rows("metric_window_result")
        if r.get("实验编码") == exp_code
        and r.get("指标编码") == metric_code
        and str(r.get("窗口开始")) == key
        and str(r.get("结果状态", CONFIRMED)) == CONFIRMED
    ]
    if not rows:
        return None
    return max(rows, key=lambda r: int(r.get("版本号", 1)))


def running_recompute(exp_code: str, metric_code: str, start: datetime) -> dict[str, Any] | None:
    """该窗口是否存在执行中的补算；执行中不能当作已完成数据返回。"""
    key = format_datetime(start)
    rows = [
        j for j in store.rows("metric_recompute_job")
        if j.get("实验编码") == exp_code
        and j.get("指标编码") == metric_code
        and str(j.get("窗口开始")) == key
        and str(j.get("状态")) == "执行中"
    ]
    if not rows:
        return None
    return max(rows, key=lambda r: int(r.get("id", 0)))


def max_version_no(exp_code: str, metric_code: str) -> int:
    """该实验+指标当前确认版本线的最大版本号。"""
    versions = [
        int(r.get("版本号", 1))
        for r in store.rows("metric_result_version")
        if r.get("实验编码") == exp_code and r.get("指标编码") == metric_code
    ]
    results = [
        int(r.get("版本号", 1))
        for r in store.rows("metric_window_result")
        if r.get("实验编码") == exp_code
        and r.get("指标编码") == metric_code
        and str(r.get("结果状态", CONFIRMED)) == CONFIRMED
    ]
    return max(versions + results + [0])


def register_version(exp_code: str, metric_code: str, version_no: int, note: str) -> dict[str, Any]:
    """确保版本线里存在该版本号，供查询展示"当前确认版本"。"""
    for row in store.rows("metric_result_version"):
        if (
            row.get("实验编码") == exp_code
            and row.get("指标编码") == metric_code
            and int(row.get("版本号", 1)) == version_no
        ):
            return row
    rows = store.rows("metric_result_version")
    row = {
        "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
        "实验编码": exp_code,
        "指标编码": metric_code,
        "版本": f"v{version_no}",
        "版本号": version_no,
        "创建时间": datetime.now().replace(microsecond=0).isoformat(),
        "说明": note,
        "status": CONFIRMED,
    }
    rows.append(row)
    return row
