# 动画制作助手

一个用于动画制作流程辅助的 AI Agent 项目。

- 学习 Agent 工程开发
- 逐步做成真正可用的工具
- 每一步都形成可运行、可测试、可提交的工程成果

当前版本：v0.16.0

---

## 这个项目能做什么

用户用自然语言提出请求，Agent 理解意图后调用工具，工具用确定性逻辑（ffprobe / ffmpeg / 规则判断）返回结构化结果，Agent 再用自然语言解释给用户。

已经支持的检查项：

- 画幅比例（含容差）
- 单镜头 / 整集时长（含整集容差）
- 帧率
- 视频编码
- 音频编码
- 文件命名规则
- 独立字幕轨道
- 音频活动比例（只描述活动/静音分布，不判断内容类型）
- 目录级聚合（文件数量、总时长、画幅/帧率/编码一致性）

**当前不能检查**（README 末尾“已知限制”有完整列表）：

- 画面中的内嵌字幕
- 音频里是否有人物对白、是否有背景音乐
- 画面中的角色风格、构图
- 每个镜头的实际数量

**核心原则**：

- LLM 负责理解意图、选择工具、解释结构化结果
- Python 负责确定性业务逻辑
- FFmpeg / ffprobe 负责底层媒体事实
- LLM 不重新计算检测结果，不编造结果
- warning / info 不会被说成 confirmed failure

---

## 快速开始

### 环境要求

- Windows + PowerShell
- Python 3.14（项目在 3.14.8 上开发）
- FFmpeg / ffprobe 已安装并加入 PATH（项目在 FFmpeg 9.0.1 上验证）

### 安装

```powershell
Set-Location "D:\AIProjects\agent-learnin"

# 创建虚拟环境（如果还没有）
python -m venv .venv

# 安装依赖
.\.venv\Scripts\python.exe -m pip install -r requirements.txt