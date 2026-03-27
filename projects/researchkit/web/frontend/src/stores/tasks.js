import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref([])
  const loading = ref(false)
  const error = ref(null)

  const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending'))
  const runningTasks = computed(() => tasks.value.filter(t => t.status === 'running'))
  const doneTasks = computed(() => tasks.value.filter(t => t.status === 'done'))
  const failedTasks = computed(() => tasks.value.filter(t => t.status === 'failed'))

  async function fetchTasks() {
    loading.value = true
    try {
      const { data } = await api.get('/tasks')
      tasks.value = data
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function createTask(body) {
    const { data } = await api.post('/tasks', body)
    tasks.value.unshift(data)
    return data
  }

  async function runTask(taskId) {
    const { data } = await api.post(`/tasks/${taskId}/run`)
    const idx = tasks.value.findIndex(t => t.id === taskId)
    if (idx !== -1) tasks.value[idx] = data
    return data
  }

  async function deleteTask(taskId) {
    await api.delete(`/tasks/${taskId}`)
    tasks.value = tasks.value.filter(t => t.id !== taskId)
  }

  function updateTaskLocally(taskId, updates) {
    const idx = tasks.value.findIndex(t => t.id === taskId)
    if (idx !== -1) Object.assign(tasks.value[idx], updates)
  }

  return {
    tasks, loading, error,
    pendingTasks, runningTasks, doneTasks, failedTasks,
    fetchTasks, createTask, runTask, deleteTask, updateTaskLocally
  }
})
