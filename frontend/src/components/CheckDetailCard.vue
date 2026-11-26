<template>
  <article class="check-detail" data-testid="check-detail">
    <header class="check-detail-head">
      <div>
        <strong>{{ check.核对编号 }}</strong>
        <span class="badge" :class="check.是否冲突 ? 'badge-warn' : 'badge-ok'">
          {{ check.状态 }}
        </span>
        <span v-if="check.是否冲突" class="badge badge-warn">版本冲突</span>
      </div>
      <span class="muted">{{ check.说明 }}</span>
    </header>

    <dl class="check-meta">
      <div><dt>实验</dt><dd>{{ check.实验编码 }}</dd></div>
      <div><dt>指标</dt><dd>{{ check.指标编码 }}</dd></div>
      <div><dt>区间</dt><dd>{{ shortTime(check.区间开始) }} ~ {{ shortTime(check.区间结束) }}</dd></div>
      <div><dt>来源查询</dt><dd>{{ check.来源查询号 }}</dd></div>
      <div><dt>登记基线</dt><dd>{{ check.版本基线 }}</dd></div>
      <div><dt>领取时间</dt><dd>{{ check.领取时间 || '未领取' }}</dd></div>
    </dl>

    <section v-if="check.状态 === '已办理'" class="check-block">
      <h5>实际采用的窗口（{{ check.采用窗口.length }}）</h5>
      <table class="mini-table" data-testid="check-adopted">
        <thead>
          <tr><th>窗口</th><th>调度窗口</th><th>版本</th><th>指标值</th><th>作业轮次</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in check.采用窗口" :key="item.窗口">
            <td>{{ item.窗口 }}</td>
            <td class="mono">{{ item.调度窗口 }}</td>
            <td>{{ item.版本 }}</td>
            <td>{{ item.指标值 ?? '—' }}</td>
            <td class="mono">{{ item.作业轮次 }}</td>
          </tr>
          <tr v-if="!check.采用窗口.length">
            <td colspan="5" class="empty-state">没有可采用的确认结果</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="check.状态 === '已办理'" class="check-block">
      <h5>尚未完成的部分（{{ check.未完成部分.length }}）</h5>
      <table class="mini-table" data-testid="check-unfinished">
        <thead>
          <tr><th>窗口</th><th>调度窗口</th><th>当前状态</th><th>原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in check.未完成部分" :key="item.窗口">
            <td>{{ item.窗口 }}</td>
            <td class="mono">{{ item.调度窗口 }}</td>
            <td>{{ item.状态 }}</td>
            <td>{{ item.原因 || '—' }}</td>
          </tr>
          <tr v-if="!check.未完成部分.length">
            <td colspan="4" class="empty-state">全部窗口均已采用</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="check.逐窗口.length" class="check-block">
      <h5>逐窗口核对（载明每个窗口是否实际采用）</h5>
      <table class="mini-table" data-testid="check-windows">
        <thead>
          <tr>
            <th>窗口</th><th>调度窗口</th><th>登记状态</th><th>领取时状态</th><th>是否采用</th><th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in check.逐窗口" :key="item.窗口" :data-adopted="item.是否采用">
            <td>{{ item.窗口 }}</td>
            <td class="mono">{{ item.调度窗口 }}</td>
            <td>{{ item.登记状态 }}</td>
            <td>{{ item.当前状态 || '—' }}</td>
            <td>{{ item.是否采用 ? '已采用' : '未采用' }}</td>
            <td>{{ item.原因 || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-else class="check-block">
      <h5>登记时快照</h5>
      <p class="muted">
        可用窗口：{{ check.登记可用窗口.join('、') || '无' }}；
        未完成：{{ check.登记未完成部分.map((w) => `${w.窗口}(${w.状态})`).join('、') || '无' }}
      </p>
      <p class="muted">该核对尚未领取，采用结果需办理后登记。</p>
    </section>
  </article>
</template>

<script setup lang="ts">
import type { RecomputeCheck } from '@/data/types'

defineProps<{ check: RecomputeCheck }>()

function shortTime(value: string): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}
</script>
