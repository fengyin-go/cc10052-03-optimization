<template>
  <div class="module-tabs">
    <nav class="tab-bar" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        :data-testid="`tab-${tab.key}`"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.key"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <MetricQueryView v-if="activeTab === 'query'" />
    <WorkbenchView v-else module-key="metric_api" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import MetricQueryView from '@/views/MetricQueryView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const activeTab = ref<'query' | 'interfaces'>('query')
const tabs = [
  { key: 'query', label: '指标窗口查询' },
  { key: 'interfaces', label: '查询接口清单' },
] as const
</script>
