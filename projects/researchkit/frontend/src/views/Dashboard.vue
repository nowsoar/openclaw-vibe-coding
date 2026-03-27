<template>
  <div>
    <h2 style="margin-bottom:20px;">仪表板</h2>
    <el-row :gutter="20" style="margin-bottom:24px;">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="never">
          <div style="font-size:13px;color:#999;">{{ stat.label }}</div>
          <div style="font-size:32px;font-weight:700;color:#409eff;margin-top:8px;">{{ stat.value }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" header="最近调研任务">
      <el-table :data="recentTasks" :loading="loading" style="width:100%">
        <el-table-column prop="name" label="任务名称" />
        <el-table-column prop="topic" label="主题" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="article_count" label="文章数" width="80" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/tasks/${row.id}/progress`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:12px;text-align:right;">
        <el-button type="primary" @click="$router.push('/new')">新建调研</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useRouter } from 'vue-router'

const store = useTaskStore()
const $router = useRouter()
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  await store.fetchAll()
  loading.value = false
})

const recentTasks = computed(() => store.tasks.slice(0, 10))

const stats = computed(() => [
  { label: '全部任务', value: store.tasks.length },
  { label: '运行中', value: store.tasks.filter(t => t.status === 'running').length },
  { label: '已完成', value: store.tasks.filter(t => t.status === 'done').length },
  { label: '失败', value: store.tasks.filter(t => t.status === 'failed').length },
])

function statusType(s) {
  return { pending: 'info', running: 'warning', done: 'success', failed: 'danger' }[s] || 'info'
}
</script>
