<template>
  <div style="max-width:720px;">
    <h2 style="margin-bottom:20px;">新建调研任务</h2>
    <el-card shadow="never">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：AI大模型市场调研2024" />
        </el-form-item>
        <el-form-item label="调研主题" prop="topic">
          <el-input v-model="form.topic" placeholder="例如：大模型商业化应用" />
        </el-form-item>
        <el-form-item label="搜索关键词" prop="query">
          <el-input v-model="form.query" placeholder="用于数据源搜索的关键词" />
        </el-form-item>
        <el-form-item label="关键词列表">
          <el-input v-model="keywordsText" type="textarea" :rows="2"
            placeholder="每行一个关键词，用于过滤文章" />
        </el-form-item>
        <el-form-item label="时间范围（天）">
          <el-input-number v-model="form.time_range_days" :min="1" :max="365" />
        </el-form-item>
        <el-form-item label="报告模板">
          <el-select v-model="form.template" style="width:200px;">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据源配置">
          <el-checkbox v-model="enableRss">RSS</el-checkbox>
          <el-checkbox v-model="enableWeb" style="margin-left:16px;">Web</el-checkbox>
          <el-checkbox v-model="enableXhs" style="margin-left:16px;">小红书</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">创建并运行</el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/tasks'
import { ElMessage } from 'element-plus'
import api from '@/api'

const $router = useRouter()
const store = useTaskStore()
const formRef = ref()
const submitting = ref(false)
const templates = ref([])
const keywordsText = ref('')
const enableRss = ref(true)
const enableWeb = ref(true)
const enableXhs = ref(false)

const form = ref({
  name: '',
  topic: '',
  query: '',
  time_range_days: 30,
  template: 'competitor_analysis',
})

const rules = {
  name: [{ required: true, message: '请输入任务名称' }],
  topic: [{ required: true, message: '请输入调研主题' }],
}

onMounted(async () => {
  try {
    const { data } = await api.get('/sources/templates')
    templates.value = data
  } catch {}
})

async function submit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    const keywords = keywordsText.value.split('\n').map(s => s.trim()).filter(Boolean)
    const sources = {}
    if (enableRss.value) sources.rss = { enabled: true, feeds: [] }
    if (enableWeb.value) sources.web = { enabled: true, urls: [] }
    if (enableXhs.value) sources.xiaohongshu = { enabled: true }

    const payload = {
      ...form.value,
      keywords: JSON.stringify(keywords),
      sources_config: JSON.stringify(sources),
      pipeline_config: JSON.stringify([
        { step: 'content_fetcher' },
        { step: 'dedup' },
        { step: 'ai_relevance', threshold: 0.5 },
        { step: 'ai_summarize' },
      ]),
      output_config: JSON.stringify({ template: form.value.template }),
    }
    const task = await store.create(payload)
    await store.run(task.id)
    ElMessage.success('任务已创建并开始运行')
    $router.push(`/tasks/${task.id}/progress`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
