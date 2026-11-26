<template>
  <section class="checks-panel-inner" data-testid="checks-panel">
    <header class="checks-head">
      <h4>补算核对办理</h4>
      <div class="page-actions">
        <select v-model="statusFilter" data-testid="check-status-filter" @change="reload">
          <option value="">全部状态</option>
          <option value="待领取">待领取</option>
          <option value="已办理">已办理</option>
        </select>
        <button class="btn" data-testid="refresh-checks" type="button" @click="reload">刷新</button>
      </div>
    </header>

    <p class="muted" data-testid="checks-scope">
      范围：{{ expCode || '全部实验' }} / {{ metricCode || '全部指标' }}
    </p>
    <p v-if="errorMessage" class="error-text" data-testid="checks-error">{{ errorMessage }}</p>

    <table class="data-table" data-testid="checks-table">
      <thead>
        <tr>
          <th>核对编号</th>
          <th>实验/指标</th>
          <th>区间</th>
          <th>来源查询</th>
          <th>状态</th>
          <th>登记摘要</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in checks"
          :key="item.id"
          :data-testid="`check-row-${item.核对编号}`"
          :data-status="item.状态"
        >
          <td>{{ item.核对编号 }}</td>
          <td>{{ item.实验编码 }} / {{ item.指标编码 }}</td>
          <td>{{ shortTime(item.区间开始) }} ~ {{ shortTime(item.区间结束) }}</td>
          <td>{{ item.来源查询号 }}</td>
          <td>
            <span class="tag" :class="item.是否冲突 ? 'tag-warn' : item.状态 === '已办理' ? 'tag-ok' : 'tag-run'">
              {{ item.状态 }}
            </span>
            <span v-if="item.是否冲突" class="tag tag-warn">冲突</span>
          </td>
          <td>
            可用 {{ item.登记可用窗口.length }} · 未完成
            {{ item.登记未完成部分.length }}
          </td>
          <td class="row-actions">
            <button
              class="link"
              :data-testid="`view-check-${item.核对编号}`"
              type="button"
              @click="openDetail(item.id)"
            >
              详情
            </button>
            <button
              v-if="item.状态 === '待领取'"
              class="link"
              :data-testid="`claim-check-${item.核对编号}`"
              type="button"
              @click="claim(item)"
            >
              领取并办理
            </button>
          </td>
        </tr>
        <tr v-if="!checks.length">
          <td colspan="7" class="empty-state">暂无补算核对</td>
        </tr>
      </tbody>
    </table>

    <p class="muted" data-testid="checks-total">共 {{ total }} 条补算核对</p>

    <section v-if="detail" class="check-detail-wrap">
      <CheckDetailCard :check="detail" />
      <div v-if="detail.状态 === '待领取'" class="page-actions">
        <button
          class="btn primary"
          :data-testid="`claim-detail-${detail.核对编号}`"
          type="button"
          @click="claim(detail)"
        >
          领取并办理
        </button>
      </div>
      <section v-if="relatedJobs.length" class="check-block">
        <h5>关联补算作业（采用窗口的作业轮次与调度窗口）</h5>
        <table class="mini-table" data-testid="check-jobs">
          <thead>
            <tr><th>补算编码</th><th>窗口</th><th>调度窗口</th><th>作业轮次</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="job in relatedJobs" :key="job.id">
              <td>{{ job.补算编码 }}</td>
              <td>{{ job.窗口 }}</td>
              <td class="mono">{{ job.调度窗口 }}</td>
              <td class="mono">{{ job.作业轮次 }}</td>
              <td>{{ job.状态 }}</td>
              <td>
                <button
                  v-if="job.状态 === '执行中'"
                  class="link"
                  :data-testid="`complete-job-${job.补算编码}`"
                  type="button"
                  @click="completeJob(job)"
                >
                  模拟补算完成
                </button>
                <span v-else class="muted">{{ job.结果版本 || '—' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import {
  claimCheck,
  completeRecomputeJob,
  listChecks,
  loadCheck,
} from '@/api/backend-service'
import CheckDetailCard from '@/components/CheckDetailCard.vue'
import type { RecomputeCheck, RecomputeJob } from '@/data/types'

const props = defineProps<{ expCode?: string; metricCode?: string }>()

const checks = ref<RecomputeCheck[]>([])
const total = ref(0)
const statusFilter = ref('')
const errorMessage = ref('')
const detail = ref<RecomputeCheck | null>(null)
const relatedJobs = ref<RecomputeJob[]>([])

function shortTime(value: string): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listChecks({
      expCode: props.expCode || undefined,
      metricCode: props.metricCode || undefined,
      status: statusFilter.value || undefined,
    })
    checks.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '核对列表读取失败'
  }
}

async function openDetail(checkId: number) {
  errorMessage.value = ''
  try {
    const payload = await loadCheck(checkId)
    detail.value = payload.check
    relatedJobs.value = payload.jobs
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '核对详情读取失败'
  }
}

async function claim(item: RecomputeCheck) {
  errorMessage.value = ''
  try {
    await claimCheck(item.id)
    await openDetail(item.id)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '核对办理失败'
  }
}

async function completeJob(job: RecomputeJob) {
  errorMessage.value = ''
  try {
    await completeRecomputeJob(job.id)
    if (detail.value) await openDetail(detail.value.id)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '补算完成失败'
  }
}

watch(() => [props.expCode, props.metricCode], () => void reload())
onMounted(reload)
</script>
