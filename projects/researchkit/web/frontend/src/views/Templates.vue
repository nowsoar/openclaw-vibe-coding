<template>
  <div class="templates">
    <el-row :gutter="20">
      <!-- 模板列表 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>报告模板</template>
          <el-menu v-model:default-active="selectedId" @select="onSelect">
            <el-menu-item v-for="t in templates" :key="t.id" :index="t.id">
              <el-icon><Document /></el-icon>
              <template #title>
                <div>
                  <div>{{ t.name }}</div>
                  <div style="font-size: 11px; color: #999; white-space: normal; line-height: 1.3">{{ t.description }}</div>
                </div>
              </template>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <!-- 模板编辑 -->
      <el-col :span="16">
        <el-card shadow="never" v-loading="loading">
          <template #header>
            <div class="editor-header">
              <span>{{ selected?.name || '选择模板' }}</span>
              <el-button type="primary" size="small" @click="save" :disabled="!selected">保存</el-button>
            </div>
          </template>

          <div v-if="selected">
            <el-form label-width="120px">
              <el-form-item label="模板名称">
                <el-input v-model="selected.name" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="selected.description" />
              </el-form-item>
              <el-form-item label="AI 合成提示词">
                <el-input
                  v-model="selected.synthesis_prompt"
                  type="textarea" :rows="12"
                  placeholder="在这里自定义 AI 合成报告的提示词..."
                />
              </el-form-item>
            </el-form>
            <el-divider>提示词变量说明</el-divider>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="{topic}">调研主题名称</el-descriptions-item>
              <el-descriptions-item label="{article_count}">文章总数</el-descriptions-item>
              <el-descriptions-item label="{articles_summary}">所有文章摘要列表（自动生成）</el-descriptions-item>
            </el-descriptions>
          </div>

          <el-empty v-else description="选择左侧模板进行编辑" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const templates = ref([])
const selected = ref(null)
const selectedId = ref('')
const loading = ref(false)

onMounted(async () => {
  const { data } = await api.get('/templates')
  templates.value = data
})

async function onSelect(id) {
  selectedId.value = id
  loading.value = true
  try {
    const { data } = await api.get(`/templates/${id}`)
    selected.value = { ...data }
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!selected.value) return
  try {
    await api.put(`/templates/${selectedId.value}`, selected.value)
    ElMessage.success('模板已保存')
    // 更新列表中的描述
    const idx = templates.value.findIndex(t => t.id === selectedId.value)
    if (idx !== -1) {
      templates.value[idx].name = selected.value.name
      templates.value[idx].description = selected.value.description
    }
  } catch {
    ElMessage.error('保存失败')
  }
}
</script>

<style scoped>
.templates { padding: 24px; }
.editor-header { display: flex; justify-content: space-between; align-items: center; }
</style>
