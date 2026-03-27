<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-logo">
        <el-icon size="40"><DataAnalysis /></el-icon>
        <h1>ResearchKit</h1>
        <p>AI 驱动的自动化调研平台</p>
      </div>

      <el-tabs v-model="activeTab" class="auth-tabs">
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" @submit.prevent="handleLogin" size="large">
            <el-form-item>
              <el-input v-model="loginForm.username" placeholder="邮箱或用户名" clearable>
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="loginForm.password" type="password" placeholder="密码"
                show-password clearable>
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
                登录
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form :model="regForm" @submit.prevent="handleRegister" size="large">
            <el-form-item>
              <el-input v-model="regForm.email" placeholder="邮箱" clearable>
                <template #prefix><el-icon><Message /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="regForm.username" placeholder="用户名" clearable>
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="regForm.password" type="password" placeholder="密码（至少8位）"
                show-password clearable>
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
                注册
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="guest-hint">
        <el-divider>或者</el-divider>
        <el-button @click="continueAsGuest" plain style="width: 100%">以游客身份使用</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const activeTab = ref('login')
const loading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ email: '', username: '', password: '' })

async function handleLogin() {
  loading.value = true
  try {
    const form = new FormData()
    form.append('username', loginForm.username)
    form.append('password', loginForm.password)
    const { data } = await api.post('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    authStore.setTokens(data.access_token, data.refresh_token)
    await authStore.fetchMe()
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  loading.value = true
  try {
    await api.post('/auth/register', regForm)
    ElMessage.success('注册成功，请登录')
    activeTab.value = 'login'
    loginForm.username = regForm.email
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}

function continueAsGuest() {
  router.push('/')
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  display: flex; align-items: center; justify-content: center;
}
.auth-card {
  background: #fff; border-radius: 16px; padding: 40px;
  width: 400px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
.auth-logo { text-align: center; margin-bottom: 24px; }
.auth-logo h1 { font-size: 24px; color: #1a1a2e; margin: 12px 0 4px; }
.auth-logo p { color: #999; font-size: 14px; }
.auth-logo .el-icon { color: #409eff; }
.auth-tabs { margin-bottom: 8px; }
</style>
