#!/usr/bin/env python3
# ============================================================
# prompt_builder.py — 紫微 prompt 构建器（开源版）
# 职责：ChartInfo + 规则判定 → 结构化 prompt（盘面事实表/动态权威表/规则判定）
# 输入：排盘引擎 JSON（见 ziwei-chart 仓库）
# 输出：技法注入 prompt（含规则判定、数字指纹、盘面事实表）
# 设计：查表类知识全部规则化注入，模型只读象不重算
# 知识层：不内置任何门派技法内容——通过 ZIWEI_KNOWLEDGE 环境变量
#         指向自己的知识库文件（UTF-8 纯文本/Markdown）后自动注入
# ============================================================

import json, sys, os, subprocess
from rules_engine import evaluate_chart

# 排盘引擎路径（ziwei-chart 仓库：https://github.com/zwgecn-commits/ziwei-chart）
ENGINE = os.environ.get(
    "ZIWEI_ENGINE",
    os.path.expanduser("~/ziwei-chart/ziwei_chart.js"))


# ---------- 知识注入（使用者自备；缺省给中性工程约束） ----------
def load_knowledge():
    """读取外部知识库文本（若配置）。不内置任何特定流派内容。"""
    kf = os.environ.get("ZIWEI_KNOWLEDGE", "")
    if kf and os.path.isfile(kf):
        with open(kf, encoding="utf-8") as f:
            return f.read()
    return (
        "【通用约束】\n"
        "1. 输出中文。结构数据（宫位/星曜/四化/岁段）一律以盘面事实表与权威表为准，"
        "禁止自行推算或编造。\n"
        "2. 断语需可回溯：能用盘面星曜/宫位/四化佐证的才写；单象标注“待验证”。\n"
        "3. 可注入自有知识库以增强断语体系（环境变量 ZIWEI_KNOWLEDGE）。\n"
    )

def run_engine(birth):
    cmd = ["node", ENGINE, str(birth["year"]), str(birth["month"]),
           str(birth["day"]), str(birth["hour"]),
           "male" if str(birth["gender"]) in ("男","male") else "female"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                       cwd=os.path.dirname(ENGINE))
    return json.loads(r.stdout)

def build_fact_table(chart):
    """盘面事实表（模型只消费不重算）"""
    lines = []
    palaces = chart.get("palaces", {})
    for pn in ["命宫","兄弟","夫妻","子女","财帛","疾厄","迁移","仆役","官禄","田宅","福德","父母"]:
        p = palaces.get(pn, {})
        tg = p.get("tianGan","?")
        dz = p.get("diZhi","?")
        majors = [s.get("name","") if isinstance(s,dict) else s for s in p.get("major",[])]
        minors = [s.get("name","") if isinstance(s,dict) else s for s in p.get("minor",[])]
        m_str = ",".join(majors) if majors else "空"
        n_str = ",".join(minors) if minors else ""
        lines.append(f"{pn}({tg}{dz}): 主[{m_str}]{(' 辅['+n_str+']') if n_str else ''}")
    return "\n".join(lines)

