# 动画制作助手

一个用于辅助动画制作流程的 AI Agent 项目。

它不生成视频，也不分析画面内容。它做的事只有一件：

**根据 `project.json` 里定义的项目规范，检查视频文件是否符合要求，并给出结构化的中文报告。**

项目同时是一个 Agent 工程学习项目，逐步演进中。

---

## 它现在能做什么

### 单文件规范检查

对单个视频文件执行确定性的规范检查：

| 检查项 | 说明 |
|---|---|
| 画幅 | 对比项目要求的比例（如 9:16），支持任意像素尺寸的精确比例匹配 |
| 时长（单镜头） | 对比单镜头最大时长，超出即判定为 `fail` |
| 时长（整集） | 对比整集目标时长，支持配置允许误差范围 |
| 帧率 | 对比目标帧率，支持 0.5 fps 的容差（覆盖 23.976 ≈ 24 这类差异） |
| 视频编码 | 对比目标视频编码（如 h264） |
| 音频编码 | 对比目标音频编码（如 aac）；视频无音频流时判为 `not_applicable` |
| 独立字幕轨道 | 根据项目配置判断是否存在不允许的独立字幕轨道 |
| 内嵌字幕 | **当前无法检测画面文字，只提示需要人工复核** |
| 背景音乐 | **当前无法区分音频内容，只提示需要人工试听** |
| 对白 | 项目允许对白时判为 `not_applicable` |
| 音频活动比例 | 使用 `ffmpeg silencedetect` 统计有声音时段比例，仅供参考 |

### 目录级聚合检查

对一个镜头目录做整体聚合（不递归子目录）：

- 文件数量
- 总时长与整集目标的偏差
- 画幅 / 帧率 / 视频编码 / 音频编码的一致性

它**不**对每个镜头执行完整的单文件检查，也**不**跑 `silencedetect`。

---

## 架构

```
用户自然语言请求
        ↓
Agent（DeepSeek，负责理解意图、选择工具、解释结果）
        ↓
Agent Tool（get_project_info / get_video_info /
            check_video_requirements / check_directory_requirements）
        ↓
Python 业务函数（确定性逻辑）
        ↓
ffprobe / ffmpeg（底层媒体事实）
        ↓
结构化检查结果（checks / issue_report）
        ↓
Agent 用自然语言解释给用户
```

### 分层原则

- **LLM**：理解意图、选择工具、解释结果。**不重新计算、不编造检测结果。**
- **Python**：确定性业务逻辑、规则判断、结构化数据。
- **FFmpeg / ffprobe**：底层媒体事实。

所有“决定结论”的逻辑都抽成**纯函数**，可独立测试。

---

## 配置

项目规范由 `project.json` 定义。修改规则不需要改代码。

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `project_name` | str | 是 | 项目名称 |
| `aspect_ratio` | str | 是 | 目标画幅，如 `"9:16"` |
| `target_duration_seconds` | number | 是 | 整集目标时长（秒） |
| `target_duration_tolerance_seconds` | number | 否 | 整集目标时长允许误差（秒）。未配置时按精确匹配处理 |
| `max_shot_duration_seconds` | number | 是 | 单镜头最大时长（秒） |
| `target_fps` | number | 否 | 目标帧率。未配置时 fps 检查返回 `not_configured` |
| `video_codec` | str | 否 | 目标视频编码，如 `"h264"` |
| `audio_codec` | str | 否 | 目标音频编码，如 `"aac"` |
| `character_style` | str | 否 | 角色风格描述 |
| `description` | str | 否 | 项目描述 |
| `audio_requirements.background_music_allowed` | bool | 否 | 是否允许背景音乐 |
| `audio_requirements.dialogue_allowed` | bool | 否 | 是否允许人物对白 |
| `subtitle_requirements.subtitle_stream_allowed` | bool | 否 | 是否允许独立字幕轨道 |
| `subtitle_requirements.burned_in_subtitles_allowed` | bool | 否 | 是否允许画面内嵌字幕 |

---

## 项目结构

```
agent-learnin/
├── .gitignore
├── app.py                      # Gradio 界面 + Agent 定义 + 对话流程
├── main.py                     # 早期学习入口（历史文件）
├── project.json                # 项目规范配置
├── tools.py                    # 核心业务逻辑 + Agent Tool
├── tools_v01_backup.py         # v0.1 备份（历史文件，不删）
├── tests/                      # 单元测试（unittest，无第三方依赖）
│   ├── test_audio_activity_parse.py
│   ├── test_codec_check.py
│   ├── test_compliance_summary.py
│   ├── test_directory_check.py
│   ├── test_directory_summary.py
│   ├── test_duration_check.py
│   ├── test_duration_tolerance.py
│   ├── test_ffprobe_parse.py
│   ├── test_fps_check.py
│   ├── test_history_extract.py
│   └── test_issue_report.py
└── .venv/                      # 虚拟环境
```

