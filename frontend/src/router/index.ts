import { createRouter, createWebHistory } from 'vue-router'

import StrategyCenterView from '@/views/StrategyCenterView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'workbench', component: WorkbenchView },
    { path: '/strategies', name: 'strategies', component: StrategyCenterView },
  ],
})

export default router
