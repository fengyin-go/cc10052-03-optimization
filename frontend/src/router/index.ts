import { createRouter, createWebHistory } from 'vue-router'

import MetricApiView from '@/views/MetricApiView.vue'
import MetricComputeView from '@/views/MetricComputeView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 指标查询服务与指标计算作业走专用工作台，其余模块仍用通用工作台。
    { path: '/metric_api', name: 'metric_api', component: MetricApiView },
    { path: '/metric_compute', name: 'metric_compute', component: MetricComputeView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
