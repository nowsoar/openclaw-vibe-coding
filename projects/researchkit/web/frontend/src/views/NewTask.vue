<template>
  <div class="new-task">
    <el-card shadow="never" class="wizard-card">
      <el-steps :active="step" align-center class="steps">
        <el-step title="基本信息" description="描述调研主题" />
        <el-step title="数据来源" description="选择信息源" />
        <el-step title="输出配置" description="选择报告格式" />
      </el-steps>

      <!-- Step 1: 基本信息 -->
      <div v-if="step === 0" class="step-content">
        <el-form :model="form" label-width="100px" size="large">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="如：2024年 AI 工具市场调研" />
          </el-form-item>
          <el-form-item label="研究主题" required>
            <el-input v-model="form.topic" placeholder="如：AI 编程工具" />
          </el-form-item>
          <el-form-item label="研究目标">
            <el-input v-model="form.query" type="textarea" :rows="3"
              placeholder="如：了解当前市场上主流 AI 编程工具的功能特性、定价和用户反馈" />
          </el-form-item>
          <el-form-item label="关键词">
            <el-select v-model="form.keywords" multiple filterable allow-create
              placeholder="输入关键词后回车添加" style="width: 100%">
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-slider v-model="form.time_range_days" :min="7" :max="90" :step="7"
              :marks="{ 7: '7天', 30: '30天', 60: '60天', 90: '90天' }" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 2: 数据来源 -->
      <div v-if="step === 1" class="step-content">
        <el-form :model="form" label-width="100px" size="large">
          <el-form-item label="RSS 订阅">
            <el-switch v-model="form.sources_config.rss.enabled" />
            <el-text type="info" size="small" style="margin-left: 8px">订阅技术博客 RSS 源</el-text>
          </el-form-item>
          <el-form-item label="微信公众号">
            <el-switch v-model="form.sources_config.wechat.enabled" />
            <el-text type="info" size="small" style="margin-left: 8px">需要配置微信 Cookie</el-text>
          </el-form-item>
          <el-form-item label="网页爬取">
            <el-switch v-model="form.sources_config.web.enabled" />
            <el-text type="info" size="small" style="margin-left: 8px">抓取指定网站内容</el-text>
          </el-form-item>

          <el-divider>处理流水线</el-divider>
          <el-form-item label="关键词过滤">
            <el-switch v-model="pipelineFlags.keyword_filter" />
          </el-form-item>
          <el-form-item label="内容去重">
            <el-switch v-model="pipelineFlags.dedup" />
          </el-form-item>
          <el-form-item label="AI 相关性过滤">
            <el-switch v-model="pipelineFlags.ai_relevance" />
          </el-form-item>
          <el-form-item label="AI 摘要生成">
            <el-switch v-model="pipelineFlags.ai_summarize" />
          </el-form-item>
          <el-form-item label="质量评分过滤">
            <el-switch v-model="pipelineFlags.quality_score" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 3: 输出配置 -->
      <div v-if="step === 2" class="step-content">
        <el-form :model="form" label-width="120px" size="large">
          <el-form-item label="报告模板">
            <el-select v-model="form.output_config.template" style="width: 100%">
              <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id">
                <span>{{ t.name }}</span>
                <span style="float: right; color: #999; font-size: 12px">{{ t.description }}</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="输出格式">
            <el-radio-group v-model="form.output_config.format">
              <el-radio value="markdown">Markdown</el-radio>
              <el-radio value="pdf">PDF</el-radio>
              <el-radio value="feishu">飞书文档</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="输出目录">
            <el-input v-model="form.output_config.dir" placeholder="~/Documents/research/" />
          </el-form-item>
        </el-form>
      </div>

      <!-- 底部按钮 -->
      <div class="wizard-footer">
        <el-button @click="step--" v-if="step > 0">上一步</el-button>
        <el-button type="primary" @click="handleNext" :loading="submitting">
          {{ step < 2 ? '下一步' : '创建任务' }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useTaskStore } from '../stores/tasks'
import api from '../api'

const router = useRouter()
const taskStore = useTaskStore()

const step = ref(0)
const submitting = ref(false)
const templates = ref([])

const form = reactive({
  name: '',
  topic: '',
  query: '',
  keywords: [],
  time_range_days: 30,
  sources_config: {
    rss: { enabled: true },
    wechat: { enabled: false },
    web: { enabled: false },
  },
  pipeline_config: [],
  output_config: {
    template: 'trend_report',
    format: 'markdown',
    dir: '~/Documents/research/',
    include_source_list: true,
  }
})

const pipelineFlags = reactive({
  keyword_filter: true,
  dedup: true,
  ai_relevance: true,
  ai_summarize: true,
  quality_score: false,
})

onMounted(async () => {
  try {
    const { data } = await api.get('/templates')
    templates.value = data
  } catch { /* ignore */ }
})

async function handleNext() {
  if (step.value < 2) {
    step.value++
    return
  }
  // 提交
  submitting.value = true
  try {
    // 构建 pipeline_config
    const pipeline = []
    if (pipelineFlags.keyword_filter) pipeline.push({ step: 'keyword_filter' })
    if (pipelineFlags.dedup) pipeline.push({ step: 'dedup' })
    if (pipelineFlags.ai_relevance) pipeline.push({ step: 'ai_relevance' })
    if (pipelineFlags.ai_summarize) pipeline.push({ step: 'ai_summarize' })
    if (pipelineFlags.quality_score) pipeline.push({ step: 'quality_score' })
    form.pipeline_config = pipeline

    const task = await taskStore.createTask({ ...form })
    ElMessage.success('任务创建成功！')

    // 立即运行
    await taskStore.runTask(task.id)
    router.push(`/tasks/${task.id}/progress`)
  } catch (e) {
    ElMessage.error('创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.new-task { padding: 24px; max-width: 800px; margin: 0 auto; }
.wizard-card { padding: 8px; }
.steps { margin: 24px 0 40px; }
.step-content { min-height: 360px; padding: 0 40px; }
.wizard-footer {
  display: flex; justify-content: flex-end; gap: 12px;
  padding-top: 24px; border-top: 1px solid #eee; margin-top: 24px;
}
</style>