def build_dynamic_abstract(chart, birth_year=None, current_year=2026):
    """动态层权威摘要（六方定案）：大限序列/大限四化/当前大限/流年四化
    模型只照抄不重算——结构数据禁止生成，起限/顺逆一律取引擎 range"""
    lines = []
    daxian = chart.get("daxian", [])
    dxs = chart.get("daxianSihua", [])
    palaces = chart.get("palaces", {})

    lines.append("【大限权威表·照抄勿重算】(起限岁数/顺逆以引擎为准)")
    for dx in daxian:
        rng = dx.get("range", ["?", "?"])
        pn = dx.get("palace", "?")
        p = palaces.get(pn, {})
        gg = f"{p.get('tianGan','?')}{p.get('diZhi','?')}"
        sh = ""
        for ds in dxs:
            if ds.get("palace") == pn:
                tg = ds.get("tianGan", "?")
                s = ds.get("sihua", {})
                parts = [f"{s[k]} {k}" for k in ("禄", "权", "科", "忌") if k in s]
                sh = f"{tg}干四化: {'/'.join(parts) if parts else '无'}"
                break
        lines.append(f"{rng[0]}-{rng[1]}岁·{pn}({gg})·{sh}")

    if birth_year:
        age = current_year - birth_year + 1  # 虚岁
        cur = next((dx for dx in daxian if dx["range"][0] <= age <= dx["range"][1]), None)
        if cur:
            lines.append(f"当前大限: {cur['range'][0]}-{cur['range'][1]}岁·{cur['palace']}（{current_year}年命主{age}虚岁）")

    # 流年四化（当前十年，按年排序）——liunianSihua key=大限宫名，条目=该大限内逐年流年四化
    GAN = "甲乙丙丁戊己庚辛壬癸"; ZHI = "子丑寅卯辰巳午未申酉戌亥"
    lls = chart.get("liunianSihua", {})
    items = []
    for pn, arr in lls.items():
        for it in arr:
            if isinstance(it, dict) and current_year <= it.get("year", 0) <= current_year + 9:
                y = it["year"]
                gz = GAN[(y - 4) % 10] + ZHI[(y - 4) % 12]  # 干支年
                # 流年命宫落点 = 本命盘中地支==流年地支的宫位
                land = next((pp for pp, ppd in palaces.items() if ppd.get("diZhi") == ZHI[(y - 4) % 12]), "?")
                items.append((y, gz, it.get("stem", "?"), pn, land, it.get("sihua", {})))
    if items:
        lines.append("【流年四化·当前十年】(逐年在某大限内；流年命宫落点按地支查本命宫位)")
        for y, gz, stem, dxn, land, s in sorted(items):
            parts = [f"{s[k]} {k}" for k in ("禄", "权", "科", "忌") if k in s]
            lines.append(f"{y}{gz}年·{dxn}大限·流年命宫落{land}·{stem}干四化: {'/'.join(parts) if parts else '无'}")
    else:
        lines.append("【流年四化】当前十年无数据")
    return "\n".join(lines)


def build_prompt(chart, question="请分析此命盘的整体运势"):
    """构建 v7 注入 prompt"""
    # 1. 规则判定 + 指纹
    rules = evaluate_chart(chart)
    fp = rules.get("fingerprint","?")
    fp_hash = rules.get("fingerprint_hash","")
    p0 = rules.get("p0_hit",0); p0t = rules.get("p0_total",0)
    p1 = rules.get("p1_hit",0)

    # 2. 盘面事实表
    fact_table = build_fact_table(chart)

    # 3. 四化摘要
    sihua = chart.get("sihua", {})
    sihua_str = " | ".join(
        f"{tag}:{s.get('star','?')}@{s.get('palace','?')}"
        for tag, s in sihua.items() if isinstance(s, dict))

    # 4. 大限/流年权威摘要（动态层全量，禁止模型重算）
    from reconcile_gate import _birth_year
    birth_year = _birth_year(chart)
    dynamic = build_dynamic_abstract(chart, birth_year)

    # 5. 组装 prompt
    prompt = f"""{load_knowledge()}

【数字指纹·必须复述】{fp} (hash={fp_hash})
【规则判定】P0命中{p0}/{p0t}·P1参考{p1}

【盘面事实表·只认此表不认记忆】
{fact_table}

【四化摘要】
{sihua_str}

【大限流年权威表·照抄勿重算】
{dynamic}

【用户问题】
{question}

【要求】
1. 先复述数字指纹，再开始分析（chain-of-verification）
2. 星曜/宫位/四化只认事实表，不得凭记忆搬动
3. 结论需≥2项独立技法支撑，单象标注"待验证"
4. 按 SKILL v7 技法体系分析，禁用已剔除外体系
"""
    return prompt

if __name__ == "__main__":
    if len(sys.argv) > 1:
        birth = json.loads(sys.argv[1])
    else:
        birth = {"year": 1990, "month": 7, "day": 14, "hour": 12, "gender": "女"}
    chart = run_engine(birth)
    q = sys.argv[2] if len(sys.argv) > 2 else "请分析此命盘的整体运势"
    print(build_prompt(chart, q))
