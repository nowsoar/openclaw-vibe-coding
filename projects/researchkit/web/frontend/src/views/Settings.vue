<template>
  <div class="settings-page">
    <el-card class="settings-card">
      <template #header>
        <span class="card-title">⚙️ 系统设置</span>
      </template>

      <el-tabs v-model="activeTab">
        <!-- ── AI 配置 Tab ─────────────────────────────────────────── -->
        <el-tab-pane label="🤖 AI 配置" name="ai">
          <el-form :model="aiForm" label-width="120px" class="settings-form">

            <!-- 快速预设 -->
            <el-form-item label="快速填入">
              <div class="provider-presets">
                <el-button
                  v-for="p in providers"
                  :key="p.name"
                  size="small"
                  :class="['preset-btn', aiForm.base_url === p.base_url ? 'active' : '']"
                  @click="applyPreset(p)"
                >
                  {{ p.label }}
                </el-button>
              </div>
              <div class="field-hint">选择服务商后自动填入 Base URL 和推荐模型，只需再填写 API Key 即可</div>
            </el-form-item>

            <el-form-item label="API Key">
              <el-input
                v-model="aiForm.api_key"
                type="password"
                show-password
                placeholder="sk-... (留空则不修改)"
                style="max-width: 480px"
              />
              <div v-if="settings.ai?.api_key_set" class="field-hint">
                当前已配置：{{ settings.ai.api_key_preview }}
              </div>
              <div v-else class="field-hint warn">⚠️ 尚未配置 API Key，任务无法运行</div>
            </el-form-item>

            <el-form-item label="Base URL">
              <el-input
                v-model="aiForm.base_url"
                placeholder="https://api.openai.com/v1"
                style="max-width: 480px"
              />
              <div class="field-hint">支持任意 OpenAI 兼容接口或 Anthropic 接口</div>
            </el-form-item>

            <el-form-item label="默认模型">
              <el-input
                v-model="aiForm.model"
                placeholder="gpt-4o-mini"
                style="max-width: 300px"
              />
            </el-form-item>

            <el-form-item label="API 类型">
              <el-select v-model="aiForm.api_type" style="width: 240px">
                <el-option label="OpenAI 兼容（大多数第三方）" value="openai" />
                <el-option label="Anthropic 原生格式" value="anthropic" />
              </el-select>
              <div class="field-hint">
                OpenAI 兼容格式适用于 DeepSeek、Moonshot、Qwen、Doubao、OpenRouter 等绝大多数第三方服务
              </div>
            </el-form-item>

            <el-form-item label="费用限额 (USD)">
              <el-input-number
                v-model="aiForm.cost_limit"
                :min="0.1"
                :max="100"
                :step="0.5"
                :precision="1"
              />
            </el-form-item>

            <el-form-item label="报告输出目录">
              <el-input
                v-model="aiForm.output_dir"
                placeholder="~/Documents/research/"
                style="max-width: 400px"
              />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveAI">💾 保存</el-button>
              <el-button :loading="testing" @click="testAI" style="margin-left: 12px">
                🔗 测试连接
              </el-button>
            </el-form-item>

            <el-form-item v-if="testResult">
              <el-alert
                :type="testResult.ok ? 'success' : 'error'"
                :title="testResult.message"
                show-icon
                :closable="false"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- ── 微信公众号 Tab ───────────────────────────────────────── -->
        <el-tab-pane label="💬 微信公众号" name="wechat">
          <div class="wechat-status" v-if="settings.wechat">
            <el-tag :type="settings.wechat.configured ? 'success' : 'warning'" size="large">
              {{ settings.wechat.configured ? '✅ 已配置' : '⚠️ 未配置' }}
            </el-tag>
            <span v-if="settings.wechat.updated_at" class="updated-at">
              上次更新：{{ settings.wechat.updated_at.slice(0, 19).replace('T', ' ') }}
            </span>
          </div>

          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 20px"
          >
            <template #title>如何获取微信公众号 curl 命令？</template>
            <ol class="curl-guide">
              <li>在浏览器中打开微信公众号后台 <code>mp.weixin.qq.com</code> 并登录</li>
              <li>打开浏览器开发者工具（F12）→ Network 面板</li>
              <li>随意打开一个文章列表页面，找到 <code>appmsg</code> 相关请求</li>
              <li>右键点击该请求 → Copy → Copy as cURL</li>
              <li>将复制的 curl 命令粘贴到下方文本框</li>
            </ol>
          </el-alert>

          <el-form :model="wechatForm" label-width="120px" class="settings-form">
            <el-form-item label="cURL 命令">
              <el-input
                v-model="wechatForm.curl_command"
                type="textarea"
                :rows="8"
                placeholder="粘贴从浏览器复制的 curl 命令..."
                style="max-width: 700px; font-family: monospace; font-size: 12px"
              />
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="savingWechat"
                @click="saveWechat"
                :disabled="!wechatForm.curl_command"
              >
                📥 提取并保存
              </el-button>
            </el-form-item>

            <el-divider>或手动填写</el-divider>

            <el-form-item label="Cookie">
              <el-input
                v-model="wechatForm.cookie"
                type="textarea"
                :rows="3"
                placeholder="手动粘贴 Cookie 字符串"
                style="max-width: 700px"
              />
            </el-form-item>

            <el-form-item label="Token">
              <el-input
                v-model="wechatForm.token"
                placeholder="数字 token，如 123456789"
                style="max-width: 300px"
              />
            </el-form-item>

            <el-form-item>
              <el-button
                :loading="savingWechat"
                @click="saveWechatManual"
                :disabled="!wechatForm.cookie && !wechatForm.token"
              >
                💾 保存手动凭证
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const activeTab = ref('ai')
const settings = ref({})
const saving = ref(false)
const testing = ref(false)
const savingWechat = ref(false)
const testResult = ref(null)

