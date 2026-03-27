<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-cards">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value" :style="{ color: stat.color }">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近任务 -->
    <el-card shadow="never" class="tasks-card">
      <template #header>
        <div class="card-header">
          <span>最近调研任务</span>
          <el-button type="primary" size="small" @click="$router.push('/tasks/new')">
            <el-icon><Plus /></el-icon>新建调研
          </el-button>
        </div>
      </template>

      <el-table :data="taskStore.tasks" v-loading="taskStore.loading" empty-text="暂无任务">
        <el-table-column label="任务名称" prop="name" min-width="180" />
        <el-table-column label="研究主题" prop="topic" min-width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文章数" prop="article_count" width="80" align="center" />
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              type="primary" size="small" text
              @click="handleRun(row)"
            >运行</el-button>
            <el-button
              v-if="row.status === 'running'"
              type="warning" size="small" text
              @click="$router.push(`/tasks/${row.id}/progress`)"
            >查看进度</el-button>
            <el-button
              v-if="row.status === 'done'"
              type="success" size="small" text
              @click="$router.push(`/tasks/${row.id}/report`)"
            >查看报告</el-button>
            <el-button type="danger" size="small" text @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '../stores/tasks'

const taskStore = useTaskStore()

onMounted(() => taskStore.fetchTasks())

const stats = computed(() => [
  { label: '全部任务', value: taskStore.tasks.length, color: '#409eff' },
  { label: '运行中', value: taskStore.runningTasks.length, color: '#e6a23c' },
  { label: '已完成', value: taskStore.doneTasks.length, color: '#67c23a' },
  { label: '失败', value: taskStore.failedTasks.length, color: '#f56c6c' },
])

const statusType = s => ({ pending: 'info', running: 'warning', done: 'success', failed: 'danger' }[s] || 'info')
const statusLabel = s => ({ pending: '待运行', running: '运行中', done: '已完成', failed: '失败' }[s] || s)

const formatDate = iso => {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false }).slice(0, 16)
}

async function handleRun(task) {
  try {
    await taskStore.runTask(task.id)
    ElMessage.success('任务已启动')
  } catch {
    ElMessage.error('启动失败')
  }
}

async function handleDelete(task) {
  await ElMessageBox.confirm(`确认删除任务「${task.name}」？`, '删除确认', { type: 'warning' })
  await taskStore.deleteTask(task.id)
  ElMessage.success('已删除')
}
</script>

<style scoped>
.dashboard { padding: 24px; }
.stat-cards { margin-bottom: 20px; }
.stat-card { text-align: center; }
.stat-value { font-size: 32px; font-weight: 700; line-height: 1; margin-bottom: 8px; }
.stat-label { color: #666; font-size: 14px; }
.tasks-card { background: #fff; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
