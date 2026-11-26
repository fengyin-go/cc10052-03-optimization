"""指标查询服务：按实验+指标+区间查询指标窗口结果，并承载补算核对。

核心约束：
- 一次检索生成一轮查询轮次，轮次内保存窗口快照，翻页只读同一轮快照，
  后到的确认结果不会改变旧轮次里已经看到的缺段。
- 区间按左闭右开切窗，只取同一实验、同一指标的实际计算结果。
- 窗口区分已确认/缺段/未算完；缺段也带调度窗口身份，可据此发起补算核对。
- 补算核对在领取时真正领用当前确认结果：版本与登记基线不一致的窗口不采用，
  登记为版本冲突；执行中的补算只登记为未完成，绝不冒充已完成数据。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.window_utils import (
    CONFIRMED,
    MISSING,
    RUNNING,
    enumerate_windows,
    format_datetime,
    latest_confirmed,
    max_version_no,
    parse_datetime,
    plan_for_metric,
    register_version,
    running_recompute,
    scheduling_window_identity,
    window_label,
    window_step,
)
from app.store import store

CHECK_PENDING = "待领取"
CHECK_DONE = "已办理"


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _next_id(table: str) -> int:
    return max((int(r.get("id", 0)) for r in store.rows(table)), default=0) + 1


def _find(table: str, entry_id: int) -> dict[str, Any] | None:
    return next((r for r in store.rows(table) if int(r.get("id", 0)) == int(entry_id)), None)


def _result_value(seed: int) -> int:
    return 1000 + (abs(seed) % 500)


def _snapshot_window(
    exp_code: str,
    metric_code: str,
    grid_start: datetime,
    grid_end: datetime,
    clip_start: datetime,
    clip_end: datetime,
) -> dict[str, Any]:
    """取一个调度窗口在轮次生成时刻的结果快照，并裁到查询区间内展示。

    - 结果按调度网格（grid_start）定位，缺段与未算完都写清真实调度窗口身份。
    - 窗口展示区间裁到查询区间（clip_start/clip_end），左闭右开。
    """
    confirmed = latest_confirmed(exp_code, metric_code, grid_start)
    identity = scheduling_window_identity(metric_code, grid_start)
    clipped = clip_start != grid_start or clip_end != grid_end
    window = {
        "窗口开始": format_datetime(clip_start),
        "窗口结束": format_datetime(clip_end),
        "调度窗口开始": format_datetime(grid_start),
        "调度窗口结束": format_datetime(grid_end),
        "窗口": window_label(clip_start, clip_end),
        "是否裁切": clipped,
        "调度窗口": identity["调度窗口"],
        "计划名称": identity["计划名称"],
        "窗口粒度": identity["窗口粒度"],
        "指标值": None,
        "结果版本": "",
        "版本号": None,
        "结果id": None,
        "作业轮次": "",
        "补算编码": "",
        "说明": "",
    }
    if confirmed is not None:
        window.update({
            "状态": CONFIRMED,
            "指标值": confirmed.get("指标值"),
            "结果版本": confirmed.get("结果版本", ""),
            "版本号": int(confirmed.get("版本号", 1)),
            "结果id": confirmed.get("id"),
            "作业轮次": confirmed.get("作业轮次", ""),
            "调度窗口": confirmed.get("调度窗口", identity["调度窗口"]),
            "说明": (
                f"已确认结果（整窗 {window_label(grid_start, grid_end)}）"
                if clipped else "已确认结果"
            ),
        })
        return window
    job = running_recompute(exp_code, metric_code, grid_start)
    if job is not None:
        window.update({
            "状态": RUNNING,
            "作业轮次": job.get("作业轮次", ""),
            "补算编码": job.get("补算编码", ""),
            "调度窗口": job.get("调度窗口", identity["调度窗口"]),
            "说明": "补算执行中，暂不返回指标值",
        })
        return window
    window.update({"状态": MISSING, "说明": "该窗口尚无确认结果"})
    return window


class MetricQueryService:
    """指标窗口查询与补算核对的领域服务。"""

    # ---- 目录：可选实验与指标 ----

    def catalog(self, exp_code: str | None = None) -> dict[str, Any]:
        experiments = [
            {"实验编码": r.get("实验编码", ""), "实验名称": r.get("实验名称", "")}
            for r in store.rows("metric_query_experiment")
        ]
        metrics: list[dict[str, Any]] = []
        metric_rows = store.rows("metric_query_metric")
        if exp_code:
            metric_rows = [r for r in metric_rows if r.get("实验编码") == exp_code]
        seen: set[str] = set()
        for r in metric_rows:
            code = str(r.get("指标编码", ""))
            if code in seen:
                continue
            seen.add(code)
            metrics.append({
                "指标编码": code,
                "指标名称": r.get("指标名称", ""),
                "单位": r.get("单位", ""),
            })
        return {"experiments": experiments, "metrics": metrics}

    def _validate_scope(self, exp_code: str, metric_code: str) -> str | None:
        experiments = {r.get("实验编码") for r in store.rows("metric_query_experiment")}
        if exp_code not in experiments:
            return f"未知实验：{exp_code}"
        metrics = {
            r.get("指标编码")
            for r in store.rows("metric_query_metric")
            if r.get("实验编码") == exp_code
        }
        if metric_code not in metrics:
            return f"实验 {exp_code} 未登记指标 {metric_code}"
        return None

    # ---- 查询轮次 ----

    def create_round(
        self,
        exp_code: str,
        metric_code: str,
        start: str,
        end: str,
        page_size: int = 1,
    ) -> dict[str, Any]:
        error = self._validate_scope(exp_code, metric_code)
        if error:
            return {"ok": False, "message": error}
        try:
            start_dt = parse_datetime(start)
            end_dt = parse_datetime(end)
        except ValueError:
            return {"ok": False, "message": "查询区间时间格式不正确"}
        if start_dt >= end_dt:
            return {"ok": False, "message": "区间开始必须早于结束（左闭右开）"}
        step = window_step(metric_code)
        windows = [
            _snapshot_window(exp_code, metric_code, grid_start, grid_end, clip_start, clip_end)
            for grid_start, grid_end, clip_start, clip_end
            in enumerate_windows(start_dt, end_dt, step)
        ]
        if not windows:
            return {"ok": False, "message": "区间内没有可查询的窗口"}
        rounds = store.rows("metric_query_round")
        round_id = _next_id("metric_query_round")
        record = {
            "id": round_id,
            "查询号": f"QR-{round_id:04d}",
            "实验编码": exp_code,
            "指标编码": metric_code,
            "区间开始": format_datetime(start_dt),
            "区间结束": format_datetime(end_dt),
            "窗口粒度": str(plan_for_metric(metric_code).get("窗口粒度", "")) if plan_for_metric(metric_code) else "小时窗口",
            "结果基线版本": f"v{max_version_no(exp_code, metric_code)}",
            "页大小": max(1, int(page_size)),
            "创建时间": _now(),
            "窗口结果": windows,
            "状态": "已生成",
            "status": "已生成",
            "pending": False,
            "abnormal": False,
        }
        rounds.append(record)
        return {"ok": True, "message": f"查询轮次 {record['查询号']} 已生成，共 {len(windows)} 个窗口", "round": self._round_payload(record)}

    def _round_payload(self, record: dict[str, Any], page: int = 1, size: int | None = None) -> dict[str, Any]:
        windows = list(record.get("窗口结果", []))
        size = max(1, int(size or record.get("页大小", 1)))
        total = len(windows)
        max_page = max(1, (total + size - 1) // size)
        page = min(max(1, int(page)), max_page)
        start = (page - 1) * size
        items = windows[start:start + size]
        counts = {
            CONFIRMED: sum(1 for w in windows if w.get("状态") == CONFIRMED),
            MISSING: sum(1 for w in windows if w.get("状态") == MISSING),
            RUNNING: sum(1 for w in windows if w.get("状态") == RUNNING),
        }
        return {
            "round_id": record.get("id"),
            "查询号": record.get("查询号", ""),
            "实验编码": record.get("实验编码", ""),
            "指标编码": record.get("指标编码", ""),
            "区间开始": record.get("区间开始", ""),
            "区间结束": record.get("区间结束", ""),
            "窗口粒度": record.get("窗口粒度", ""),
            "结果基线版本": record.get("结果基线版本", ""),
            "创建时间": record.get("创建时间", ""),
            "total": total,
            "page": page,
            "size": size,
            "max_page": max_page,
            "items": items,
            "counts": counts,
        }

    def get_round(self, round_id: int, page: int = 1, size: int | None = None) -> dict[str, Any]:
        record = _find("metric_query_round", round_id)
        if record is None:
            return {"ok": False, "message": f"查询轮次 {round_id} 不存在"}
        return {"ok": True, **self._round_payload(record, page=page, size=size)}

    # ---- 补算核对 ----

    def _overlap_windows(
        self, record: dict[str, Any], start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """把核对区间与轮次窗口按左闭右开求交，只保留有交集的部分。"""
        selected = []
        for window in record.get("窗口结果", []):
            ws = parse_datetime(window.get("窗口开始"))
            we = parse_datetime(window.get("窗口结束"))
            left, right = max(ws, start), min(we, end)
            if left >= right:
                continue
            item = dict(window)
            item["选定开始"] = format_datetime(left)
            item["选定结束"] = format_datetime(right)
            selected.append(item)
        return selected

    def _ensure_recompute_job(
        self, exp_code: str, metric_code: str, window: dict[str, Any], check_id: int
    ) -> dict[str, Any] | None:
        """缺段窗口登记补算作业；已有执行中作业则复用，不重复开单。

        作业按调度窗口（整窗）登记，保证与调度器的网格与窗口标识一致。
        """
        grid_start = parse_datetime(window.get("调度窗口开始") or window.get("窗口开始"))
        grid_end = parse_datetime(window.get("调度窗口结束") or window.get("窗口结束"))
        if latest_confirmed(exp_code, metric_code, grid_start) is not None:
            return None
        existing = running_recompute(exp_code, metric_code, grid_start)
        if existing is not None:
            return existing
        jobs = store.rows("metric_recompute_job")
        job_id = _next_id("metric_recompute_job")
        day = grid_start.strftime("%Y%m%d")
        seq = sum(1 for j in jobs if str(j.get("作业轮次", "")).startswith(f"ROUND-{day}-")) + 1
        job = {
            "id": job_id,
            "补算编码": f"RJOB-{job_id:04d}",
            "实验编码": exp_code,
            "指标编码": metric_code,
            "窗口开始": format_datetime(grid_start),
            "窗口结束": format_datetime(grid_end),
            "窗口": window.get("窗口"),
            "调度窗口": window.get("调度窗口", ""),
            "作业轮次": f"ROUND-{day}-{seq:02d}",
            "状态": "执行中",
            "指标值": None,
            "结果版本": "",
            "版本号": None,
            "来源": "缺段补算",
            "核对id": check_id,
            "创建时间": _now(),
            "完成时间": None,
        }
        jobs.append(job)
        return job

    def register_check(self, round_id: int, start: str, end: str) -> dict[str, Any]:
        record = _find("metric_query_round", round_id)
        if record is None:
            return {"ok": False, "message": f"查询轮次 {round_id} 不存在"}
        try:
            start_dt = parse_datetime(start)
            end_dt = parse_datetime(end)
        except ValueError:
            return {"ok": False, "message": "核对区间时间格式不正确"}
        if start_dt >= end_dt:
            return {"ok": False, "message": "核对区间开始必须早于结束（左闭右开）"}
        selected = self._overlap_windows(record, start_dt, end_dt)
        if not selected:
            return {"ok": False, "message": "所选区间不在查询轮次内，无法登记核对"}
        exp_code = str(record.get("实验编码", ""))
        metric_code = str(record.get("指标编码", ""))
        checks = store.rows("metric_recompute_check")
        check_id = _next_id("metric_recompute_check")
        available = [w for w in selected if w.get("状态") == CONFIRMED]
        unfinished = [w for w in selected if w.get("状态") != CONFIRMED]
        check = {
            "id": check_id,
            "核对编号": f"RC-{check_id:04d}",
            "实验编码": exp_code,
            "指标编码": metric_code,
            "区间开始": format_datetime(start_dt),
            "区间结束": format_datetime(end_dt),
            "来源查询轮次": record.get("id"),
            "来源查询号": record.get("查询号", ""),
            "状态": CHECK_PENDING,
            "status": CHECK_PENDING,
            "pending": True,
            "abnormal": False,
            "创建时间": _now(),
            "领取时间": "",
            "版本基线": f"v{max_version_no(exp_code, metric_code)}",
            "登记快照": selected,
            "登记可用窗口": [w.get("窗口") for w in available],
            "登记未完成部分": [
                {"窗口": w.get("窗口"), "状态": w.get("状态"), "调度窗口": w.get("调度窗口", "")}
                for w in unfinished
            ],
            "采用窗口": [],
            "未完成部分": [
                {"窗口": w.get("窗口"), "状态": w.get("状态"), "调度窗口": w.get("调度窗口", ""), "原因": ""}
                for w in unfinished
            ],
            "是否冲突": False,
            "说明": f"登记时可用 {len(available)} 个窗口，未完成 {len(unfinished)} 个",
        }
        checks.append(check)
        for window in unfinished:
            if window.get("状态") == MISSING:
                self._ensure_recompute_job(exp_code, metric_code, window, check_id)
        return {"ok": True, "message": f"核对 {check['核对编号']} 已登记，等待领取", "check": self._check_payload(check)}

    def claim_check(self, check_id: int) -> dict[str, Any]:
        """领取并办理核对：领用当前确认结果，登记采用窗口与未完成部分。"""
        check = _find("metric_recompute_check", check_id)
        if check is None:
            return {"ok": False, "message": f"核对 {check_id} 不存在"}
        if check.get("状态") != CHECK_PENDING:
            return {"ok": False, "message": f"核对 {check.get('核对编号')} 已领取，不能重复办理"}
        exp_code = str(check.get("实验编码", ""))
        metric_code = str(check.get("指标编码", ""))
        adopted: list[dict[str, Any]] = []
        unfinished: list[dict[str, Any]] = []
        conflict = False
        per_window: list[dict[str, Any]] = []
        for window in check.get("登记快照", []):
            grid_start = parse_datetime(window.get("调度窗口开始") or window.get("窗口开始"))
            current = latest_confirmed(exp_code, metric_code, grid_start)
            expected_status = window.get("状态")
            entry = {
                "窗口": window.get("窗口"),
                "调度窗口": window.get("调度窗口", ""),
                "登记状态": expected_status,
                "是否采用": False,
                "原因": "",
            }
            if current is None:
                running = running_recompute(exp_code, metric_code, grid_start)
                reason = "补算执行中，尚未完成" if running else "仍无确认结果"
                entry.update({"当前状态": RUNNING if running else MISSING, "原因": reason})
                unfinished.append({
                    "窗口": window.get("窗口"), "状态": RUNNING if running else MISSING,
                    "调度窗口": window.get("调度窗口", ""), "原因": reason,
                })
            else:
                current_version = int(current.get("版本号", 1))
                expected_version = window.get("版本号")
                same_version = (
                    expected_status == CONFIRMED and expected_version == current_version
                )
                if same_version:
                    entry.update({
                        "当前状态": CONFIRMED,
                        "是否采用": True,
                        "采用版本": current.get("结果版本", f"v{current_version}"),
                        "指标值": current.get("指标值"),
                        "作业轮次": current.get("作业轮次", ""),
                    })
                    adopted.append({
                        "窗口": window.get("窗口"),
                        "调度窗口": window.get("调度窗口", ""),
                        "版本": current.get("结果版本", f"v{current_version}"),
                        "指标值": current.get("指标值"),
                        "作业轮次": current.get("作业轮次", ""),
                    })
                else:
                    conflict = True
                    reason = (
                        f"版本冲突：登记为{expected_status}"
                        f"{'（' + str(window.get('结果版本')) + '）' if expected_status == CONFIRMED else ''}，"
                        f"领取时已有 {current.get('结果版本', f'v{current_version}')} 确认结果"
                    )
                    entry.update({"当前状态": CONFIRMED, "原因": reason})
                    unfinished.append({
                        "窗口": window.get("窗口"), "状态": CONFIRMED,
                        "调度窗口": window.get("调度窗口", ""), "原因": reason,
                    })
            per_window.append(entry)
        check["状态"] = CHECK_DONE
        check["status"] = CHECK_DONE
        check["pending"] = False
        check["领取时间"] = _now()
        check["领用人"] = "数据工程组"
        check["采用窗口"] = adopted
        check["未完成部分"] = unfinished
        check["逐窗口"] = per_window
        check["是否冲突"] = conflict
        check["异常"] = conflict
        check["abnormal"] = conflict
        if conflict:
            check["说明"] = f"领取时发生版本冲突，采用 {len(adopted)} 个窗口，{len(unfinished)} 个未完成"
        elif unfinished:
            check["说明"] = f"已领用 {len(adopted)} 个窗口，{len(unfinished)} 个尚未完成"
        else:
            check["说明"] = f"已领用全部 {len(adopted)} 个窗口的确认结果"
        return {"ok": True, "message": check["说明"], "check": self._check_payload(check)}

    def _check_payload(self, check: dict[str, Any]) -> dict[str, Any]:
        return dict(check)

    def list_checks(
        self,
        exp_code: str | None = None,
        metric_code: str | None = None,
        round_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        rows = list(store.rows("metric_recompute_check"))
        if exp_code:
            rows = [r for r in rows if r.get("实验编码") == exp_code]
        if metric_code:
            rows = [r for r in rows if r.get("指标编码") == metric_code]
        if round_id is not None:
            rows = [r for r in rows if int(r.get("来源查询轮次", 0)) == int(round_id)]
        if status:
            rows = [r for r in rows if r.get("状态") == status]
        rows.sort(key=lambda r: int(r.get("id", 0)), reverse=True)
        total = len(rows)
        start = (page - 1) * size
        return {
            "items": [self._check_payload(r) for r in rows[start:start + size]],
            "total": total,
            "page": page,
            "size": size,
        }

    def get_check(self, check_id: int) -> dict[str, Any]:
        check = _find("metric_recompute_check", check_id)
        if check is None:
            return {"ok": False, "message": f"核对 {check_id} 不存在"}
        exp_code = str(check.get("实验编码", ""))
        metric_code = str(check.get("指标编码", ""))
        windows = {
            str(w.get("窗口开始"))
            for w in check.get("登记快照", [])
        }
        jobs = [
            dict(j) for j in store.rows("metric_recompute_job")
            if j.get("实验编码") == exp_code
            and j.get("指标编码") == metric_code
            and (
                int(j.get("核对id") or 0) == int(check_id)
                or str(j.get("窗口开始")) in windows
            )
        ]
        jobs.sort(key=lambda r: int(r.get("id", 0)))
        return {"ok": True, "check": self._check_payload(check), "jobs": jobs}

    # ---- 补算作业 ----

    def list_jobs(
        self,
        exp_code: str | None = None,
        metric_code: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        rows = list(store.rows("metric_recompute_job"))
        if exp_code:
            rows = [r for r in rows if r.get("实验编码") == exp_code]
        if metric_code:
            rows = [r for r in rows if r.get("指标编码") == metric_code]
        if status:
            rows = [r for r in rows if r.get("状态") == status]
        rows.sort(key=lambda r: int(r.get("id", 0)))
        return {"items": [dict(r) for r in rows], "total": len(rows)}

    def complete_job(self, job_id: int, value: Any = None) -> dict[str, Any]:
        """补算完成：推出版本并写入确认结果，供之后的新查询看到。"""
        job = _find("metric_recompute_job", job_id)
        if job is None:
            return {"ok": False, "message": f"补算作业 {job_id} 不存在"}
        if job.get("状态") != "执行中":
            return {"ok": False, "message": f"补算作业 {job.get('补算编码')} 不是执行中，不能重复完成"}
        exp_code = str(job.get("实验编码", ""))
        metric_code = str(job.get("指标编码", ""))
        start = parse_datetime(job.get("窗口开始"))
        end = parse_datetime(job.get("窗口结束"))
        version_no = max_version_no(exp_code, metric_code) + 1
        if value is None or str(value).strip() == "":
            try:
                value = _result_value(int(job.get("id", 0)) * 37)
            except (TypeError, ValueError):
                value = 1000
        results = store.rows("metric_window_result")
        result = {
            "id": max((int(r.get("id", 0)) for r in results), default=0) + 1,
            "实验编码": exp_code,
            "指标编码": metric_code,
            "窗口开始": format_datetime(start),
            "窗口结束": format_datetime(end),
            "窗口": job.get("窗口", window_label(start, end)),
            "指标值": value,
            "结果版本": f"v{version_no}",
            "版本号": version_no,
            "结果状态": CONFIRMED,
            "作业轮次": job.get("作业轮次", ""),
            "调度窗口": job.get("调度窗口", ""),
            "作业id": job.get("id"),
            "确认时间": _now(),
        }
        results.append(result)
        register_version(exp_code, metric_code, version_no, f"补算作业 {job.get('补算编码')} 完成")
        job["状态"] = "已完成"
        job["pending"] = False
        job["指标值"] = value
        job["结果版本"] = result["结果版本"]
        job["版本号"] = version_no
        job["完成时间"] = _now()
        return {
            "ok": True,
            "message": f"补算作业 {job.get('补算编码')} 已完成，推出 {result['结果版本']}",
            "job": dict(job),
            "result": dict(result),
        }

    # ---- 窗口结果（供指标计算作业核对口径） ----

    def window_results(
        self, exp_code: str, metric_code: str, start: str | None = None, end: str | None = None
    ) -> dict[str, Any]:
        error = self._validate_scope(exp_code, metric_code)
        if error:
            return {"ok": False, "message": error}
        rows = [
            dict(r) for r in store.rows("metric_window_result")
            if r.get("实验编码") == exp_code and r.get("指标编码") == metric_code
        ]
        if start:
            start_dt = parse_datetime(start)
            rows = [r for r in rows if parse_datetime(r.get("窗口开始")) >= start_dt]
        if end:
            end_dt = parse_datetime(end)
            rows = [r for r in rows if parse_datetime(r.get("窗口开始")) < end_dt]
        rows.sort(key=lambda r: str(r.get("窗口开始")))
        return {"ok": True, "items": rows, "total": len(rows)}


metric_query_service = MetricQueryService()
