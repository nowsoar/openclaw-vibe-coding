请将当前目录的俄罗斯方块游戏升级为一个完整的项目结构，并修复/增加以下功能：

**项目结构调整：**
把现在的 index.html 拆分成专业的项目目录结构：
- tetris/
  - index.html（主页面）
  - css/style.css（样式）
  - js/game.js（游戏核心逻辑）
  - js/ui.js（UI 交互）
  - js/storage.js（存档/读档）
  - README.md（项目说明）

**功能修复和新增：**
1. 暂停后恢复进度正确（当前暂停后进度丢失的 bug 需修复）
2. 本地存档：localStorage 保存最高分、当前关卡、游戏进度（下次打开自动恢复）
3. 音效开关按钮（用 Web Audio API 生成简单音效，不依赖外部文件）
4. 连击奖励：连续消行有额外分数加成，显示连击特效文字
5. 软降加速，硬降有视觉冲击（白色闪光效果）
6. 移动端支持：触摸滑动控制（左右滑=移动，上滑=旋转，下滑=硬降）
7. 游戏统计面板：总游戏时间、最高分（localStorage 持久化）

**完成后执行：**
- 删除根目录的旧 index.html（已移入 tetris/）
- git add .
- git commit -m "feat: restructure project, add save/resume/touch/sfx features"
- git push origin main
- 最后运行：openclaw system event --text "俄罗斯方块项目重构完成，已推送到 GitHub" --mode now
