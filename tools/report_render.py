#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_render.py v2 — 紫微阁六件套 HTML 渲染器
适配 report_schema v1 契约结构（palaces/daxian 字符串数组、sections verdict+溯源、
scores 确定性公式、gate 完整字段）——紫金主题。
用法：python3 report_render.py <report.json> [输出.html]
"""
import json, os, sys, re

CSS = """
:root { --purple:#6B4FA0; --gold:#D4AF37; --bg:#FAF7F2; --ink:#2B2436; --muted:#8A7F99; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:"Noto Serif SC","Songti SC",serif; background:var(--bg); color:var(--ink); line-height:1.7; }
.wrap { max-width:920px; margin:0 auto; padding:20px 24px 60px; }
.hero { background:linear-gradient(135deg,#4A3570,#6B4FA0); color:#fff; padding:28px 24px; border-radius:12px; margin-bottom:18px; }
.hero h1 { font-size:1.5em; }
.hero .meta { color:#E8D9B0; font-size:.85em; margin-top:8px; }
h2 { color:var(--purple); border-left:5px solid var(--gold); padding-left:12px; margin:26px 0 12px; font-size:1.15em; }
table { border-collapse:collapse; width:100%; margin:10px 0; font-size:.88em; }
th { background:var(--purple); color:#fff; padding:6px 9px; text-align:left; }
td { border:1px solid #E4DCCB; padding:6px 9px; }
tr:nth-child(even) td { background:#F4EFE6; }
.mapcol { font-size:.78em; color:#5A4E72; line-height:1.5; }
.score-card { display:flex; gap:10px; flex-wrap:wrap; margin:10px 0; }
.score { border:1px solid #D8CCE8; border-radius:10px; padding:8px 14px; background:#fff; }
.score b { color:var(--purple); }
.ethics { background:#FDF6E3; border-left:5px solid var(--gold); padding:10px 14px; font-size:.85em; color:#7A6A2E; margin-top:18px; }
"""


def _parse_palace(line):
    """'本命仆役: 主[] 辅[左辅 地劫]' → (宫名, 主星, 辅星)"""
    m = re.match(r"^本命([^:：]+)[:：]\s*主\[(.*?)\]\s*辅\[(.*?)\]", line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return line, "", ""


def render(report):
    r = json.load(open(report, encoding="utf-8")) if isinstance(report, str) else report
    meta = r.get("meta", {})
    facts = r.get("chart_facts", {})
    verdict = r.get("rule_verdict", {})
    scores = r.get("scores", {})
    sections = r.get("sections", [])
    gate = r.get("gate", {})

    # 1. 十二宫总览（契约版字符串数组）
    palaces = facts.get("palaces", [])
    rows = ""
    for line in palaces:
        name, maj, mnr = _parse_palace(line)
        rows += f"<tr><td>{name}</td><td>{maj or '—'}</td><td>{mnr or '—'}</td></tr>"

    # 2. 生年四化（契约版 sihua_birth）
    sb = facts.get("sihua_birth", {})
    sb_rows = "".join(f"<tr><td>{k}</td><td>{v or '—'}</td></tr>" for k, v in
                      [("禄", sb.get("禄", "")), ("权", sb.get("权", "")),
                       ("科", sb.get("科", "")), ("忌", sb.get("忌", ""))])

    # 3. 大限总览（契约版字符串数组 + v2.6 宫位映射列·读引擎 daxianPalaceMap 权威映射）
    dx_rows = ""
    dpm = facts.get("daxianPalaceMap", []) or []
    for line in facts.get("daxian", []):
        parts = [p.strip() for p in line.split("·")]
        while len(parts) < 3:
            parts.append("")
        map_txt = "—"
        for g in dpm:
            if not isinstance(g, dict):
                continue
            gr = g.get("range") or [0, 0]
            if len(gr) == 2 and f"{gr[0]}-{gr[1]}" in parts[0]:
                _mm = [m for m in (g.get("map") or []) if isinstance(m, dict)]
                map_txt = "、".join(f"{m.get('daxian','')}={m.get('benming','')}({m.get('zhi','')})" for m in _mm)
                break
        dx_rows += f"<tr><td>{parts[0]}</td><td>{parts[1] or '—'}</td><td>{parts[2] or '—'}</td><td class='mapcol'>{map_txt}</td></tr>"

    # 4. 断语分节（契约版 verdict + technique_trace）
    sec_html = ""
    for s in sections:
        sec_html += f"<h3>{s.get('title', '')}</h3><p>{s.get('verdict', s.get('text', ''))}</p>"
        tr = s.get("technique_trace") or []
        if tr:
            sec_html += f"<div style='font-size:.75em;color:var(--muted)'>🔍 技法溯源: {'；'.join(tr)}</div>"

    # 5. 评分（确定性公式·LLM 零参与）
    cards = ""
    if scores.get("rules_engine_signal"):
        cards += f"<div class='score'><b>规则引擎</b>：{scores['rules_engine_signal']}</div>"
    if scores.get("verdict") and scores["verdict"] != "—":
        cards += f"<div class='score'><b>综合</b>：{scores['verdict']}</div>"
    for f in scores.get("formula") or []:
        cards += f"<div class='score'>{f}</div>"

    # 6. 质量门（契约版完整字段）
    gate_html = f"L2 {gate.get('l2_lower','')} ｜ reconcile {gate.get('reconcile','')} ｜ 硬错率 {gate.get('hard_error_rate','')} ｜ 上线闸 {gate.get('upper_gate','')}"

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>紫微阁 · 命盘分析报告</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="hero"><h1>紫微阁 · 紫微斗数命盘分析报告</h1>
<div class="meta">指纹：{meta.get('fingerprint','')} ｜ 引擎：{meta.get('engine','')} ｜ 五行局：{meta.get('wuxing_ju','')} ｜ 性别：{meta.get('gender','')} ｜ 脱敏：{meta.get('deidentified','')}</div>
<div class="meta">命宫：{facts.get('ming','')} ｜ 身宫：{facts.get('shen','')}</div>
<div class="meta">质量门：{gate_html}</div></div>
<h2>① 十二宫星曜总览</h2><table><tr><th>宫位</th><th>主星</th><th>辅星</th></tr>{rows}</table>
<h2>② 生年四化</h2><table><tr><th>化</th><th>星曜@宫位</th></tr>{sb_rows}</table>
<h2>③ 大限总览</h2><table><tr><th>岁段</th><th>宫位</th><th>大限四化</th><th>宫位映射(大限=本命·地支)</th></tr>{dx_rows}</table>
<h2>④ 分析断语</h2>{sec_html}
<h2>⑤ 综合评分</h2><div class="score-card">{cards or '—'}</div>
<div class="ethics">⚠ 免责声明：本报告基于确定性排盘引擎数据，仅供研究、学习与娱乐参考，不构成任何现实决策依据。命理是"倾向"不是"宿命"——不引动不发生，事在人为。</div>
</div></body></html>"""
    return html


def main():
    if len(sys.argv) < 2:
        print("用法: report_render.py <report.json> [输出.html]")
        return 1
    out = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1].replace(".json", ".html")
    open(out, "w", encoding="utf-8").write(render(sys.argv[1]))
    print(f"✅ 六件套渲染: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