---

## 环境要求

- **操作系统**：Windows + PowerShell
- **Python**：3.14+
- **FFmpeg / ffprobe**：需在 `PATH` 中
- **LLM**：DeepSeek（`deepseek-flash`，通过 `https://api.deepseek.com`）
- **依赖**：`openai-agents`、`gradio`、`openai`

---

## 运行

### 启动 Gradio 界面

```powershell
Set-Location "D:\AIProjects\agent-learnin"
.\.venv\Scripts\python.exe .\app.py
```

浏览器打开 `http://127.0.0.1:7860`，在“模型设置”里输入 DeepSeek API Key。

### 单独测试工具

```powershell
.\.venv\Scripts\python.exe .\tools.py
```

按提示输入 MP4 路径和视频范围（整集 / 单镜头）。

---

## 测试

全部使用 Python 自带的 `unittest`，**不依赖第三方测试框架**。

```powershell
Set-Location "D:\AIProjects\agent-learnin"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**当前：123 个测试，全部通过。**

### 测试覆盖

| 测试文件 | 覆盖的纯函数 |
|---|---|
| `test_issue_report.py` | `_build_video_issue_report` |
| `test_audio_activity_parse.py` | `_parse_silencedetect_output` |
| `test_compliance_summary.py` | `_build_compliance_summary` |
| `test_duration_check.py` | `_build_duration_check` |
| `test_duration_tolerance.py` | `_build_duration_check`（容差分支） |
| `test_ffprobe_parse.py` | `_normalize_ffprobe_streams` |
| `test_fps_check.py` | `_build_fps_check` |
| `test_codec_check.py` | `_build_codec_check` |
| `test_directory_summary.py` | `_build_directory_summary` |
| `test_directory_check.py` | `_check_directory_requirements`（mock IO） |
| `test_history_extract.py` | `_extract_history_lines` |

---

## 版本历史摘要

每个小版本对应一个 tag。以下按系列分组。

### v0.4.x —— 抽纯函数，建立回归测试

把内联在 IO 函数里的逻辑抽出来，配上单元测试，端到端验证行为不变。

- v0.4.0：为 issue_report 分类逻辑建立回归测试
- v0.4.1：抽出 `_parse_silencedetect_output`
- v0.4.2：抽出 `_build_compliance_summary`
- v0.4.3：抽出 `_build_duration_check`
- v0.4.4：抽出 `_normalize_ffprobe_streams`

### v0.5.x —— 第一个可配置检查

- v0.5.0：支持 `target_fps`，fps 检查从“永远 not_configured”变成真正的 pass / fail

### v0.6.x —— 时长容差 + 报告文案同步

- v0.6.0：支持 `target_duration_tolerance_seconds`，整集时长在容差内判为 `at_target`
- v0.6.1：duration 的 recommendation 反映已配置的容差
- v0.6.2：fps 的 recommendation 反映 4 种状态
- v0.6.3：fps 的 title 反映实际检查结果
- v0.6.4：Agent instructions 覆盖新字段
- v0.6.5：修复 Gradio 5.x 多轮对话历史解析

### v0.7.x —— 编码检查

- v0.7.0：支持 `video_codec` / `audio_codec`，新增 `_build_codec_check`
- v0.7.1：Agent instructions 覆盖新字段

### v0.8.x —— 目录级检查

- v0.8.0：`_build_directory_summary` 纯函数
- v0.8.1：`_check_directory_requirements` IO 编排 + mock 测试
- v0.8.2：把目录检查暴露为 Agent 工具，并约束 duration_status 的报告措辞

### v0.9.x —— 工程整理

- v0.9.0：Agent instructions 拆分为 6 个主题常量（逐字比对验证内容不变）
- v0.9.1：把工具调用日志从 `print` 改为 `logging`

---

## 已知边界

以下内容**当前版本无法检测**，报告中只会提示“需人工复核”或“不适用”，**不会**被判定为“已通过”：

- **画面中的文字**（内嵌字幕）—— 需要 OCR
- **音轨内容**（是否存在背景音乐、是否为对白）—— 需要音频分类
- **画面内容**（角色风格、构图、角色是否出框）—— 需要视觉模型
- **镜头实际数量** —— 需要场景检测
- **字幕内容** —— 需读取字幕流文本

另外：

- **没有独立字幕轨道 ≠ 画面中没有内嵌字幕**
- **存在音频流 ≠ 存在背景音乐**
- **`warning` 不是已确认的违规**，它表示需要复核或检测能力不足
- **`info` 不是不合格**，它只是参考信息

---

## 开发原则

- LLM 不重新计算、不编造检测结果
- 确定性逻辑由 Python 负责
- 检测层 / 规则层 / 报告层 / Agent 层职责清晰
- 每个功能改动先写测试，再端到端验证
- 行为变更与重构分离
- 每个 tag 独立可回退