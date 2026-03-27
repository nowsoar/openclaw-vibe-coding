<template>
  <div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
      <el-button @click="$router.back()">← 返回</el-button>
      <h2 style="margin:0;">{{ report?.topic || '加载中...' }}</h2>
    </div>
    <el-card v-if="report" shadow="never">
      <div v-html="renderedContent" class="report-content" />
    </el-card>
    <el-skeleton v-else :rows="12" animated />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import api from '@/api'

const route = useRoute()
const $router = useRouter()
const report = ref(null)

onMounted(async () => {
  try {
    const { data } = await api.get(`/reports/${route.params.id}`)
    report.value = data
  } catch (e) {
    console.error(e)
  }
})

const renderedContent = computed(() => {
  if (!report.value?.content) return ''
  return marked(report.value.content)
})
</script>

<style scoped>
.report-content :deep(h1) { font-size: 1.8em; border-bottom: 2px solid #4a90d9; padding-bottom: 8px; margin: 24px 0 16px; }
.report-content :deep(h2) { font-size: 1.4em; border-bottom: 1px solid #eee; padding-bottom: 6px; margin: 20px 0 12px; }
.report-content :deep(h3) { font-size: 1.1em; margin: 16px 0 8px; }
.report-content :deep(p) { line-height: 1.8; margin-bottom: 12px; }
.report-content :deep(a) { color: #409eff; text-decoration: none; }
.report-content :deep(blockquote) { border-left: 4px solid #409eff; padding: 8px 16px; background: #f0f4ff; margin: 12px 0; }
.report-content :deep(code) { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
.report-content :deep(ul), .report-content :deep(ol) { padding-left: 24px; margin-bottom: 12px; }
.report-content :deep(li) { line-height: 1.8; }
</style>
