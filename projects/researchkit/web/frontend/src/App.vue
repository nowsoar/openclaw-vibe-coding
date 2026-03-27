<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-container">
      <el-aside width="220px" class="sidebar">
        <div class="logo">
          <el-icon><DataAnalysis /></el-icon>
          <span>ResearchKit</span>
        </div>
        <el-menu :router="true" :default-active="$route.path" class="side-menu">
          <el-menu-item index="/">
            <el-icon><Odometer /></el-icon>
            <span>仪表盘</span>
          </el-menu-item>
          <el-menu-item index="/tasks/new">
            <el-icon><Plus /></el-icon>
            <span>新建调研</span>
          </el-menu-item>
          <el-menu-item index="/sources">
            <el-icon><Connection /></el-icon>
            <span>数据源管理</span>
          </el-menu-item>
          <el-menu-item index="/templates">
            <el-icon><Document /></el-icon>
            <span>报告模板</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-container>
        <el-header class="top-bar">
          <span class="page-title">{{ $route.meta.title || 'ResearchKit' }}</span>
        </el-header>
        <el-main class="main-content">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </el-config-provider>
</template>

<script setup>
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif; }
.app-container { height: 100vh; }
.sidebar { background: #1a1a2e; display: flex; flex-direction: column; }
.logo {
  padding: 20px 24px;
  display: flex; align-items: center; gap: 10px;
  color: #6eb5ff; font-size: 18px; font-weight: 700;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.side-menu { border-right: none; background: transparent; flex: 1; }
.side-menu .el-menu-item { color: rgba(255,255,255,0.7); }
.side-menu .el-menu-item.is-active,
.side-menu .el-menu-item:hover { color: #fff; background: rgba(110,181,255,0.15); }
.top-bar {
  display: flex; align-items: center;
  border-bottom: 1px solid #eee; background: #fff;
  padding: 0 24px;
}
.page-title { font-size: 16px; font-weight: 600; color: #333; }
.main-content { background: #f5f7fa; overflow-y: auto; }
</style>