// ── 服务商预设 ────────────────────────────────────────────────────────
const providers = [
  { label: 'OpenAI',      base_url: 'https://api.openai.com/v1',                                    model: 'gpt-4o-mini',          api_type: 'openai' },
  { label: 'DeepSeek',    base_url: 'https://api.deepseek.com/v1',                                  model: 'deepseek-chat',        api_type: 'openai' },
  { label: 'Moonshot',    base_url: 'https://api.moonshot.cn/v1',                                   model: 'moonshot-v1-8k',       api_type: 'openai' },
  { label: 'Qwen (阿里)', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',            model: 'qwen-plus',            api_type: 'openai' },
  { label: 'Doubao (字节)', base_url: 'https://ark.cn-beijing.volces.com/api/v3',                   model: 'doubao-pro-32k',       api_type: 'openai' },
  { label: 'Gemini',      base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/',     model: 'gemini-2.0-flash',     api_type: 'openai' },
  { label: 'OpenRouter',  base_url: 'https://openrouter.ai/api/v1',                                 model: 'deepseek/deepseek-chat', api_type: 'openai' },
  { label: 'Anthropic',   base_url: 'https://api.anthropic.com',                                    model: 'claude-3-5-haiku-20241022', api_type: 'anthropic' },
  { label: '自定义',       base_url: '',                                                              model: '',                     api_type: 'openai' },
]

function applyPreset(preset) {
  if (preset.label === '自定义') {
    aiForm.value.base_url = ''
    aiForm.value.model = ''
    aiForm.value.api_type = 'openai'
    return
  }
  aiForm.value.base_url = preset.base_url
  aiForm.value.model = preset.model
  aiForm.value.api_type = preset.api_type
}

const aiForm = ref({
  api_key: '',
  base_url: '',
  model: '',
  api_type: 'openai',
  cost_limit: 5.0,
  output_dir: '',
})

const wechatForm = ref({
  curl_command: '',
  cookie: '',
  token: '',
})

async function loadSettings() {
  try {
    const { data } = await api.get('/settings')
    settings.value = data
    // 填充表单默认值（不填 api_key，保持 placeholder 提示）
    aiForm.value.base_url = data.ai?.base_url || ''
    aiForm.value.model = data.ai?.default_model || ''
    aiForm.value.api_type = data.ai?.api_type || 'openai'
    aiForm.value.cost_limit = data.ai?.cost_limit_usd ?? 5.0
    aiForm.value.output_dir = data.output_dir || ''
  } catch (e) {
    ElMessage.error('加载配置失败：' + (e.response?.data?.detail || e.message))
  }
}

async function saveAI() {
  saving.value = true
  testResult.value = null
  try {
    const payload = {
      ai_base_url: aiForm.value.base_url,
      ai_model: aiForm.value.model,
      ai_api_type: aiForm.value.api_type,
      ai_cost_limit: aiForm.value.cost_limit,
      output_dir: aiForm.value.output_dir,
    }
    if (aiForm.value.api_key) {
      payload.ai_api_key = aiForm.value.api_key
    }
    await api.post('/settings', payload)
    ElMessage.success('AI 配置已保存')
    aiForm.value.api_key = ''
    await loadSettings()
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function testAI() {
  testing.value = true
  testResult.value = null
  try {
    const { data } = await api.post('/settings/test-ai')
    testResult.value = data
  } catch (e) {
    testResult.value = { ok: false, message: e.response?.data?.detail || e.message }
  } finally {
    testing.value = false
  }
}

async function saveWechat() {
  savingWechat.value = true
  try {
    await api.post('/settings', { curl_command: wechatForm.value.curl_command })
    ElMessage.success('微信凭证已提取并保存')
    wechatForm.value.curl_command = ''
    await loadSettings()
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    savingWechat.value = false
  }
}

async function saveWechatManual() {
  savingWechat.value = true
  try {
    await api.post('/settings', {
      wechat_cookie: wechatForm.value.cookie,
      wechat_token: wechatForm.value.token,
    })
    ElMessage.success('微信凭证已保存')
    wechatForm.value.cookie = ''
    wechatForm.value.token = ''
    await loadSettings()
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    savingWechat.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.settings-card {
  border-radius: 8px;
}

.card-title {
  font-size: 18px;
  font-weight: 700;
}

.settings-form {
  padding-top: 16px;
}

.field-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.field-hint.warn {
  color: #e6a23c;
}

.wechat-status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.updated-at {
  font-size: 13px;
  color: #909399;
}

.curl-guide {
  margin: 8px 0 0 16px;
  line-height: 1.8;
  font-size: 13px;
}

.curl-guide code {
  background: #f0f0f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}

.provider-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preset-btn {
  border-radius: 16px !important;
}

.preset-btn.active {
  background-color: #409eff !important;
  color: #fff !important;
  border-color: #409eff !important;
}
</style>
