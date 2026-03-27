<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h2>任务列表</h2>
      <el-button type="primary" @click="$router.push('/new')">新建调研</el-button>
    </div>
    <el-card shadow="never">
      <el-table :data="store.tasks" v-loading="loading" style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="任务名称" />
        <el-table-column prop="topic" label="主题" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="article_count" label="文章数" width="80" />
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/tasks/${row.id}/progress`)">进度</el-button>
            <el-button v-if="row.status === 'done'" size="small" type="success"
              @click="$router.push(`/reports/${row.id}`)">报告</el-button>
            <el-popconfirm title="确定删除此任务?" @confirm="remove(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const store = useTaskStore()
const $router = useRouter()
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  await store.fetchAll()
  loading.value = false
})

async function remove(id) {
  try {
    await store.remove(id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function statusType(s) {
  return { pending: 'info', running: 'warning', done: 'success', failed: 'danger' }[s] || 'info'
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleString('zh-CN') : '-'
}
</script>
