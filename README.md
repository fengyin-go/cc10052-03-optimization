# 实验指标分析与归因评估平台

支撑AB实验分组、指标口径计算、显著性检验、归因分析与报告分发的实验评估平台

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8022/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5202/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8022`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 事件接入 | `event_stream` | 事件定义 | 事件编码、事件名称、属性字段 |
| 实验设计 | `exp_design` | 实验方案 | 实验编码、实验名称、分组策略 |
| 分组分配器 | `variant_assign` | 分组结果 | 分配批次、用户标识、实验编码 |
| 指标口径中心 | `metric_catalog` | 指标定义 | 指标编码、指标名称、计算口径 |
| 指标计算作业 | `metric_compute` | 计算作业 | 作业名称、指标编码、计算窗口 |
| 显著性检验 | `significance_test` | 检验结果 | 检验批次、实验编码、指标编码 |
| 归因分析器 | `attr_analysis` | 归因结果 | 归因批次、实验编码、贡献因子 |
| 人群圈选器 | `cohort_builder` | 人群包 | 人群编码、人群名称、圈选条件 |
| 报告生成器 | `report_gen` | 分析报告 | 报告编码、实验编码、报告模板 |
| 报告分发 | `report_dist` | 分发记录 | 分发批次、报告编码、接收方 |
| 窗口调度器 | `window_scheduler` | 调度计划 | 计划名称、指标编码、窗口粒度 |
| 数据时效监控 | `data_freshness` | 时效记录 | 监控对象、数据域、最新水位 |
| 指标异常检测 | `anomaly_metric` | 异常事件 | 异常编号、指标编码、基线区间 |
| 实验归档库 | `exp_archive` | 归档实验 | 实验编码、结束时间、结论摘要 |
| 样本量核对 | `sample_ratio` | 核对结果 | 核对批次、实验编码、计划比例 |
| AA预检器 | `aa_check` | AA检验 | 检验编码、实验编码、检验窗口 |
| 切片分析器 | `segment_slice` | 切片结果 | 切片批次、实验编码、切片维度 |
| 曝光日志接入 | `exposure_log` | 曝光记录 | 日志批次、实验编码、用户标识 |
| 结论评审队列 | `conclusion_review` | 评审记录 | 记录编号、实验编码、评审结论 |
| 指标查询服务 | `metric_api` | 查询接口 | 接口编码、指标编码、服务对象 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 指标查询服务：窗口查询与补算核对

`metric_api` 与 `metric_compute` 使用专用工作台，围绕"选定实验+指标→检索区间→
按轮次翻页→从缺段发起补算核对"展开，逻辑集中在
`backend/app/services/metric_query.py` 与 `backend/app/services/window_utils.py`。

- 一次检索生成一个**查询轮次**，轮次内保存窗口快照；翻页只换页码，不重新取数，
  后到的确认结果不会改写旧轮次里已经看到的缺段。
- 区间按**左闭右开**与调度网格求交：窗口锚定在调度网格（小时窗锚在整点），首尾窗口
  可被查询区间裁短，但都带真实**调度窗口**标识，缺段据此定位可补算的窗口。
- 窗口只取**同一实验、同一指标**的实际结果，状态区分**已确认 / 缺段 / 未算完**；
  执行中的补算只标"未算完"，不冒充已完成数据。
- 补算核对在**领取时**才真正领用当前确认结果：与登记基线版本不一致的窗口登记为
  **版本冲突**，执行中的补算登记为未完成；核对载明每个窗口"是否实际采用"。
- 补算完成会推出新的确认版本，**新的查询**能看到结果；旧轮次仍按快照复查原缺段。

主要接口（均在 `/api` 下）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/metric-query/catalog` | 可选实验与该实验下指标 |
| POST | `/metric-query/rounds` | 按实验+指标+区间生成查询轮次（返回第一页快照） |
| GET | `/metric-query/rounds/{id}?page=&size=` | 同一轮指定页（翻页） |
| POST | `/metric-query/rounds/{id}/checks` | 从选定区间登记补算核对 |
| GET/POST | `/metric-query/checks`、`/checks/{id}`、`/checks/{id}/claim` | 列出/查看/领取办理核对 |
| GET/POST | `/metric-query/jobs`、`/jobs/{id}/complete` | 补算作业与完成（推出新版本） |
| GET | `/metric_compute/window-identity` | 指标窗口结果对应的作业轮次与调度窗口身份 |

前端对应 `MetricApiView`（窗口查询 + 补算核对）与 `MetricComputeView`
（窗口结果身份 + 继续办理核对）。

领域：数据工程
子方向：数据分析与数据应用
