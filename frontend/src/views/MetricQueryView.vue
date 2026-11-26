<template>
  <section class="page" data-testid="metric-query-view">
    <header class="page-head">
      <div>
        <h2>指标查询服务</h2>
        <p class="page-desc">
          选定实验与指标后检索时间区间：按左闭右开裁窗，只返回同一实验、同一指标的实际计算结果。
          翻页固定在同一轮查询结果上，缺段可定位到调度窗口并发起补算核对。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="open-checks" type="button" @click="showChecks = !showChecks">
          {{ showChecks ? '收起补算核对' : '查看补算核对' }}
        </button>
      </div>
    </header>

    <form class="filter-bar query-form" data-testid="query-form" @submit.prevent="runQuery">
      <label class="filter-item">
        <span>实验</span>
        <select v-model="expCode" data-testid="select-experiment" @change="onExperimentChange">
          <option value="" disabled>请选择实验</option>
          <option v-for="item in experiments" :key="item.实验编码" :value="item.实验编码">
            {{ item.实验编码 }} · {{ item.实验名称 }}
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>指标</span>
        <select v-model="metricCode" data-testid="select-metric">
          <option value="" disabled>请选择指标</option>
          <option v-for="item in metrics" :key="item.指标编码" :value="item.指标编码">
            {{ item.指标编码 }} · {{ item.指标名称 }}
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>开始（含）</span>
        <input v-model="startAt" data-testid="input-start" type="datetime-local" step="60" />
      </label>
      <label class="filter-item">
        <span>结束（不含）</span>
        <input v-model="endAt" data-testid="input-end" type="datetime-local" step="60" />
      </label>
      <label class="filter-item">
        <span>每页窗口数</span>
        <input v-model.number="pageSize" data-testid="input-page-size" type="number" min="1" max="50" />
      </label>
      <button class="btn primary" data-testid="run-query" type="submit" :disabled="loading">
        {{ loading ? '检索中…' : '检索' }}
      </button>
    </form>

    <p v-if="errorMessage" class="error-text" data-testid="query-error">{{ errorMessage }}</p>

    <template v-if="activeRound">
      <div class="round-bar" data-testid="round-summary">
        <span><strong>{{ activeRound.查询号 }}</strong> · {{ activeRound.实验编码 }} / {{ activeRound.指标编码 }}</span>
        <span class="muted">
          {{ shortTime(activeRound.区间开始) }} ~ {{ shortTime(activeRound.区间结束) }}
          （左闭右开，{{ activeRound.窗口粒度 }}）
        </span>
        <span class="muted">基线 {{ activeRound.结果基线版本 }}</span>
        <span class="round-counts">
          <span class="tag tag-ok">已确认 {{ activeRound.counts['已确认'] }}</span>
          <span class="tag tag-warn">缺段 {{ activeRound.counts['缺段'] }}</span>
          <span class="tag tag-run">未算完 {{ activeRound.counts['未算完'] }}</span>
        </span>
      </div>

      <table class="data-table" data-testid="window-table">
        <thead>
          <tr>
            <th>窗口</th>
            <th>状态</th>
            <th>指标值</th>
            <th>结果版本</th>
            <th>作业轮次</th>
            <th>调度窗口</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in activeRound.items"
            :key="row.窗口开始"
            :data-testid="`window-${row.窗口开始}`"
            :data-status="row.状态"
            :data-scheduling-window="row.调度窗口"
            :class="`row-${statusClass(row.状态)}`"
          >
            <td>{{ row.窗口 }}</td>
            <td>
              <span class="tag" :class="`tag-${statusClass(row.状态)}`">{{ row.状态 }}</span>
            </td>
            <td>
              <template v-if="row.状态 === '已确认'">{{ row.指标值 }}</template>
              <span v-else class="muted">{{ row.状态 === '未算完' ? '补算执行中' : '—' }}</span>
            </td>
            <td>{{ row.状态 === '已确认' ? row.结果版本 : '—' }}</td>
            <td class="mono">{{ row.作业轮次 || '—' }}</td>
            <td class="mono">
              {{ row.调度窗口 }}
              <span
                v-if="row.是否裁切"
                class="muted"
                :title="`调度窗口整窗：${shortTime(row.调度窗口开始)} ~ ${shortTime(row.调度窗口结束)}`"
              >
                （裁切至 {{ row.窗口 }}）
              </span>
            </td>
            <td>{{ row.说明 }}</td>
          </tr>
          <tr v-if="!activeRound.items.length">
            <td colspan="7" class="empty-state">该页没有窗口</td>
          </tr>
        </tbody>
      </table>

      <div class="pager" data-testid="pager">
        <button
          class="btn"
          data-testid="prev-page"
          type="button"
          :disabled="activeRound.page <= 1 || paging"
          @click="goPage(activeRound.page - 1)"
        >
          上一页
        </button>
        <span data-testid="page-indicator">
          第 {{ activeRound.page }} / {{ activeRound.max_page }} 页 · 共 {{ activeRound.total }} 个窗口
        </span>
        <button
          class="btn"
          data-testid="next-page"
          type="button"
          :disabled="activeRound.page >= activeRound.max_page || paging"
          @click="goPage(activeRound.page + 1)"
        >
          下一页
        </button>
      </div>

      <section class="check-form" data-testid="check-form">
        <h4>从选中区间发起补算核对</h4>
        <p class="muted">
          选定区间按左闭右开与查询窗口求交，登记后可用于办理补算；缺段会定位到调度窗口。
        </p>
        <div class="check-form-row">
          <label class="filter-item">
            <span>核对开始（含）</span>
            <input v-model="checkStart" data-testid="check-start" type="datetime-local" step="60" />
          </label>
          <label class="filter-item">
            <span>核对结束（不含）</span>
            <input v-model="checkEnd" data-testid="check-end" type="datetime-local" step="60" />
          </label>
          <button class="btn primary" data-testid="register-check" type="button" @click="submitCheck">
            登记补算核对
          </button>
          <button class="btn ghost" data-testid="select-missing" type="button" @click="selectMissingRange">
            选中当前缺段范围
          </button>
        </div>
        <p v-if="lastCheck" class="check-result" data-testid="check-registered">
          已登记 {{ lastCheck.核对编号 }}：登记可用窗口
          {{ lastCheck.登记可用窗口.join('、') || '无' }}，未完成
          {{ lastCheck.登记未完成部分.map((w) => `${w.窗口}(${w.状态})`).join('、') || '无' }}。
          可到「补算核对」办理。
        </p>
        <CheckDetailCard v-if="lastCheck" :check="lastCheck" />
      </section>
    </template>

    <p v-else-if="!loading" class="empty-state" data-testid="query-empty">
      请选择实验、指标与时间区间后检索。
    </p>

    <section v-if="showChecks" class="checks-panel">
      <ChecksPanel :exp-code="expCode" :metric-code="activeRound?.指标编码 || metricCode" />
    </section>

    <footer class="page-foot">
      <span>{{ activeRound ? `当前轮次 ${activeRound.查询号}` : '尚未检索' }}</span>
      <span class="muted">{{ noticeMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  createQueryRound,
  loadQueryCatalog,
  loadQueryRound,
  registerCheck,
} from '@/api/backend-service'
import CheckDetailCard from '@/components/CheckDetailCard.vue'
import ChecksPanel from '@/components/ChecksPanel.vue'
import type {
  QueryExperiment,
  QueryMetric,
  QueryRound,
  RecomputeCheck,
} from '@/data/types'

const experiments = ref<QueryExperiment[]>([])
const metrics = ref<QueryMetric[]>([])
const expCode = ref('')
const metricCode = ref('')
const startAt = ref('2026-09-01T10:00')
const endAt = ref('2026-09-01T13:00')
const pageSize = ref(1)
const activeRound = ref<QueryRound | null>(null)
const loading = ref(false)
const paging = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const showChecks = ref(false)
const checkStart = ref('2026-09-01T10:00')
const checkEnd = ref('2026-09-01T13:00')
const lastCheck = ref<RecomputeCheck | null>(null)

function statusClass(status: string): string {
  if (status === '已确认') return 'ok'
  if (status === '未算完') return 'run'
  return 'warn'
}

function shortTime(value: string): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

async function loadMetrics() {
  const catalog = await loadQueryCatalog(expCode.value || undefined)
  metrics.value = catalog.metrics
  if (!metrics.value.some((m) => m.指标编码 === metricCode.value)) {
    metricCode.value = metrics.value[0]?.指标编码 || ''
  }
}

async function onExperimentChange() {
  metricCode.value = ''
  await loadMetrics()
}

async function runQuery() {
  errorMessage.value = ''
  noticeMessage.value = ''
  lastCheck.value = null
  if (!expCode.value || !metricCode.value) {
    errorMessage.value = '请先选择实验与指标'
    return
  }
  loading.value = true
  try {
    const round = await createQueryRound(
      expCode.value,
      metricCode.value,
      startAt.value,
      endAt.value,
      pageSize.value,
    )
    activeRound.value = round
    checkStart.value = shortInput(round.区间开始)
    checkEnd.value = shortInput(round.区间结束)
    noticeMessage.value = `已生成 ${round.查询号}，共 ${round.total} 个窗口`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '查询失败'
  } finally {
    loading.value = false
  }
}

function shortInput(value: string): string {
  return value ? value.slice(0, 16) : ''
}

/** 翻页只取同一轮快照：条件与页码都保留，不重新检索。 */
async function goPage(page: number) {
  if (!activeRound.value) return
  paging.value = true
  errorMessage.value = ''
  try {
    activeRound.value = await loadQueryRound(activeRound.value.round_id, page, activeRound.value.size)
    noticeMessage.value = `同一轮 ${activeRound.value.查询号} 的第 ${activeRound.value.page} 页（快照不变）`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '翻页失败'
  } finally {
    paging.value = false
  }
}

function selectMissingRange() {
  if (!activeRound.value) return
  const missing = activeRound.value.items.filter((row) => row.状态 !== '已确认')
  if (!missing.length) {
    checkStart.value = shortInput(activeRound.value.区间开始)
    checkEnd.value = shortInput(activeRound.value.区间结束)
    return
  }
  checkStart.value = shortInput(missing[0].窗口开始)
  checkEnd.value = shortInput(missing[missing.length - 1].窗口结束)
}

async function submitCheck() {
  if (!activeRound.value) return
  errorMessage.value = ''
  try {
    lastCheck.value = await registerCheck(
      activeRound.value.round_id,
      checkStart.value,
      checkEnd.value,
    )
    noticeMessage.value = `核对 ${lastCheck.value.核对编号} 已登记`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '核对登记失败'
  }
}

onMounted(async () => {
  try {
    const catalog = await loadQueryCatalog()
    experiments.value = catalog.experiments
    expCode.value = catalog.experiments[0]?.实验编码 || ''
    await loadMetrics()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目录加载失败'
  }
})
</script>
