import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { title: '仪表盘' }
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录', layout: 'blank' }
  },
  {
    path: '/tasks/new',
    name: 'new-task',
    component: () => import('../views/NewTask.vue'),
    meta: { title: '新建调研任务' }
  },
  {
    path: '/tasks/:id/progress',
    name: 'task-progress',
    component: () => import('../views/TaskProgress.vue'),
    meta: { title: '任务进度' }
  },
  {
    path: '/tasks/:id/report',
    name: 'report-view',
    component: () => import('../views/ReportView.vue'),
    meta: { title: '查看报告' }
  },
  {
    path: '/sources',
    name: 'sources',
    component: () => import('../views/Sources.vue'),
    meta: { title: '数据源管理' }
  },
  {
    path: '/templates',
    name: 'templates',
    component: () => import('../views/Templates.vue'),
    meta: { title: '报告模板' }
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/Settings.vue'),
    meta: { title: '系统设置' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
