"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import metric_compute, metric_query, resource

# 具体路径（/api/metric-query/*、/api/metric_compute/window-identity）必须排在
# 通用 /api/{module} 之前，否则会被动态路径抢先匹配。
ROUTERS = [metric_query, metric_compute, resource]
