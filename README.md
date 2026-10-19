# 动画制作助手

一个用于动画制作流程辅助的 AI Agent 项目。

- 学习 Agent 工程开发
- 逐步做成真正可用的工具
- 每一步都形成可运行、可测试、可提交的工程成果

当前版本：v0.16.0

---

## 这个项目能做什么

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

当前不能检查：

- 画面中的内嵌字幕（需要 OCR）
- 音频里是否有人物对白、是否有背景音乐（需要音频分类）
- 画面中的角色风格、构图（需要视觉模型）
- 每个镜头的实际数量（需要场景检测）

核心原则：

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
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 第一次使用

1. 启动应用：

```powershell
Set-Location "D:\AIProjects\agent-learnin"
.\.venv\Scripts\python.exe .\app.py
```

或者双击 `start.bat`。

2. 浏览器打开 `http://127.0.0.1:7860`。

3. 在“模型设置”里：

   - 从“大模型平台”下拉框选择平台（默认 DeepSeek）；
   - 在 Key 输入框里粘贴对应平台的 API Key；
   - 点“保存设置”，状态行显示“已保存到 config.json，当前平台：xxx”。

4. 关闭程序后重新启动，Key 会自动填充。

5. 在对话区输入问题，例如：

   - “这个项目的画幅要求是什么？”
   - “检查 D:\videos\ep01_shot_001.mp4 是否符合项目规范，这是单个镜头”
   - “检查 D:\videos\ep01 这个目录的整体情况”

---

## 配置说明

### config.json

`config.json` 是本机运行时配置，保存各平台的 API Key 和当前选中的平台。

**注意**：

- 已被 `.gitignore` 忽略，**不要提交到 Git**；
- 包含 API Key，**不要在用户之间共享**；
- 推荐通过 UI 的“模型设置”修改，不要用 PowerShell 的 `Set-Content` / `ConvertTo-Json` 直接改（在中文 Windows 上会导致编码损坏）。

结构：

```json
{
  "active_provider": "deepseek",
  "providers": {
    "deepseek": {
      "display_name": "DeepSeek",
      "base_url": "https://api.deepseek.com",
      "models": ["deepseek-flash", "deepseek-v4-pro"],
      "default_model": "deepseek-flash",
      "api_key": ""
    }
  }
}
```

字段说明：

| 字段 | 含义 |
|---|---|
| `active_provider` | 当前使用的平台，必须是 `providers` 中的一个 key |
| `providers.{name}.display_name` | UI 中显示的平台名称 |
| `providers.{name}.base_url` | 该平台的 OpenAI 兼容接口地址 |
| `providers.{name}.models` | 该平台可用模型列表 |
| `providers.{name}.default_model` | 默认使用的模型 |
| `providers.{name}.api_key` | 该平台的 API Key |

缺失的字段会从 `app.py` 的 `DEFAULT_CONFIG` 深度合并补齐。例如只写：

```json
{
  "active_provider": "deepseek",
  "providers": {
    "deepseek": {"api_key": "sk-..."}
  }
}
```

也能正常工作。

### 支持的平台

| provider | 显示名 | base_url |
|---|---|---|
| `deepseek` | DeepSeek | `https://api.deepseek.com` |
| `doubao` | 豆包（火山方舟） | `https://ark.cn-beijing.volces.com/api/v3` |
| `qwen` | 通义千问（阿里云百炼） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `kimi` | Kimi（月之暗面） | `https://api.moonshot.cn/v1` |
| `zhipu` | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4/` |
| `openai` | OpenAI | `https://api.openai.com/v1` |
| `claude` | Anthropic Claude（OpenAI 兼容层） | `https://api.anthropic.com/v1/` |

模型名以各平台官方文档为准。平台更新模型后，改 `config.json` 里的 `models` / `default_model` 即可，不需要动代码。

### 各平台 API Key 获取地址

