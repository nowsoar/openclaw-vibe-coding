<template>
  <div>
    <h2 style="margin-bottom:16px;">调研报告</h2>
    <el-card shadow="never">
      <el-table :data="reports" v-loading="loading" style="width:100%">
        <el-table-column prop="task_id" label="任务ID" width="80" />
        <el-table-column prop="task_name" label="任务名称" />
        <el-table-column prop="topic" label="主题" />
        <el-table-column prop="article_count" label="参考文章" width="90" />
        <el-table-column prop="created_at" label="生成时间" width="160">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="$router.push(`/reports/${row.task_id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'

const $router = useRouter()
const reports = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await api.get('/reports')
    reports.value = data
  } catch {} finally { loading.value = false }
})

function fmtDate(d) { return d ? new Date(d).toLocaleString('zh-CN') : '-' }
</script>
