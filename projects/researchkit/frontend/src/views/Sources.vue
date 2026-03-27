<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h2>数据源管理</h2>
      <el-button :loading="loading" @click="refresh">刷新状态</el-button>
    </div>
    <el-row :gutter="16">
      <el-col :span="12" v-for="src in sources" :key="src.name" style="margin-bottom:16px;">
        <el-card shadow="never">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-size:16px;font-weight:600;text-transform:capitalize;">{{ src.name }}</div>
              <div style="font-size:13px;color:#666;margin-top:4px;">{{ src.message }}</div>
            </div>
            <el-tag :type="statusType(src.status)" size="large">{{ src.status }}</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-divider />
    <h3 style="margin-bottom:12px;">报告模板</h3>
    <el-table :data="templates" style="width:100%">
      <el-table-column prop="id" label="ID" width="180" />
      <el-table-column prop="name" label="模板名称" />
      <el-table-column prop="description" label="描述" />
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'

const sources = ref([])
const templates = ref([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const [srcRes, tplRes] = await Promise.all([
      api.get('/sources'),
      api.get('/sources/templates'),
    ])
    sources.value = srcRes.data
    templates.value = tplRes.data
  } catch {} finally { loading.value = false }
}

onMounted(refresh)

function statusType(s) {
  return { ok: 'success', warn: 'warning', error: 'danger' }[s] || 'info'
}
</script>
