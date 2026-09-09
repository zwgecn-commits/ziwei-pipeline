# 紫微 AI 分析管线 · ziwei-pipeline

> 排盘引擎见姊妹仓库 [zwgecn-commits/ziwei-chart](https://github.com/zwgecn-commits/ziwei-chart)（npm `@zwge/ziwei-chart`）。

一套**确定性优先**的紫微斗数 AI 分析管线工程参考实现：排盘 → 规则判定 → 事实表注入 → LLM 分析 → 成品对账闸门 → 结构化报告契约 → HTML 渲染。

核心理念（都是踩坑踩出来的）：

1. **结构数据禁止 LLM 生成**——宫位/星曜/四化/岁段一律由排盘引擎输出权威表注入，模型只读照抄，不心算。
2. **成品对账用确定性代码**——正则抽取"岁段→宫名"序列与引擎 JSON 全等比对，不用 LLM 自评对错。
3. **质量闸门兜底**——星曜/四化/宫位三元绑定白名单校验（L2）+ 指纹复述。
4. **报告契约化**——六件套 JSON Schema（report/v1）+ 模板渲染，LLM 只填判词。
5. **知识层外置**——本仓库不内置任何门派技法/知识库；通过环境变量挂载自己的知识体系（见下）。

## 文档

- [架构说明](docs/architecture.md) — 链路细节、质量门、踩坑铁律
- [模型训练配方](docs/training-recipe.md) — 程序化 QA 数据构成 + QLoRA → GGUF + 升级验证
- [数据回流协议](docs/telemetry.md) — opt-in 遥测/报告反馈/对账众包三通道（零遥测默认·隐私合规）

## 仓库结构

```
ziwei-pipeline/
├── server/
│   └── pipeline_demo.py      # 参考实现：全链演示（排盘→规则→L2→闸门→六件套→渲染）
├── tools/
│   ├── rules_engine.py       # 32 条确定性规则（P0 硬 18 条 + P1 软 14 条）+ 数字指纹
│   ├── reconcile_gate.py     # 成品对账闸门：岁段→宫位序列 vs 引擎全等比对
│   ├── l2_validator.py       # L2 白名单校验：星曜/四化/宫位绑定
│   ├── prompt_builder.py     # prompt 构造：事实表 + 动态权威表 + 规则判定（知识外置）
│   ├── report_schema.json    # 六件套呈现数据契约 report/v1
│   ├── report_schema_check.py
│   ├── report_render.py      # 六件套 HTML 渲染器（紫金主题·可选反馈按钮）
│   ├── gen_daxian_map_qa.py  # 训练数据工厂：大限换算 QA 程序化生成（零 LLM）
│   └── telemetry.py          # opt-in 数据回流（运行遥测+报告反馈·零遥测默认）
└── frontend/
    └── index.html            # 对话前端（单文件：输入生辰+问题 → 轮询 async API）
```

## 快速开始

前置：Node.js ≥16 + 排盘引擎

```bash
# 1. 取排盘引擎（ziwei-chart 仓库）
git clone https://github.com/zwgecn-commits/ziwei-chart ~/ziwei-chart
cd ~/ziwei-chart && npm install

# 2. 跑通参考实现全链（默认示例盘 1990-07-14 午时 女）
cd ziwei-pipeline/server
python3 pipeline_demo.py

# 3. 自定生辰
python3 pipeline_demo.py '{"year":1990,"month":7,"day":14,"hour":12,"gender":"女"}'
```

预期输出：六步 ✅，HTML 落在 `/tmp/chain_report.html`。

`pipeline_demo.py` 不调推理模型（LLM 环节是留白接口）。接入推理的推荐路径：

```bash
# 构造注入 prompt（排盘引擎 JSON + 规则判定 + 外部知识库）
python3 tools/prompt_builder.py '{"year":1990,"month":7,"day":14,"hour":12,"gender":"女"}' "请分析整体运势"
```

把输出发给任意 LLM（Ollama / OpenAI 兼容 API）→ 成品用 `reconcile_gate.verify(chart, text)` 对账 → 通过后组装六件套 JSON → `report_render` 出 HTML。

## 挂载自己的知识库

本仓库刻意**不内置任何流派技法文本**（工程与知识分离，避免版权/师门争议）。有自研或授权知识体系的用户：

```bash
export ZIWEI_KNOWLEDGE=/path/to/your/knowledge.md   # UTF-8 纯文本/Markdown
python3 server/pipeline_demo.py
```

`prompt_builder.load_knowledge()` 会在 prompt 顶部注入该文件全文；未配置时只给中性工程约束。

## 确定性闸门用法（LLM 输出必须过）

```python
from reconcile_gate import verify, repair
rep = verify(engine_chart_json, llm_final_text)   # {'pass': bool, 'mismatches': [...]}
if not rep['pass']:
    fixed = repair(llm_final_text, engine_chart_json)  # 程序化纠错回引擎权威段
```

L2 校验（星曜搬宫/四化错位/宫位错置）：

```bash
python3 tools/l2_validator.py chart.json answer.txt --strict
```

## 免责声明

- 本仓库为**工程参考实现**：排盘数据与管线架构可自由复用，但**不含**任何门派的命理知识体系与断语规则——分析能力完全取决于你挂载的知识层与模型。
- 紫微斗数为传统文化参考体系，输出仅供文化研究与娱乐参考，不构成医疗/法律/投资等专业建议。
- 使用排盘数据服务时请遵守当地法律法规，注意个人信息保护（生辰属敏感个人信息）。

## License

MIT — 与 `ziwei-chart` 引擎一致。
