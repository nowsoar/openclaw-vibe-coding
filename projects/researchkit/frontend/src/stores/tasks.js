import { defineStore } from 'pinia'
import api from '@/api'

export const useTaskStore = defineStore('tasks', {
  state: () => ({
    tasks: [],
    loading: false,
    error: null,
  }),
  actions: {
    async fetchAll() {
      this.loading = true
      try {
        const { data } = await api.get('/tasks')
        this.tasks = data
      } catch (e) {
        this.error = e.message
      } finally {
        this.loading = false
      }
    },
    async create(payload) {
      const { data } = await api.post('/tasks', payload)
      this.tasks.unshift(data)
      return data
    },
    async run(taskId) {
      const { data } = await api.post(`/tasks/${taskId}/run`)
      const idx = this.tasks.findIndex(t => t.id === taskId)
      if (idx !== -1) this.tasks[idx] = data
      return data
    },
    async remove(taskId) {
      await api.delete(`/tasks/${taskId}`)
      this.tasks = this.tasks.filter(t => t.id !== taskId)
    },
    async getOne(taskId) {
      const { data } = await api.get(`/tasks/${taskId}`)
      return data
    },
  }
})
