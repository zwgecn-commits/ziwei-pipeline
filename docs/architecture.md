# 架构说明

## 设计总则

**确定性数据永远由代码产出，LLM 只做语言组织与判词**。这是整套管线的立身之本——
凡是"模型心算"过的宫位/四化/岁段，都被证明会批量漂移（三单三错、14/50 处换算错），
因此全部改为：引擎输出权威表 → 注入 prompt → 闸门代码比对回引擎。

## 链路

```
生辰(y/m/d/h/性别)
   │
   ▼
① 排盘 ziwei-chart（JS 引擎 · 金标准对齐）
   │  palaces / sihua / daxian / daxianSihua / liunianSihua / dieGong / flyingChains
   ▼
② 规则判定 rules_engine.py
   │  32 条确定性规则 → judgements + 数字指纹（命宫地支+五行局+四化星 → md5）
   │  P0 硬错率口径：四类硬错 <2% 才允许上线
   ▼
③ prompt 构造 prompt_builder.py
   │  盘面事实表（全星曜） + 大限/流年权威表（引擎照抄，禁推算）
   │  + 规则判定摘要 + 外部知识库（可选挂载）
   ▼
④ LLM 分析（留白：Ollama / OpenAI 兼容 API / 自研模型均可）
   │  输出结构化判词（sections），禁止其生成任何宫位/岁段数据
   ▼
⑤ 成品对账闸门 reconcile_gate.py
   │  正则抽「岁段→宫名」 vs 引擎 daxian 全等比对（逐条，防 4对1错蒙混）
   │  未提及放行（防误杀）；失败 → repair() 程序化纠错 → 重跑闸门
   ▼
⑥ 六件套 report_schema v1 + report_render.py
     meta / chart_facts / rule_verdict / sections / scores / gate
     → JSON（数据层）+ HTML（紫金主题展示层）
```

## 质量门细节

| 层 | 工具 | 查什么 | 失败处理 |
|---|---|---|---|
| 排盘后 | `_chart_audit` | 四化完整性 wx02 / 大限四化 dg01 / 流年四化 dg03 / 大限12宫 sk01 | 422 拒单（不降级） |
| 生成后 | `l2_validator` | 星曜搬宫 / 四化错位 / 宫位错置（白名单比对） | 违例拦退重跑 |
| 成品 | `reconcile_gate` | 岁段→宫位序列全等 + 流年年份归属大限区间 | repair 纠错或标记 |

## 三个反复踩过的坑（实现时务必遵守）

1. **流年命宫 = 本命盘 diZhi==流年地支的宫**（绝对映射），不是大限偏移；流年四化字段的 key=大限宫名。
2. **大限天干/四化一律从引擎 `daxianSihua` 抄**，禁止按"宫干+四化表"推理链让模型心算（五虎遁手推必错）。
3. **闸门必须确定性代码**，禁止 LLM 判对错（同源模型会自洽幻觉，语法检查必放行）。
