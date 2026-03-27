<template>
  <div style="display:flex;justify-content:center;align-items:center;min-height:100vh;background:#f5f7fa;">
    <el-card style="width:400px;" shadow="always">
      <h2 style="text-align:center;margin-bottom:24px;">🔬 ResearchKit</h2>
      <el-tabs v-model="tab">
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent="doLogin">
            <el-form-item><el-input v-model="form.username" placeholder="用户名" prefix-icon="User" /></el-form-item>
            <el-form-item><el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" /></el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" style="width:100%;">登录</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form @submit.prevent="doRegister">
            <el-form-item><el-input v-model="regForm.username" placeholder="用户名" prefix-icon="User" /></el-form-item>
            <el-form-item><el-input v-model="regForm.email" placeholder="邮箱（可选）" prefix-icon="Message" /></el-form-item>
            <el-form-item><el-input v-model="regForm.password" type="password" placeholder="密码" prefix-icon="Lock" /></el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" style="width:100%;">注册</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const auth = useAuthStore()
const $router = useRouter()
const tab = ref('login')
const loading = ref(false)
const form = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', email: '' })

async function doLogin() {
  loading.value = true
  try {
    await auth.login(form.value.username, form.value.password)
    $router.push('/')
  } catch (e) {
    ElMessage.error(e.message)
  } finally { loading.value = false }
}

async function doRegister() {
  loading.value = true
  try {
    await auth.register(regForm.value.username, regForm.value.password, regForm.value.email)
    ElMessage.success('注册成功，请登录')
    tab.value = 'login'
  } catch (e) {
    ElMessage.error(e.message)
  } finally { loading.value = false }
}
</script>
