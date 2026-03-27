<template>
  <el-config-provider>
    <el-container style="height: 100vh;">
      <el-aside width="220px" style="background:#1a1a2e; overflow:hidden;">
        <div style="color:#fff; padding:20px 16px 8px; font-size:18px; font-weight:700;">
          🔬 ResearchKit
        </div>
        <el-menu
          :router="true"
          :default-active="$route.path"
          background-color="#1a1a2e"
          text-color="#ccc"
          active-text-color="#409eff"
          style="border:none;"
        >
          <el-menu-item index="/">
            <el-icon><Odometer /></el-icon><span>仪表板</span>
          </el-menu-item>
          <el-menu-item index="/new">
            <el-icon><Plus /></el-icon><span>新建调研</span>
          </el-menu-item>
          <el-menu-item index="/tasks">
            <el-icon><List /></el-icon><span>任务列表</span>
          </el-menu-item>
          <el-menu-item index="/reports">
            <el-icon><Document /></el-icon><span>调研报告</span>
          </el-menu-item>
          <el-menu-item index="/sources">
            <el-icon><Connection /></el-icon><span>数据源</span>
          </el-menu-item>
        </el-menu>
      </el-aside>
      <el-main style="padding:24px; background:#f5f7fa; overflow:auto;">
        <router-view />
      </el-main>
    </el-container>
  </el-config-provider>
</template>

<script setup>
import { useRoute } from 'vue-router'
const $route = useRoute()
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "PingFang SC", "Helvetica Neue", Arial, sans-serif; }
</style>
