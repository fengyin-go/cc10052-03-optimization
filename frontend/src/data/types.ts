/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

/** 指标查询服务：目录、查询轮次、窗口结果与补算核对。 */

export type QueryExperiment = {
  实验编码: string
  实验名称: string
}

export type QueryMetric = {
  指标编码: string
  指标名称: string
  单位: string
}

export type QueryCatalog = {
  experiments: QueryExperiment[]
  metrics: QueryMetric[]
}

export type WindowStatus = '已确认' | '缺段' | '未算完'

export type WindowResult = {
  窗口开始: string
  窗口结束: string
  调度窗口开始: string
  调度窗口结束: string
  窗口: string
  是否裁切: boolean
  调度窗口: string
  计划名称: string
  窗口粒度: string
  指标值: number | null
  结果版本: string
  版本号: number | null
  结果id: number | null
  作业轮次: string
  补算编码: string
  说明: string
  状态: WindowStatus
}

export type QueryRound = {
  round_id: number
  查询号: string
  实验编码: string
  指标编码: string
  区间开始: string
  区间结束: string
  窗口粒度: string
  结果基线版本: string
  创建时间: string
  total: number
  page: number
  size: number
  max_page: number
  items: WindowResult[]
  counts: Record<WindowStatus, number>
}

export type CheckWindow = {
  窗口: string
  状态: WindowStatus | string
  调度窗口: string
  原因?: string
}

export type AdoptedWindow = {
  窗口: string
  调度窗口: string
  版本: string
  指标值: number | null
  作业轮次: string
}

export type CheckWindowDetail = {
  窗口: string
  调度窗口: string
  登记状态: string
  当前状态?: string
  是否采用: boolean
  原因?: string
  版本?: string
  指标值?: number | null
  作业轮次?: string
}

export type RecomputeCheck = {
  id: number
  核对编号: string
  实验编码: string
  指标编码: string
  区间开始: string
  区间结束: string
  来源查询轮次: number
  来源查询号: string
  状态: string
  status: string
  创建时间: string
  领取时间: string
  版本基线: string
  登记可用窗口: string[]
  登记未完成部分: CheckWindow[]
  采用窗口: AdoptedWindow[]
  未完成部分: CheckWindow[]
  逐窗口: CheckWindowDetail[]
  是否冲突: boolean
  说明: string
}

export type RecomputeJob = {
  id: number
  补算编码: string
  实验编码: string
  指标编码: string
  窗口开始: string
  窗口结束: string
  窗口: string
  调度窗口: string
  作业轮次: string
  状态: string
  指标值: number | null
  结果版本: string
  来源: string
  核对id: number | null
  创建时间: string
  完成时间: string | null
}

export type CheckListResult = {
  items: RecomputeCheck[]
  total: number
  page: number
  size: number
}

