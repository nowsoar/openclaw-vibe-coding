<template>
  <div class="task-progress">
    <el-card shadow="never" v-if="task">
      <template #header>
        <div class="card-header">
          <div>
            <el-text size="large" tag="b">{{ task.name }}</el-text>
            <el-tag :type="statusType" class="status-tag">{{ statusLabel }}</el-tag>
          </div>
          <el-button v-if="task.status === 'done'" type="success"
            @click="$router.push(`/tasks/${taskId}/report`)">
            查看报告
          </el-button>
        </div>
      </template>

      <!-- 进度条 -->
      <div class="progress-section">
        <div v-for="stage in stages" :key="stage.key" class="stage">
          <div class="stage-header">
            <span class="stage-name">{{ stage.label }}</span>
            <el-tag size="small" :type="stage.tagType">{{ stage.status }}</el-tag>
          </div>
          <el-progress
            :percentage="stage.pct"
            :status="stage.progressStatus"
            :striped="stage.key === currentStage"
            :striped-flow="stage.key === currentStage"
            :duration="4"
          />
          <div class="stage-msg" v-if="stage.message">{{ stage.message }}</div>
        </div>
      </div>

      <!-- 日志流 -->
      <el-divider>运行日志</el-divider>
      <div class="log-container" ref="logContainer">
        <div v-for="(log, i) in logs" :key="i" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span :class="`log-${log.type}`">{{ log.text }}</span>
        </div>
        <div v-if="task.status === 'running'" class="log-line blinking">▌</div>
      </div>

      <!-- 错误信息 -->
      <el-alert v-if="task.status === 'failed'" :title="task.error" type="error" class="error-alert" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTaskStore } from '../stores/tasks'
import api from '../api'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()
const taskId = route.params.id

const task = ref(null)
const logs = ref([])
const currentStage = ref('fetch')
const logContainer = ref(null)

const stageData = ref({
  fetch: { pct: 0, message: '', done: false },
  process: { pct: 0, message: '', done: false },
  output: { pct: 0, message: '', done: false },
})

const stages = computed(() => [
  { key: 'fetch', label: '数据抓取', ...stageInfo('fetch') },
  { key: 'process', label: '内容处理', ...stageInfo('process') },
  { key: 'output', label: '生成报告', ...stageInfo('output') },
])

function stageInfo(key) {
  const d = stageData.value[key]
  const isDone = d.done
  const isCurrent = currentStage.value === key && !isDone
  return {
    pct: d.pct,
    message: d.message,
    tagType: isDone ? 'success' : isCurrent ? 'warning' : 'info',
    status: isDone ? '完成' : isCurrent ? '进行中' : '等待中',
    progressStatus: isDone ? 'success' : null,
  }
}

const statusType = computed(() => ({
  pending: 'info', running: 'warning', done: 'success', failed: 'danger'
})[task.value?.status] || 'info')

const statusLabel = computed(() => ({
  pending: '待运行', running: '运行中', done: '已完成', failed: '失败'
})[task.value?.status] || '')

function addLog(type, text) {
  const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  logs.value.push({ time: now, type, text })
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

let ws = null

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/tasks/${taskId}`)

  ws.onmessage = ({ data }) => {
    const event = JSON.parse(data)
    if (event.type === 'ping') return

    if (event.type === 'progress') {
      const { stage, current, total, message } = event
      const pct = total > 0 ? Math.round(current / total * 100) : 0
      currentStage.value = stage
      if (stageData.value[stage]) {
        stageData.value[stage].pct = pct
        stageData.value[stage].message = message
      }
      addLog('info', `[${stage}] ${message}`)
    }

    if (event.type === 'done') {
      Object.keys(stageData.value).forEach(k => {
        stageData.value[k].pct = 100
        stageData.value[k].done = true
      })
      taskStore.updateTaskLocally(taskId, {
        status: 'done', report_path: event.report_path, article_count: event.article_count
      })
      if (task.value) {
        task.value.status = 'done'
        task.value.report_path = event.report_path
        task.value.article_count = event.article_count
      }
      addLog('success', `✓ 调研完成，共 ${event.article_count} 篇文章`)
    }

    if (event.type === 'error') {
      taskStore.updateTaskLocally(taskId, { status: 'failed', error: event.message })
      if (task.value) { task.value.status = 'failed'; task.value.error = event.message }
      addLog('error', `✗ 错误: ${event.message}`)
    }
  }

  ws.onerror = () => addLog('error', 'WebSocket 连接错误，请刷新页面')
  ws.onclose = () => addLog('info', '连接已关闭')
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/tasks/${taskId}`)
    task.value = data
    if (data.status === 'running') {
      connectWS()
      addLog('info', '已连接，等待进度更新...')
    } else if (data.status === 'done') {
      Object.keys(stageData.value).forEach(k => {
        stageData.value[k].pct = 100; stageData.value[k].done = true
      })
    }
  } catch {
    addLog('error', '获取任务信息失败')
  }
})

onUnmounted(() => { if (ws) ws.close() })
</script>

<style scoped>
.task-progress { padding: 24px; max-width: 900px; margin: 0 auto; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.status-tag { margin-left: 12px; }
.progress-section { display: flex; flex-direction: column; gap: 20px; padding: 16px 0; }
.stage-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.stage-name { font-weight: 600; color: #333; }
.stage-msg { font-size: 12px; color: #999; margin-top: 4px; }
.log-container {
  background: #1a1a2e; color: #cdd6f4; font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px; border-radius: 8px; padding: 12px 16px;
  height: 240px; overflow-y: auto; line-height: 1.6;
}
.log-line { display: flex; gap: 12px; }
.log-time { color: #6c7086; flex-shrink: 0; }
.log-info { color: #cdd6f4; }
.log-success { color: #a6e3a1; }
.log-error { color: #f38ba8; }
.blinking { animation: blink 1s step-start infinite; }
@keyframes blink { 50% { opacity: 0; } }
.error-alert { margin-top: 16px; }
</style>
