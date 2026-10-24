# Reelwright · 影匠

> by [Taoran_Jiang](https://jiangtaoran.xin/) · [GitHub](https://github.com/attentionme)

一个本地 AI Agent，把一份剧本变成一段动态分镜（animatic）。

```
剧本 script.txt
   ↓ LLM 分镜规划
segments/seg_01 ~ seg_03（每段 10–13s、2–3 个镜头）
   ↓ 尾帧接力 + ComfyUI 批量生成
batches/（每段 2 个候选 + 技术质检 + 审片页面）
   ↓ 人工挑片 + 自动拼接
episode_final.mp4
```

Reelwright（影匠）不是一个通用产品，而是一个**可运行的参考实现**：演示如何用 Agent 编排 ComfyUI 做视频生成，并把"分镜规划 → 批量抽卡 → 质量门控 → 人工审片 → 成片拼接"串成一条可复现的流水线。

## 为什么做这个

市面上的 AI 视频工具大多是"一次性生成"，很难控制：

- 一段 10 秒的片子，想要 3 个镜头切换，模型经常理解不了"机位变化"；
- 多段生成，人物脸和场景对不上；
- 抽卡 20 个，人工挑片要逐个打开；
- 挑完还要手动拼接。

Reelwright 尝试解决的是**"从剧本到成片"的工程化流程**，而不是"单次生成质量"。核心思路：

- **LLM 负责规划**：把剧本拆成段，把每段写成 H3 能理解的六段式 prompt，用自然语言描述"画面里有什么"而不是"用什么机位"；
- **Python 负责执行**：调用 ComfyUI API、抽尾帧、技术检测、拼接；
- **人负责审美**：挑哪个视频、节奏好不好，这部分不交给 AI。

## 核心能力

### 1. 剧本 → 多视图分镜

`plan_segments.py` 把剧本拆成 2–5 段，每段 8–14 秒，包含 2–3 个"视图"（镜头切换）。视图切换用自然语言描述：

```
The video starts with a wide view of a small apartment living room at night...
Then the view changes to a close look at 小满's hand pressing a folded cloth...
Then the view changes back to the wide view of the living room...
```

不使用 `[Shot 1]`、`close-up`、`over-the-shoulder` 这类摄影术语——H3 不理解，会把 "over-the-shoulder" 理解成"画面里要有个人挡着"，凭空多出人物。**这是踩过的坑，不是猜测。**

### 2. 尾帧接力

每段生成完，`pipeline.py` 自动抽最后一帧，作为下一段的 `<Picture 3>` 参考图。3 段连起来，角色、场景、灯光保持一致。

```
seg_01 尾帧 → seg_02 参考图 → seg_02 尾帧 → seg_03 参考图 → ...
```

### 3. 批量生成 + 质量门控

`batch_run.py` 对每段跑 2 个候选，自动做：

- **技术检测**：时长异常、无音频流、文件过小、帧率偏离；
- **音频检测**：SEAD 模型判断是否有 BGM；
- **可疑排序**：可疑的视频排在审片页面最前面。

### 4. 审片页面

每次生成完自动生成 `review.html`：

- 每个视频一个播放器，下方显示 seed、耗时、文件大小、时长、帧率；
- 右上角"通过"/"可疑"标记，可疑的排在前面；
- 点"喜欢"/"淘汰"，标记存在浏览器 localStorage，**按集累积**，换集清零；
- 点"导出本集全部标记"，下载 `review_marks.json`。

### 5. 自动拼接

`concat_episode.py` 按 `seg_01 → seg_02 → seg_03` 的顺序 ffmpeg concat，输出 `episode_final.mp4`。

### 6. Agent 接管

Gradio 界面里的 Agent 有 10 个工具：

**只读**：
- `inspect_episode`：扫描当前集状态（哪段已生成、哪段已标记）
- `plan_next_step`：根据状态建议下一步命令
- `summarize_review`：汇总标记情况

**执行**：
- `start_generation(segment, trial=False)`：后台启动生成，不阻塞对话
- `check_generation(task_id)`：查任务状态
- `list_generations`：列最近任务

Agent 的边界很清楚：**能启动、能查状态、能给命令，不能判断画面好不好看、不能自动挑片、不能改脚本代码。**

## 技术栈

- **LLM 编排**：`openai-agents` 0.23.1，支持 DeepSeek / 豆包 / 通义千问 / Kimi / 智谱 / OpenAI / Claude 七个平台
- **UI**：Gradio 6.30
- **视频生成**：ComfyUI + MiniMax H3（Ref2VA 模式）
- **媒体处理**：FFmpeg 9.0
- **音频检测**：SEAD（YamNet）
- **Python 3.14**

## 快速开始

### 前置条件

- Windows + PowerShell
- Python 3.14
- FFmpeg 已加入 PATH
- ComfyUI 桌面版已安装，能通过 `http://127.0.0.1:8188` 访问
- 一张 16GB 显存的 GPU（项目在 RTX 5070 Ti 上验证）

### 安装

```powershell
git clone https://github.com/attentionme/reelwright.git
cd reelwright
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 配置

1. 把 ComfyUI 导出的 API 格式工作流保存为 `workflow_api_2.json`；
2. 写 `workflow_profile_2.json`，把语义角色（prompt、seed、时长）映射到节点 id；
3. 启动 `app.py`，在 UI 里填 API Key、保存。

### 跑一集

```powershell
# 1. 写剧本 script.txt

# 2. LLM 分镜
.\.venv\Scripts\python.exe .\plan_segments.py `
  --script script.txt `
  --ref-characters 小满1_2048.png,桃子1_2048.png `
  --force

# 3. 逐段生成（首次建议用 trial 模式验证）
.\.venv\Scripts\python.exe .\run_episode.py --trial

# 4. 打开 batches/seg01_*/review.html，标记喜欢，导出 review_marks.json

# 5. 正式跑
.\.venv\Scripts\python.exe .\run_episode.py --count 2

# 6. 拼接
.\.venv\Scripts\python.exe .\concat_episode.py
```

或者启动 Agent，直接对话：

```powershell
.\.venv\Scripts\python.exe .\app.py
```

> "帮我跑 seg_01，用 trial 模式"
> "跑完了吗"
> "现在什么状态"

## 工程实践

- **纯函数分离**：所有"决定结论"的逻辑抽成纯函数（`_build_duration_check`、`_resolve_provider_config`、`_provider_options`），196 个单元测试覆盖；
- **结构化输出**：`issue_report` 分 `error / warning / info / pass / at_target / not_applicable / unclassified` 七类，Agent 不能把 warning 说成 failure；
- **多平台配置**：`config.json` 支持 7 个 OpenAI 兼容平台，UI 下拉切换；
- **后台任务管理**：`task_manager.py` 用 `subprocess.Popen` + `tasks/*.json` 状态文件，Agent 启动 20 分钟的任务不阻塞对话；
- **启动前检查**：`start_generation` 先检查 ComfyUI 在线，不在线直接返回错误，不启动注定失败的任务。

## 已知限制

- **视觉质量没有自动检测**。技术检测能抓时长、音频、帧率，但抓不住"画面崩坏、角色不像、有字幕"。这些需要人工审片。
- **生成质量有种子方差**。同一个 seed 和 prompt，不同次生成的质量可能差异很大。批量跑 2 个候选 + 人工挑是当前的工作方式。
- **多视图不是真正的电影分镜**。H3 能理解"画面内容变化"，但不能理解"机位切换、轴线、视线匹配"。所以多视图是保守的"全景 → 局部 → 全景"，不是真正的电影剪辑。
- **13s + 1.5MP 是 16GB 显存的负载边缘**。偶尔会超时，`comfy_adapter.py` 会主动中断卡住的任务。

## 项目结构

```
reelwright/
├── app.py                   # Gradio UI + Agent 定义 + 10 个工具
├── task_manager.py          # 后台任务管理
├── plan_segments.py         # LLM 分镜规划
├── pipeline.py              # 尾帧接力
├── batch_run.py             # 批量生成主脚本
├── comfy_adapter.py         # 工作流适配层
├── quality_check.py         # 技术检测 + SEAD
├── concat_episode.py        # 拼接成片
├── run_episode.py           # 一键跑全流程
├── tools.py                 # 早期视频规范检查工具
├── workflow_api_2.json      # H3 工作流（API 格式）
├── workflow_profile_2.json  # 语义角色映射
├── segments/                # 分镜 prompt
├── tests/                   # 196 个单元测试
└── ...
```

## 版本历史

从 v0.4 到 v0.40，完整 tag 历史。关键节点：

- **v0.4–v0.12**：视频规范检查 Agent（画幅、时长、编码、命名）
- **v0.18**：ComfyUI 适配层（profile 机制）
- **v0.19**：SelfLift H3 工作流
- **v0.29**：SEAD 音频检测
- **v0.36**：多视图 prompt + 13s 分段
- **v0.37**：命名优化 + mtime 排序
- **v0.38**：Agent 只读状态工具
- **v0.39**：Agent 后台执行工具
- **v0.40**：任务目录忽略 + 适配层最终化

## Author

**Taoran_Jiang**

- Portfolio: [jiangtaoran.xin](https://jiangtaoran.xin/)
- GitHub: [@attentionme](https://github.com/attentionme)
- Email: [zmyjtr0418@gmail.com](mailto:zmyjtr0418@gmail.com)

## License

MIT License

Copyright (c) 2026 Taoran_Jiang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.