| 平台 | 控制台入口 |
|---|---|
| DeepSeek | https://platform.deepseek.com/api_keys |
| 豆包（火山方舟） | https://console.volcengine.com/ark |
| 通义千问（阿里云百炼） | https://bailian.console.aliyun.com/ |
| Kimi（月之暗面） | https://platform.moonshot.cn/console/api-keys |
| 智谱 GLM | https://open.bigmodel.cn/usercenter/apikeys |
| OpenAI | https://platform.openai.com/api-keys |
| Anthropic Claude | https://console.anthropic.com/settings/keys |

### 关于 Claude

Claude 通过 Anthropic 提供的 OpenAI 兼容层接入。这个兼容层有一个已知限制：

- **函数调用的 `strict` 参数会被忽略**，工具调用 JSON 不保证严格遵循 schema。

对本项目的影响：如果用户选 Claude，Agent 在调用 `check_video_requirements` 时可能在工具参数上出现偏差（例如视频路径拼写错误、`video_scope` 取值不对）。

**建议**：优先使用 DeepSeek、豆包、通义千问、Kimi、智谱、OpenAI 这类原生 OpenAI 兼容平台。Claude 作为可选平台保留，但工具调用稳定性低于上述平台。

### config.json 路径

当前版本 `config.json` 位于项目目录（`D:\AIProjects\agent-learnin\config.json`）。

这意味着：

- 更新项目代码时如果覆盖整个目录，配置会丢失；
- 把项目目录复制给别人时，如果忘记排除 `config.json`，会连带泄露 Key。

未来版本会迁移到用户目录（如 `%USERPROFILE%\.animation-agent\config.json`）。当前版本请自行注意不要提交、不要分享。

---

## 项目结构

```text
agent-learnin/
├── .env                     # 可选，保存 DEEPSEEK_API_KEY（已被 .gitignore 忽略）
├── .gitignore
├── config.json              # 本机运行时配置（已被 .gitignore 忽略）
├── start.bat                # Windows 启动器
├── app.py                   # Gradio 界面 + Agent 定义 + 多平台配置
├── main.py                  # 早期学习入口（历史文件）
├── project.json             # 项目规范配置
├── README.md
├── requirements.txt
├── tools.py                 # 核心业务逻辑 + Agent Tool
├── tools_v01_backup.py      # v0.1 备份（历史文件，不删）
├── tests/                   # 单元测试 + 集成测试（unittest）
└── .venv/
```

`project.json` 是**项目规范**，会被提交到 Git。`config.json` 是**本机运行时配置**，不提交。两者不要混。

---

## 运行测试

```powershell
Set-Location "D:\AIProjects\agent-learnin"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前版本共 196 个测试（单元 + 集成），全部通过。

单独测试某个模块：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_resolve_provider_config -v
```

---

## 已知限制

以下内容当前版本**不能检查**，Agent 不会声称已经检查：

- 画面中的内嵌字幕
- 音频里是否有人物对白
- 音频里是否有背景音乐
- 画面中的角色风格、构图
- 每个镜头的实际数量

报告规则：

- `warning` 是需要复核、检测能力不足或标准未配置的项目，**不是已确认的违规**；
- `info` 是参考信息，**不是不合格**；
- 没有独立字幕轨道**不代表**画面没有内嵌字幕；
- 存在音频流**不代表**存在背景音乐；
- 未检查的项目不会因为“没发现问题”被判定为通过。

---

## 版本历史

| 版本 | 内容 |
|---|---|
| v0.17.x | README 更新，补 requirements.txt |
| v0.16.0 | UI 加多平台下拉框，切换平台写入 config.json |
| v0.15.0 | build_agent 从 config.json 读取 active_provider 的 base_url / model |
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
- 不加入复杂 OCR 或音频分类模型（除非明确规划为下一个阶段）
- 不让 LLM 重新计算确定性检测数据
- 不把 warning 说成 confirmed failure，不把 info 说成 failure
- 不把“没有 subtitle stream”说成“画面绝对没有字幕”
- 不把 audio stream 说成 BGM
- 不在没有实际检查的情况下声称全部通过