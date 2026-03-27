<template>
  <div class="sources">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>数据源状态</span>
          <el-button @click="refresh" :loading="loading" :icon="Refresh" size="small">刷新</el-button>
        </div>
      </template>

      <el-table :data="sources" v-loading="loading" empty-text="加载中...">
        <el-table-column label="数据源" width="140">
          <template #default="{ row }">
            <div class="source-name">
              <el-icon><component :is="sourceIcon(row.name)" /></el-icon>
              <span>{{ sourceLabel(row.name) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">
              {{ row.status === 'ok' ? '● 正常' : '✗ 异常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="详情" prop="message" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              v-if="row.name === 'wechat'"
              size="small" text
              @click="showWechatHelp = true"
            >配置指南</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 微信配置说明弹窗 -->
    <el-dialog v-model="showWechatHelp" title="微信公众号配置指南" width="600px">
      <el-steps direction="vertical" :active="4">
        <el-step title="安装 Cookie 导出插件"
          description="在 Chrome 中安装 EditThisCookie 或 Get cookies.txt 插件" />
        <el-step title="登录微信公众号平台"
          description="访问 https://mp.weixin.qq.com 并登录" />
        <el-step title="导出 Cookie"
          description="使用插件导出 Cookie，保存为 JSON 格式" />
        <el-step title="保存到配置目录"
          description="将 Cookie 保存至 ~/.researchkit/wechat-auth.json" />
      </el-steps>
      <template #footer>
        <el-button @click="showWechatHelp = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh, Rss, ChatDotRound, Link } from '@element-plus/icons-vue'
import api from '../api'

const sources = ref([])
const loading = ref(false)
const showWechatHelp = ref(false)

const sourceLabel = name => ({ wechat: '微信公众号', rss: 'RSS 订阅', web: '网页抓取' }[name] || name)
const sourceIcon = name => ({ wechat: ChatDotRound, rss: Rss, web: Link }[name])

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/sources')
    sources.value = data
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.sources { padding: 24px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.source-name { display: flex; align-items: center; gap: 8px; }
</style>
