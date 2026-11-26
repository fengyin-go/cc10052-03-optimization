"""指标计算作业领域服务：管理实验指标的计算窗口、窗口水位推进与作业重试。

数据链路位置：指标计算层，消费指标口径中心的生效口径与曝光日志的去重数据，
产出指标结果写入显著性检验，是实验评估的核心计算环节。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.services.metric_query import metric_query_service
from app.store import store


class MetricComputeService(BaseModuleService):
    MODULE = "metric_compute"
    ENTITY = "计算作业"
    OPERATION_TERM = "计算"
    LIST_FIELDS = ["作业名称", "指标编码", "计算窗口", "窗口水位", "作业状态"]
    REQUIRED_FIELDS = ["作业名称", "指标编码", "计算窗口"]
    STATUS_ORDER = ["待执行", "执行中", "已完成", "计算失败"]
    ACTION_RULES = {"启动作业": "执行中", "重试计算": "计算失败"}
    NEGATIVE_ACTIONS = []

    # ---- 业务扩展：窗口计算与结果下发 ----

    def start_job(self, entry_id: int) -> dict[str, Any]:
        """启动计算作业，推进窗口水位并在完成后写入显著性检验批次。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待执行":
            return {"ok": False, "message": "仅待执行作业可启动"}
        metric = next(
            (m for m in store.rows("metric_catalog") if m.get("指标编码") == entry.get("指标编码")),
            None,
        )
        if metric is None or metric.get("status") != "已生效":
            return {"ok": False, "message": f"口径 {entry.get('指标编码')} 未生效，禁止计算"}
        entry["status"] = "已完成"
        entry["pending"] = False
        entry["作业状态"] = "已完成"
        entry["窗口水位"] = datetime.now(timezone.utc).isoformat()
        test_rows = store.rows("significance_test")
        test_rows.append({
            "id": max((int(r.get("id", 0)) for r in test_rows), default=0) + 1,
            "检验批次": f"ST-{entry_id}-{datetime.now(timezone.utc).timestamp():.0f}",
            "实验编码": f"EXP_-000{entry_id}",
            "指标编码": entry.get("指标编码", ""),
            "P值": "0.031",
            "置信区间": "[-0.021, 0.045]",
            "status": "待检验",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"作业 {entry_id} 计算完成并登记检验批次"}

    def retry_failed_job(self, entry_id: int) -> dict[str, Any]:
        """重试计算失败作业，重算窗口并登记异常事件。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "计算失败":
            return {"ok": False, "message": "仅计算失败作业可重试"}
        entry["status"] = "执行中"
        entry["pending"] = True
        entry["作业状态"] = "执行中"
        entry["重试次数"] = str(int(entry.get("重试次数", "0") or 0) + 1)
        anomaly_rows = store.rows("anomaly_metric")
        anomaly_rows.append({
            "id": max((int(r.get("id", 0)) for r in anomaly_rows), default=0) + 1,
            "异常编号": f"AN-{entry_id}-retry",
            "指标编码": entry.get("指标编码", ""),
            "基线区间": entry.get("计算窗口", ""),
            "观测值": "作业重试",
            "异常评分": "0.5",
            "status": "待确认",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"作业 {entry_id} 已进入重试（第 {entry['重试次数']} 次）"}

    def advance_watermark(self, entry_id: int, new_watermark: str) -> dict[str, Any]:
        """推进窗口水位并同步数据时效监控的最新水位。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or not new_watermark.strip():
            return {"ok": False, "message": "作业不存在或水位为空"}
        old = str(entry.get("窗口水位", ""))
        if new_watermark <= old:
            return {"ok": False, "message": "新水位必须晚于当前水位"}
        entry["窗口水位"] = new_watermark
        freshness_rows = store.rows("data_freshness")
        matched = [f for f in freshness_rows if f.get("监控对象") == f"metric_compute:{entry_id}"]
        if matched:
            matched[-1]["最新水位"] = new_watermark
            matched[-1]["status"] = "新鲜"
            matched[-1]["时效等级"] = "新鲜"
        else:
            freshness_rows.append({
                "id": max((int(r.get("id", 0)) for r in freshness_rows), default=0) + 1,
                "监控对象": f"metric_compute:{entry_id}",
                "数据域": "指标计算",
                "最新水位": new_watermark,
                "延迟分钟": "0",
                "时效等级": "新鲜",
                "status": "新鲜",
                "pending": True,
                "abnormal": False,
            })
        return {"ok": True, "message": f"水位已推进到 {new_watermark}"}

    def batch_execute_pending(self) -> dict[str, Any]:
        """批量执行全部待执行作业并汇总结果。"""
        pending_rows = [r for r in store.rows(self.MODULE) if r.get("status") == "待执行"]
        done, failed = 0, 0
        for row in pending_rows:
            result = self.start_job(int(row.get("id", 0)))
            if result.get("ok"):
                done += 1
            else:
                row["status"] = "计算失败"
                row["pending"] = False
                row["abnormal"] = True
                failed += 1
        return {"ok": True, "message": f"批量执行完成：成功 {done}，失败 {failed}", "success": done, "failed": failed}

    def consume_from_window_scheduler(self, metric_code: str) -> list[dict[str, Any]]:
        """读取窗口调度器中该指标的活跃计划，返回调度约束。"""
        return [
            {
                "计划名称": s.get("计划名称", ""),
                "窗口粒度": s.get("窗口粒度", ""),
                "下次窗口": s.get("下次窗口", ""),
            }
            for s in store.rows("window_scheduler")
            if s.get("指标编码") == metric_code and s.get("status") in ("待执行", "执行中")
        ]

    def consume_from_exposure_log(self, exp_code: str) -> dict[str, Any]:
        """统计曝光日志去重记录数，作为计算作业的分母数据。"""
        rows = [
            r for r in store.rows("exposure_log")
            if r.get("实验编码") == exp_code and r.get("status") == "已去重"
        ]
        return {
            "实验编码": exp_code,
            "去重曝光数": len(rows),
            "分组分布": {
                group: sum(1 for r in rows if r.get("分组名称") == group)
                for group in ("对照组", "实验组")
            },
        }

    def export_job_results(self, metric_code: str) -> list[dict[str, Any]]:
        """导出指定指标的完成作业清单，供报告生成器编排数据窗口。"""
        return [
            {
                "作业名称": r.get("作业名称", ""),
                "计算窗口": r.get("计算窗口", ""),
                "窗口水位": r.get("窗口水位", ""),
            }
            for r in store.rows(self.MODULE)
            if r.get("指标编码") == metric_code and r.get("status") == "已完成"
        ]

    # ---- 业务扩展：为指标查询提供窗口结果的作业轮次与调度窗口身份 ----

    def window_result_identity(
        self, exp_code: str, metric_code: str, start: str | None = None, end: str | None = None
    ) -> dict[str, Any]:
        """按实验+指标读取指标窗口结果，返回作业轮次与调度窗口身份。

        指标查询服务用这份数据展示已确认窗口；缺段窗口则由调度计划补出
        调度窗口身份（见 window_utils.scheduling_window_identity），二者口径一致。
        """
        result = metric_query_service.window_results(exp_code, metric_code, start, end)
        if not result.get("ok"):
            return {"ok": False, "message": result.get("message", "窗口结果读取失败")}
        items = []
        for row in result["items"]:
            job_id = row.get("作业id")
            job = self._find_result_job(row, job_id)
            items.append({
                "窗口开始": row.get("窗口开始", ""),
                "窗口结束": row.get("窗口结束", ""),
                "窗口": row.get("窗口", ""),
                "指标值": row.get("指标值"),
                "结果版本": row.get("结果版本", ""),
                "作业轮次": row.get("作业轮次", "") or (job.get("作业轮次", "") if job else ""),
                "调度窗口": row.get("调度窗口", ""),
                "作业id": job_id,
                "作业名称": self._job_name(job),
            })
        return {
            "ok": True,
            "实验编码": exp_code,
            "指标编码": metric_code,
            "items": items,
            "total": len(items),
        }

    def _find_result_job(self, row: dict[str, Any], job_id: Any) -> dict[str, Any] | None:
        """定位产生该窗口结果的作业：先找补算作业，再回退到计算作业清单。

        两类作业各自独立编号，必须按同一实验+指标+窗口匹配，不能只按 id 碰撞。
        """
        if job_id is not None:
            recompute = next(
                (j for j in store.rows("metric_recompute_job")
                 if int(j.get("id", 0)) == int(job_id)
                 and str(j.get("实验编码", "")) == str(row.get("实验编码", ""))
                 and str(j.get("指标编码", "")) == str(row.get("指标编码", ""))
                 and str(j.get("窗口开始", "")) == str(row.get("窗口开始", ""))),
                None,
            )
            if recompute is not None:
                return {**recompute, "_来源": "recompute"}
        start = str(row.get("窗口开始", ""))
        direct = next(
            (j for j in store.rows(self.MODULE)
             if str(j.get("实验编码", "")) == str(row.get("实验编码", ""))
             and str(j.get("指标编码", "")) == str(row.get("指标编码", ""))
             and start in str(j.get("计算窗口", ""))),
            None,
        )
        return {**direct, "_来源": "compute"} if direct is not None else None

    @staticmethod
    def _job_name(job: dict[str, Any] | None) -> str:
        if job is None:
            return ""
        if job.get("_来源") == "recompute":
            return f"补算 {job.get('补算编码', '')}"
        return str(job.get("作业名称", ""))

