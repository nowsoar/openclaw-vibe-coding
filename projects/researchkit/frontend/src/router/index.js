import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import NewTask from '@/views/NewTask.vue'
import TaskList from '@/views/TaskList.vue'
import TaskProgress from '@/views/TaskProgress.vue'
import Reports from '@/views/Reports.vue'
import ReportView from '@/views/ReportView.vue'
import Sources from '@/views/Sources.vue'
import Login from '@/views/Login.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login, meta: { public: true } },
    { path: '/', component: Dashboard },
    { path: '/new', component: NewTask },
    { path: '/tasks', component: TaskList },
    { path: '/tasks/:id/progress', component: TaskProgress },
    { path: '/reports', component: Reports },
    { path: '/reports/:id', component: ReportView },
    { path: '/sources', component: Sources },
  ]
})

// 可选：如果需要强制登录，取消注释下方代码
// router.beforeEach((to) => {
//   const { useAuthStore } = require('@/stores/auth')
//   const auth = useAuthStore()
//   if (!to.meta.public && !auth.isLoggedIn) return '/login'
// })

export default router

