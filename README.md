# 动画制作助手

一个用于动画制作流程辅助的个人项目。

- 前半部分：确定性的视频规范检查 Agent
- 后半部分：ComfyUI 批量生成、技术质量门控、审片页面

当前版本：v0.21.0

---

## 项目由两部分组成

### 第一部分：视频规范检查 Agent

用户用自然语言提出请求，Agent 理解意图后调用工具，工具用确定性逻辑（ffprobe / ffmpeg / 规则判断）返回结构化结果，Agent 再用自然语言解释给用户。

已支持的检查项：

- 画幅比例（含容差）
- 单镜头 / 整集时长（含整集容差）
- 帧率
- 视频编码 / 音频编码
- 文件命名规则
- 独立字幕轨道
- 音频活动比例（只描述活动/静音分布，不判断内容类型）
- 目录级聚合（文件数量、总时长、画幅/帧率/编码一致性）

### 第二部分：ComfyUI 批量生成

用脚本驱动 ComfyUI 的 API，批量生成视频，每次记录 seed 和参数，生成审片页面，并对输出做确定性的技术质量检测。

当前支持：

- 通过 `workflow_profile.json` 把语义角色（prompt、seed、时长、分辨率、输出节点）映射到具体工作流节点
- 批量循环，断点续跑，`--force` 强制重跑
- 每个批次生成独立目录 `batches/YYYYMMDD_HHMMSS/`
- 自动生成 `review.html`，浏览器打开即可一次看完一批
- 技术质量检测：时长异常、无音频流、文件过小、帧率偏离

核心原则（两部分共用）：

- LLM 只负责理解意图和解释结果，不重新计算确定性数据
- Python 负责确定性业务逻辑
- FFmpeg / ffprobe 负责底层媒体事实
- warning / info 不会被说成 confirmed failure

---

## 快速开始

### 环境要求

- Windows + PowerShell
- Python 3.14（项目在 3.14.8 上开发）
- FFmpeg / ffprobe 已安装并加入 PATH
- ComfyUI 桌面版（仅批量生成部分需要）

### 安装

```powershell
Set-Location "D:\AIProjects\agent-learnin"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 第一部分：启动检查 Agent

```powershell
Set-Location "D:\AIProjects\agent-learnin"
.\.venv\Scripts\python.exe .\app.py
```

浏览器打开 `http://127.0.0.1:7860`，在“模型设置”里选平台、填 API Key、点保存。

### 第二部分：批量生成

先确保 ComfyUI 桌面版已启动，Web 界面能打开（默认 `http://127.0.0.1:8188`）。

```powershell
Set-Location "D:\AIProjects\agent-learnin"

# 跑 5 个随机 seed
.\.venv\Scripts\python.exe .\batch_run.py --profile workflow_profile_2.json --count 5 --megapixels 1.5 --duration 6.0

# 指定 seed
.\.venv\Scripts\python.exe .\batch_run.py --profile workflow_profile_2.json --seeds 123,456 --megapixels 1.5 --duration 6.0

# 强制重跑已完成的 seed
.\.venv\Scripts\python.exe .\batch_run.py --profile workflow_profile_2.json --seeds 123 --megapixels 1.5 --duration 6.0 --force
```

跑完后终端会打印审片页面路径，用浏览器打开那个 `review.html`。

---

## ComfyUI 批量生成的配置

### 三个配置文件

| 文件 | 作用 | 是否提交到 Git |
|---|---|---|
| `workflow_api_*.json` | ComfyUI 导出的 API 格式工作流 | 提交（可复现的输入） |
| `workflow_profile_*.json` | 语义角色 → 节点 id + 参数名 的映射 | 提交 |
| `subject_definitions.txt` | 本次生成用的 prompt | 提交 |

`workflow_api_*.json` 必须从 ComfyUI 界面 **工作流 → 导出（API）** 得到，不能手动改 UI 格式的 JSON。

### profile 的结构

```json
{
  "name": "h3_ref2v_selflift",
  "workflow_file": "workflow_api_2.json",
  "output_node": {"id": "364", "title": "Video Combine 🎥🅥🅗🅢"},
  "output_dir": "D:/Comfy-Desktop/ComfyUI-Shared/output",
  "roles": {
    "prompt":          {"node": "263", "param": "text"},
    "seed":            {"node": "397", "param": "seed"},
    "duration":        {"node": "259", "param": "value"},
    "aspect_ratio":    {"node": "252", "param": "aspect_ratio"},
    "megapixels":      {"node": "252", "param": "megapixels"},
    "filename_prefix": {"node": "364", "param": "filename_prefix"}
  }
}
```

