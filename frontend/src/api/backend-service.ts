import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  CheckListResult,
  EntryRow,
  OverviewResult,
  PageResult,
  QueryCatalog,
  QueryRound,
  RecomputeCheck,
  RecomputeJob,
  WindowResult,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

/** ---- 指标查询服务 ---- */

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    let detail = fallback
    try {
      const payload = await response.json()
      if (payload?.detail) detail = String(payload.detail)
    } catch {
      /* 保留兜底文案 */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function loadQueryCatalog(expCode?: string): Promise<QueryCatalog> {
  const query = expCode ? `?exp_code=${encodeURIComponent(expCode)}` : ''
  const response = await request(`/api/metric-query/catalog${query}`)
  return await readJson<QueryCatalog>(response, '实验与指标目录读取失败')
}

export async function createQueryRound(
  expCode: string,
  metricCode: string,
  start: string,
  end: string,
  pageSize: number,
): Promise<QueryRound> {
  const response = await request('/api/metric-query/rounds', {
    method: 'POST',
    body: JSON.stringify({
      exp_code: expCode,
      metric_code: metricCode,
      start,
      end,
      page_size: pageSize,
    }),
  })
  const payload = await readJson<{ round: QueryRound }>(response, '查询失败')
  return payload.round
}

export async function loadQueryRound(
  roundId: number,
  page: number,
  size: number,
): Promise<QueryRound> {
  const response = await request(
    `/api/metric-query/rounds/${roundId}?page=${page}&size=${size}`,
  )
  return await readJson<QueryRound>(response, '查询轮次读取失败')
}

export async function registerCheck(
  roundId: number,
  start: string,
  end: string,
): Promise<RecomputeCheck> {
  const response = await request(`/api/metric-query/rounds/${roundId}/checks`, {
    method: 'POST',
    body: JSON.stringify({ start, end }),
  })
  const payload = await readJson<{ check: RecomputeCheck }>(response, '核对登记失败')
  return payload.check
}

export async function listChecks(params: {
  expCode?: string
  metricCode?: string
  roundId?: number
  status?: string
}): Promise<CheckListResult> {
  const query = new URLSearchParams()
  if (params.expCode) query.set('exp_code', params.expCode)
  if (params.metricCode) query.set('metric_code', params.metricCode)
  if (params.roundId != null) query.set('round_id', String(params.roundId))
  if (params.status) query.set('status', params.status)
  const response = await request(`/api/metric-query/checks?${query.toString()}`)
  return await readJson<CheckListResult>(response, '核对列表读取失败')
}

export async function loadCheck(
  checkId: number,
): Promise<{ check: RecomputeCheck; jobs: RecomputeJob[] }> {
  const response = await request(`/api/metric-query/checks/${checkId}`)
  return await readJson(response, '核对详情读取失败')
}

export async function claimCheck(checkId: number): Promise<RecomputeCheck> {
  const response = await request(`/api/metric-query/checks/${checkId}/claim`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  const payload = await readJson<{ check: RecomputeCheck }>(response, '核对办理失败')
  return payload.check
}

export async function listRecomputeJobs(params: {
  expCode?: string
  metricCode?: string
  status?: string
}): Promise<{ items: RecomputeJob[]; total: number }> {
  const query = new URLSearchParams()
  if (params.expCode) query.set('exp_code', params.expCode)
  if (params.metricCode) query.set('metric_code', params.metricCode)
  if (params.status) query.set('status', params.status)
  const response = await request(`/api/metric-query/jobs?${query.toString()}`)
  return await readJson(response, '补算作业读取失败')
}

export async function completeRecomputeJob(
  jobId: number,
  value?: number,
): Promise<RecomputeJob> {
  const response = await request(`/api/metric-query/jobs/${jobId}/complete`, {
    method: 'POST',
    body: JSON.stringify({ value: value ?? null }),
  })
  const payload = await readJson<{ job: RecomputeJob }>(response, '补算完成失败')
  return payload.job
}

export async function loadWindowResults(
  expCode: string,
  metricCode: string,
  start?: string,
  end?: string,
): Promise<WindowResult[]> {
  const query = new URLSearchParams({ exp_code: expCode, metric_code: metricCode })
  if (start) query.set('start', start)
  if (end) query.set('end', end)
  const response = await request(`/api/metric-query/window-results?${query.toString()}`)
  const payload = await readJson<{ items: WindowResult[] }>(response, '指标窗口结果读取失败')
  return payload.items
}

export type WindowIdentity = {
  窗口开始: string
  窗口结束: string
  窗口: string
  指标值: number | null
  结果版本: string
  作业轮次: string
  调度窗口: string
  作业id: number | null
  作业名称: string
}

/** 指标计算作业读取窗口结果的作业轮次与调度窗口身份。 */
export async function loadWindowIdentity(
  expCode: string,
  metricCode: string,
  start?: string,
  end?: string,
): Promise<WindowIdentity[]> {
  const query = new URLSearchParams({ exp_code: expCode, metric_code: metricCode })
  if (start) query.set('start', start)
  if (end) query.set('end', end)
  const response = await request(`/api/metric_compute/window-identity?${query.toString()}`)
  const payload = await readJson<{ items: WindowIdentity[] }>(response, '作业窗口身份读取失败')
  return payload.items
}
