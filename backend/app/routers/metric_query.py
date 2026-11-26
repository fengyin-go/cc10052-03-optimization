"""指标查询服务专用接口：实验/指标目录、查询轮次、分页快照与补算核对。

这些路径比通用资源路由更具体，必须在通用 `/{module}` 路由之前注册，
否则 `/api/metric-query/catalog` 会被当成模块 `metric-query` 的详情查询。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.metric_query import metric_query_service

router = APIRouter(prefix="/api/metric-query", tags=["指标查询服务"])


class RoundPayload(BaseModel):
    exp_code: str
    metric_code: str
    start: str
    end: str
    page_size: int = Field(default=1, ge=1, le=200)


class CheckPayload(BaseModel):
    start: str
    end: str


class CompletePayload(BaseModel):
    value: Any | None = None


def _require_ok(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "操作失败"))
    return result


@router.get("/catalog")
def catalog(exp_code: str | None = Query(default=None)) -> dict[str, Any]:
    """可选实验，以及该实验下可选指标。"""
    return metric_query_service.catalog(exp_code)


@router.post("/rounds")
def create_round(payload: RoundPayload) -> dict[str, Any]:
    """按实验+指标+区间生成一次查询轮次，并返回第一页窗口结果。"""
    return _require_ok(metric_query_service.create_round(
        payload.exp_code, payload.metric_code, payload.start, payload.end, payload.page_size,
    ))


@router.get("/rounds/{round_id}")
def get_round(
    round_id: int,
    page: int = Query(default=1, ge=1),
    size: int | None = Query(default=None, ge=1, le=200),
) -> dict[str, Any]:
    """读取同一轮查询的指定页：翻页只动页码，不重新取数。"""
    return _require_ok(metric_query_service.get_round(round_id, page=page, size=size))


@router.post("/rounds/{round_id}/checks")
def register_check(round_id: int, payload: CheckPayload) -> dict[str, Any]:
    """从查询轮次里选定的区间登记补算核对。"""
    return _require_ok(metric_query_service.register_check(round_id, payload.start, payload.end))


@router.get("/checks")
def list_checks(
    exp_code: str | None = Query(default=None),
    metric_code: str | None = Query(default=None),
    round_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    return metric_query_service.list_checks(
        exp_code=exp_code, metric_code=metric_code, round_id=round_id,
        status=status, page=page, size=size,
    )


@router.get("/checks/{check_id}")
def get_check(check_id: int) -> dict[str, Any]:
    return _require_ok(metric_query_service.get_check(check_id))


@router.post("/checks/{check_id}/claim")
def claim_check(check_id: int) -> dict[str, Any]:
    """领取并办理核对：真正领用确认结果，登记采用窗口与未完成部分。"""
    return _require_ok(metric_query_service.claim_check(check_id))


@router.get("/jobs")
def list_jobs(
    exp_code: str | None = Query(default=None),
    metric_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    return metric_query_service.list_jobs(exp_code=exp_code, metric_code=metric_code, status=status)


@router.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict[str, Any]:
    result = metric_query_service.list_jobs()
    job = next((j for j in result["items"] if int(j.get("id", 0)) == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"补算作业 {job_id} 不存在")
    results = [r for r in metric_query_service.window_results(
        str(job.get("实验编码", "")), str(job.get("指标编码", "")))["items"]
        if int(r.get("作业id") or 0) == job_id]
    return {"job": job, "results": results}


@router.post("/jobs/{job_id}/complete")
def complete_job(job_id: int, payload: CompletePayload) -> dict[str, Any]:
    """补算完成：推出新版本并写入确认结果，之后的新查询可见。"""
    return _require_ok(metric_query_service.complete_job(job_id, payload.value))


@router.get("/window-results")
def window_results(
    exp_code: str = Query(...),
    metric_code: str = Query(...),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> dict[str, Any]:
    """指标计算作业读取指标窗口结果，核对作业轮次与调度窗口身份。"""
    return _require_ok(metric_query_service.window_results(exp_code, metric_code, start, end))
