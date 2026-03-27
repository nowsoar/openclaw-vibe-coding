import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import NewTask from '@/views/NewTask.vue'
import TaskList from '@/views/TaskList.vue'
import TaskProgress from '@/views/TaskProgress.vue'
import Reports from '@/views/Reports.vue'
import ReportView from '@/views/ReportView.vue'
import Sources from '@/views/Sources.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/new', component: NewTask },
    { path: '/tasks', component: TaskList },
    { path: '/tasks/:id/progress', component: TaskProgress },
    { path: '/reports', component: Reports },
    { path: '/reports/:id', component: ReportView },
    { path: '/sources', component: Sources },
  ]
})
