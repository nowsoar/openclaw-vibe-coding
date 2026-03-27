<template>
  <div>
    <h2 style="margin-bottom:16px;">任务进度</h2>
    <el-card v-if="task" shadow="never" style="margin-bottom:16px;">
      <el-descriptions :column="3" border>
        <el-descriptions-item label="任务名称">{{ task.name }}</el-descriptions-item>
        <el-descriptions-item label="主题">{{ task.topic }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusType(task.status)">{{ task.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="文章数">{{ task.article_count }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ fmtDate(task.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" header="实时进度" style="margin-bottom:16px;">
      <div v-for="(log, i) in logs" :key="i" style="font-family:monospace;font-size:13px;padding:2px 0;">
        <el-tag size="small" :type="log.type === 'error' ? 'danger' : 'info'" style="margin-right:8px;">
          {{ log.stage || log.type }}
        </el-tag>
        {{ log.message }}
      </div>
      <div v-if="logs.length === 0" style="color:#999;">等待任务启动...</div>
    </el-card>

    <el-card v-if="task?.status === 'done'" shadow="never">
      <el-result icon="success" title="调研完成！">
        <template #extra>
          <el-button type="primary" @click="$router.push(`/reports/${task.id}`)">查看报告</el-button>
          <el-button @click="$router.push('/tasks')">返回列表</el-button>
        </template>
      </el-result>
    </el-card>
    <el-card v-if="task?.status === 'failed'" shadow="never">
      <el-result icon="error" :title="task.error || '任务失败'">
        <template #extra>
          <el-button @click="$router.push('/tasks')">返回列表</el-button>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/tasks'

const route = useRoute()
const $router = useRouter()
const store = useTaskStore()
const task = ref(null)
const logs = ref([])
let ws = null

onMounted(async () => {
  const taskId = Number(route.params.id)
  task.value = await store.getOne(taskId)

  // WebSocket 实时进度
  const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/tasks/${taskId}`
  ws = new WebSocket(wsUrl)
  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data)
      logs.value.push(event)
      if (event.type === 'done' || event.type === 'error') {
        store.fetchAll()
        store.getOne(taskId).then(t => task.value = t)
      }
    } catch {}
  }
  // ping 保活
  const pingInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send('ping')
  }, 25000)
  ws._pingInterval = pingInterval
})

onUnmounted(() => {
  if (ws) {
    clearInterval(ws._pingInterval)
    ws.close()
  }
})

function statusType(s) {
  return { pending: 'info', running: 'warning', done: 'success', failed: 'danger' }[s] || 'info'
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleString('zh-CN') : '-'
}
</script>