`roles` 里只写本次批量实际要控制的参数。`batch_run.py` 当前会设 `prompt`、`seed`、`duration`、`aspect_ratio`、`megapixels` 五个角色，profile 里缺任何一个都会报 `KeyError`。

### 换工作流的流程

1. 在 ComfyUI 里加载新工作流，确认无红框；
2. 导出 API JSON，放到项目目录；
3. 用这条命令列出所有节点的 id / class_type / title：

```powershell
$wf = Get-Content .\workflow_api_new.json -Raw -Encoding UTF8 | ConvertFrom-Json
$wf.PSObject.Properties | ForEach-Object {
    "{0}  {1}  {2}" -f $_.Name, $_.Value.class_type, $_.Value._meta.title
}
```

4. 新建 `workflow_profile_new.json`，把角色映射到新节点 id；
5. `batch_run.py --profile workflow_profile_new.json ...` 跑。

**Python 代码不用改。** 这就是 profile 机制的目的。

### 常见坑

- **API 格式丢了 UI 布局和注释**：这是 ComfyUI 的设计，API 格式是给程序用的，不是给人编辑的。要看、要改，加载原来的 UI 工作流。
- **节点 id 会变**：重新加载工作流后 id 可能重新编号，每次换工作流都要重新核对 profile。
- **`megapixels` 会被脚本默认值覆盖**：`batch_run.py` 默认 `megapixels=1.0`，如果工作流 UI 里设的是 1.5，脚本会把分辨率降下来。**每次跑都要显式传 `--megapixels`**。
- **prompt 文件为空会清空工作流的 prompt**：`batch_run.py` 有非空检查，读到空文件会直接退出。
- **VHS_VideoCombine 先写 png 再写 mp4**：`find_output` 会等到 mp4 出现才返回，不会拿到预览图。
- **ComfyUI 有内部缓存**：同 seed 重跑可能几秒就返回上次的结果。改 prompt 时要注意这一点。

---

## 批次目录和审片页面

每次 `batch_run.py` 创建一个批次目录：

```text
batches/
└── 20261021_160759/
    ├── seed_3578509293379117.mp4
    ├── seed_1919492562697271.mp4
    ├── seed_5753404422420423.mp4
    └── review.html
```

`review.html` 的特点：

- 每个视频一个播放器，下方显示 seed、耗时、文件大小、时长、帧率；
- 右上角有“通过”或“可疑”标记；
- 可疑的视频排在前面，下方列出原因；
- 顶部显示成功数量和可疑数量。

`batches/` 和 `batch_log.csv` 已被 `.gitignore` 忽略，不进 Git。

---

## 技术质量检测的边界

`quality_check.py` 能抓：

- 时长异常（实际时长与预期差 > 1 秒）
- 没有音频流
- 文件过小（< 0.5MB）
- 帧率异常（偏离 24fps 超过 0.5）

**它抓不住**：

- 画面局部崩坏、色块、肢体扭曲
- 人物形象与参考图不符
- 动作不符合 prompt 描述
- 画风漂移（2D 手绘变成 3D 写实）

这些需要视觉模型（AIGCQA、VideoArgus、多模态 LLM），当前版本没有接入。**技术检测通过不代表画面没问题**，人工审片仍然必要。

---

## 其他配置

### config.json（检查 Agent 用）

`config.json` 保存各平台的 API Key 和当前选中的平台，已被 `.gitignore` 忽略。

**注意**：

- 不要提交到 Git；
- 不要在用户之间共享；
- 推荐通过 UI 修改，不要用 PowerShell 的 `Set-Content` / `ConvertTo-Json` 直接改（会导致编码损坏）。

支持的平台：DeepSeek、豆包、通义千问、Kimi、智谱 GLM、OpenAI、Claude。模型名以各平台官方文档为准。

### project.json（检查 Agent 用）

`project.json` 是**项目规范**，会被提交到 Git。字段包括画幅、时长、帧率、编码、命名规则、音频/字幕要求。修改规则不需要改代码。

