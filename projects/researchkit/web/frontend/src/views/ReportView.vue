<template>
  <div class="report-view">
    <el-row :gutter="20">
      <!-- 报告内容 -->
      <el-col :span="18">
        <el-card shadow="never" v-loading="loading">
          <template #header>
            <div class="report-header">
              <span>{{ taskName }}</span>
              <div class="report-actions">
                <el-button size="small" @click="copyContent" :icon="CopyDocument">复制</el-button>
                <el-button size="small" @click="downloadMd" :icon="Download">下载 MD</el-button>
              </div>
            </div>
          </template>
          <div class="markdown-body" v-html="renderedContent" />
        </el-card>
      </el-col>

      <!-- 目录导航 -->
      <el-col :span="6">
        <el-card shadow="never" class="toc-card">
          <template #header>目录</template>
          <ul class="toc-list">
            <li v-for="h in headings" :key="h.id"
                :class="`toc-${h.level}`"
                @click="scrollTo(h.id)">
              {{ h.text }}
            </li>
          </ul>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CopyDocument, Download } from '@element-plus/icons-vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import api from '../api'

const route = useRoute()
const taskId = route.params.id

const loading = ref(true)
const rawContent = ref('')
const taskName = ref('调研报告')
const headings = ref([])

marked.setOptions({
  highlight: (code, lang) => {
    const valid = hljs.getLanguage(lang)
    return valid ? hljs.highlight(code, { language: lang }).value : hljs.highlightAuto(code).value
  }
})

const renderedContent = computed(() => marked.parse(rawContent.value))

function extractHeadings(md) {
  const result = []
  let idx = 0
  for (const line of md.split('\n')) {
    const m = line.match(/^(#{1,3})\s+(.+)/)
    if (m) {
      const id = `h-${idx++}`
      result.push({ level: m[1].length, text: m[2], id })
    }
  }
  return result
}

function scrollTo(id) {
  nextTick(() => {
    const hs = document.querySelectorAll('.markdown-body h1, .markdown-body h2, .markdown-body h3')
    const target = Array.from(hs).find((_, i) => `h-${i}` === id)
    if (target) target.scrollIntoView({ behavior: 'smooth' })
  })
}

async function copyContent() {
  await navigator.clipboard.writeText(rawContent.value)
  ElMessage.success('已复制到剪贴板')
}

function downloadMd() {
  const blob = new Blob([rawContent.value], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${taskName.value}.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  try {
    const [taskRes, reportRes] = await Promise.all([
      api.get(`/tasks/${taskId}`),
      api.get(`/tasks/${taskId}/report`),
    ])
    taskName.value = taskRes.data.name
    rawContent.value = reportRes.data.content
    headings.value = extractHeadings(rawContent.value)
  } catch (e) {
    ElMessage.error('加载报告失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.report-view { padding: 24px; }
.report-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.report-actions { display: flex; gap: 8px; }
.toc-card { position: sticky; top: 20px; }
.toc-list { list-style: none; padding: 0; }
.toc-list li { padding: 4px 0; cursor: pointer; color: #555; font-size: 13px; line-height: 1.4; }
.toc-list li:hover { color: #409eff; }
.toc-1 { font-weight: 600; }
.toc-2 { padding-left: 12px; }
.toc-3 { padding-left: 24px; font-size: 12px; color: #999; }
.markdown-body { max-width: 100%; line-height: 1.8; color: #333; }
.markdown-body :deep(h1) { font-size: 2em; border-bottom: 2px solid #4a90d9; padding-bottom: 8px; margin: 24px 0 16px; }
.markdown-body :deep(h2) { font-size: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 6px; margin: 20px 0 12px; }
.markdown-body :deep(h3) { font-size: 1.25em; margin: 16px 0 10px; }
.markdown-body :deep(p) { margin: 0 0 12px; }
.markdown-body :deep(a) { color: #4a90d9; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(code) { background: #f5f5f5; padding: 2px 5px; border-radius: 3px; font-size: 0.9em; }
.markdown-body :deep(pre) { background: #f8f8f8; border-radius: 8px; padding: 16px; overflow-x: auto; }
.markdown-body :deep(blockquote) { border-left: 4px solid #4a90d9; margin: 0; padding-left: 16px; color: #666; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid #ddd; padding: 8px 12px; }
.markdown-body :deep(th) { background: #f0f4ff; }
</style>
