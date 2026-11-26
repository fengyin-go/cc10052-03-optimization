<template>
  <div class="module-tabs">
    <nav class="tab-bar" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        :data-testid="`compute-tab-${tab.key}`"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.key"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <section v-if="activeTab === 'identity'" class="page" data-testid="metric-compute-view">
      <header class="page-head">
        <div>
          <h2>指标计算作业</h2>
          <p class="page-desc">
            为查询接口提供指标窗口结果对应的作业轮次与调度窗口身份；可继续办理由所选区间登记的补算核对，
            并查看它实际采用的窗口。
          </p>
        </div>
      </header>

      <form class="filter-bar query-form" data-testid="compute-form" @submit.prevent="load">
        <label class="filter-item">
          <span>实验</span>
          <select v-model="expCode" data-testid="compute-experiment" @change="onExperimentChange">
            <option v-for="item in experiments" :key="item.实验编码" :value="item.实验编码">
              {{ item.实验编码 }} · {{ item.实验名称 }}
            </option>
          </select>
        </label>
        <label class="filter-item">
          <span>指标</span>
          <select v-model="metricCode" data-testid="compute-metric" @change="load">
            <option v-for="item in metrics" :key="item.指标编码" :value="item.指标编码">
              {{ item.指标编码 }} · {{ item.指标名称 }}
            </option>
          </select>
        </label>
        <button class="btn" data-testid="compute-reload" type="submit">刷新</button>
      </form>

      <p v-if="errorMessage" class="error-text" data-testid="compute-error">{{ errorMessage }}</p>

      <h4>指标窗口结果身份</h4>
      <table class="data-table" data-testid="window-identity-table">
        <thead>
          <tr><th>窗口</th><th>指标值</th><th>结果版本</th><th>作业轮次</th><th>调度窗口</th><th>作业</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in identities" :key="row.窗口开始" :data-testid="`identity-${row.窗口}`">
            <td>{{ row.窗口 }}</td>
            <td>{{ row.指标值 ?? '—' }}</td>
            <td>{{ row.结果版本 }}</td>
            <td class="mono">{{ row.作业轮次 }}</td>
            <td class="mono">{{ row.调度窗口 }}</td>
            <td>{{ row.作业名称 }}</td>
          </tr>
          <tr v-if="!identities.length">
            <td colspan="6" class="empty-state">该实验/指标暂无已确认窗口结果</td>
          </tr>
        </tbody>
      </table>

      <h4 class="section-gap">由所选区间登记的补算核对</h4>
      <ChecksPanel :exp-code="expCode" :metric-code="metricCode" />
    </section>

    <WorkbenchView v-else module-key="metric_compute" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  loadQueryCatalog,
  loadWindowIdentity,
  type WindowIdentity,
} from '@/api/backend-service'
import ChecksPanel from '@/components/ChecksPanel.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import type { QueryExperiment, QueryMetric } from '@/data/types'

const activeTab = ref<'identity' | 'jobs'>('identity')
const tabs = [
  { key: 'identity', label: '窗口结果与补算核对' },
  { key: 'jobs', label: '计算作业清单' },
] as const

const experiments = ref<QueryExperiment[]>([])
const metrics = ref<QueryMetric[]>([])
const expCode = ref('')
const metricCode = ref('')
const identities = ref<WindowIdentity[]>([])
const errorMessage = ref('')

async function load() {
  errorMessage.value = ''
  if (!expCode.value) return
  try {
    const catalog = await loadQueryCatalog(expCode.value)
    metrics.value = catalog.metrics
    if (!metrics.value.some((m) => m.指标编码 === metricCode.value)) {
      metricCode.value = metrics.value[0]?.指标编码 || ''
    }
    if (metricCode.value) {
      identities.value = await loadWindowIdentity(expCode.value, metricCode.value)
    } else {
      identities.value = []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业窗口身份读取失败'
  }
}

async function onExperimentChange() {
  metricCode.value = ''
  await load()
}

onMounted(async () => {
  try {
    const catalog = await loadQueryCatalog()
    experiments.value = catalog.experiments
    expCode.value = catalog.experiments[0]?.实验编码 || ''
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目录加载失败'
  }
})
</script>