---

## 项目结构

```text
agent-learnin/
├── .env                     # 可选，DEEPSEEK_API_KEY（已被 .gitignore 忽略）
├── .gitignore
├── config.json              # 本机运行时配置（已被 .gitignore 忽略）
├── batch_log.csv            # 批量生成日志（已被 .gitignore 忽略）
├── batches/                 # 批次输出（已被 .gitignore 忽略）
├── start.bat                # Windows 启动器
├── app.py                   # Gradio 界面 + Agent 定义 + 多平台配置
├── batch_run.py             # 批量生成主脚本
├── comfy_adapter.py         # 工作流适配层（profile → 节点参数）
├── quality_check.py         # 技术质量检测
├── workflow_api.json        # 旧工作流（v0.18 起的第一个 profile）
├── workflow_api_2.json      # 新工作流（SelfLift H3）
├── workflow_profile.json    # 旧工作流的角色映射
├── workflow_profile_2.json  # 新工作流的角色映射
├── subject_definitions.txt  # 本次生成的 prompt
├── probe_run.py             # 单次生成调试脚本
├── main.py                  # 早期学习入口（历史文件）
├── project.json             # 项目规范配置
├── requirements.txt
├── tools.py                 # 核心业务逻辑 + Agent Tool
├── tools_v01_backup.py      # v0.1 备份（历史文件，不删）
├── tests/                   # 单元测试 + 集成测试
└── .venv/
```

---

## 运行测试

```powershell
Set-Location "D:\AIProjects\agent-learnin"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前共 196 个测试，覆盖检查 Agent 的纯函数和集成逻辑。批量生成部分（`batch_run.py`、`comfy_adapter.py`、`quality_check.py`）目前没有单元测试，依赖手动验证。

---

## 已知限制

- 视觉质量没有自动检测。技术检测通过不代表画面没问题。
- 生成质量存在种子方差。同一个工作流、同一套参数，不同 seed 的输出质量差异可能很大。批量跑 + 人工挑是当前的工作方式。
- 有 `<Picture 5>` 这类 prompt 引用但工作流没有对应输入节点时，模型会忽略该引用，导致“从上一段视频的最后一帧开始”这类约束失效。
- ComfyUI 的内部缓存可能导致同 seed 重跑几秒返回旧结果。

---

## 版本历史

| 版本 | 内容 |
|---|---|
| v0.21.0 | 技术质量检测（时长、音频流、文件大小、帧率） |
| v0.20.0 | 批次目录、审片页面、`--force` 重跑、mp4 优先检测 |
| v0.19.0 | SelfLift H3 工作流 profile、prompt 非空检查 |
| v0.18.0 | ComfyUI 适配层（profile 机制）、单次探测脚本 |
| v0.17.x | README 更新，补 requirements.txt |
| v0.16.0 | UI 加多平台下拉框，切换平台写入 config.json |
| v0.15.0 | build_agent 从 config.json 读取 active_provider |
| v0.14.0 | config.json 管理 API Key，UI 增加“保存设置” |
| v0.13.x | 从 .env 加载 API Key，Gradio Soft 主题，Windows 启动器 |
| v0.12.0 | 画幅容差 |
| v0.11.0 | 文件命名检查 |
| v0.10.x | 集成测试 |
| v0.9.x | 工程整理 |
| v0.8.x | 目录级检查 |
| v0.7.x | 视频/音频编码检查 |
| v0.6.x | 时长容差 + 报告文案同步 |
| v0.5.0 | target_fps 支持 |
| v0.4.x | 抽纯函数，建立回归测试 |

---

## 开发原则

- 每一个重要功能完成后：先运行、测试、检查 diff、`git diff --check`、`git add`、`git diff --cached`、commit
- 不直接 `git add .`，尤其不要把未跟踪的临时文件加入 Git
- 不删除 `tools_v01_backup.py`，不删除历史 tag，不修改历史 commit，不使用 `git clean -fd`
- 不让 LLM 重新计算确定性检测数据
- 不把 warning 说成 confirmed failure，不把 info 说成 failure
- 不把“没有 subtitle stream”说成“画面绝对没有字幕”
- 不把 audio stream 说成 BGM
- 不在没有实际检查的情况下声称全部通过