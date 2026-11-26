"""指标计算作业专用接口：向指标查询服务提供窗口结果的作业轮次与调度窗口身份。

放在通用 `/{module}` 路由之前注册，避免 `window-identity` 被当成作业 id。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services import service_for

router = APIRouter(prefix="/api/metric_compute", tags=["指标计算作业"])


@router.get("/window-identity")
def window_identity(
    exp_code: str = Query(...),
    metric_code: str = Query(...),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> dict[str, Any]:
    """指标窗口结果对应的作业轮次与调度窗口身份，供指标查询服务展示。"""
    service = service_for("metric_compute")
    result = service.window_result_identity(exp_code, metric_code, start, end)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "窗口结果读取失败"))
    return result
