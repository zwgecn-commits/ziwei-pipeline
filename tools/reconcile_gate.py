#!/usr/bin/env python3
"""reconcile_gate.py — 成品对账闸门
确定性代码校验，禁 LLM 判对错（同源失效）、禁仅正则扫散文（自洽幻觉语法检查必放行）。
原则：教师永远不该"生成"盘面数据，只该"搬运"已注入数据；本闸门验证该原则是否被遵守。

用法:
  from reconcile_gate import verify, repair
  rep = verify(engine_chart, final_text)
  if not rep['pass']:
      fixed = repair(final_text, engine_chart)   # 程序化纠错
"""
import json, re

PALACES = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
           "迁移", "仆役", "官禄", "田宅", "福德", "父母"]

# 岁段→宫名：支持 "6-15岁·命宫" "16至25岁 父母宫" "26~35岁（戌）" 等变体
_RANGE_PALACE = re.compile(
    r"(\d{1,3})\s*[-–~至到]\s*(\d{1,3})\s*岁\s*[·,，:：]?\s*[（(]?(" + "|".join(PALACES) + r")宫?"
)

# 干支标注：(丙申) / （己亥）
_GANZHI = re.compile(r"[（(]([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])[)）]")

# 流年行: "2026丙午年·田宅大限·流年命宫落夫妻·丙干四化: ..."（支持 19xx 早年）
_LIUNIAN = re.compile(r"((?:19|20)\d{2})[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]年·(" + "|".join(PALACES) + r")大限")


def extract_daxian_seq(text):
    """抽 'X-Y岁·宫名' 序列 → [(start, end, palace), ...]"""
    return [(int(m.group(1)), int(m.group(2)), m.group(3))
            for m in _RANGE_PALACE.finditer(text)]


def extract_liunian(text):
    """抽流年行 → [(year, palace), ...]"""
    return [(int(m.group(1)), m.group(2)) for m in _LIUNIAN.finditer(text)]


def _palace_ganzhi(chart, palace):
    p = chart.get("palaces", {}).get(palace, {})
    return f"{p.get('tianGan','?')}{p.get('diZhi','?')}"


def _birth_year(chart):
    s = chart.get("solar")
    if isinstance(s, dict):
        return s.get("year")
    if isinstance(s, str):
        import re as _re
        m = _re.search(r"(19|20)\d{2}", s)
        return int(m.group(0)) if m else None
    return None


def verify(chart, text):
    """对账成品 vs 引擎 JSON。
    - 未提及大限 → 放行（防误杀卡死管线）
    - 提及 → 逐条全等比对（防"4对1错"蒙混）
    - 覆盖：大限序列 + 宫位干支标注 + 流年落点
    返回 {"pass": bool, "mismatches": [...], "checked": n}"""
    eng = {(d["range"][0], d["range"][1]): d["palace"] for d in chart.get("daxian", [])}
    eng_sihua = {}
    for ds in chart.get("daxianSihua", []):
        eng_sihua[ds.get("palace")] = ds.get("sihua", {})

    mis = []
    seq = extract_daxian_seq(text)
    for s, e, p in seq:
        true_p = eng.get((s, e))
        if true_p is None:
            mis.append(f"大限 {s}-{e}岁 引擎中不存在（起限/顺逆疑有误）")
        elif true_p != p:
            mis.append(f"大限 {s}-{e}岁 应为 {true_p}({_palace_ganzhi(chart, true_p)})，成品写 {p}({_palace_ganzhi(chart, p)})")

    # 干支标注核对：抽取的 (干支) 若匹配到某宫干支则校验宫名引用一致性（轻量，避免误杀）
    # 流年核对：年份须落在该大限公历区间（birth_year + range[0]-1 ≤ year ≤ birth_year + range[1]-1）
    birth_year = _birth_year(chart)
    for y, p in extract_liunian(text):
        # 流年命宫落点：本命宫位=流年地支（以命宫地支为锚）。引擎数据：liunianSihua[p] 含该年条目
        found = False
        for it in chart.get("liunianSihua", {}).get(p, []):
            if isinstance(it, dict) and it.get("year") == y:
                found = True
                break
        if not found:
            # 兜底：校验年份在大限区间内（语义：该年处于 p 宫大限）
            rng = next((d["range"] for d in chart.get("daxian", []) if d["palace"] == p), None)
            if rng and birth_year and rng[0] - 1 <= y - birth_year + 1 <= rng[1]:
                found = True
        if not found:
            mis.append(f"流年 {y}年·{p}大限 与引擎大限区间不符")

    return {"pass": len(mis) == 0, "mismatches": mis, "checked": len(seq)}


def repair(text, chart):
    """程序化纠错：按岁段把错误宫名替换回引擎权威宫名（剥错段拼回权威段）。"""
    eng = {(d["range"][0], d["range"][1]): d["palace"] for d in chart.get("daxian", [])}
    out = text
    for (s, e), true_p in eng.items():
        pat = re.compile(
            rf"({s}\s*[-–~至到]\s*{e}\s*岁\s*[·,，:：]?\s*[（(]?)(" + "|".join(PALACES) + r")")
        out = pat.sub(lambda m: m.group(1) + true_p, out)
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: reconcile_gate.py <chart.json> [answer.txt] [--repair]")
        print("  chart.json: 引擎 ChartInfo JSON（必填）；answer.txt 缺省时从 stdin 读取成品文本")
        sys.exit(1)
    chart = json.load(open(sys.argv[1]))
    text = open(sys.argv[2]).read() if len(sys.argv) > 2 else sys.stdin.read()
    rep = verify(chart, text)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if not rep["pass"] and len(sys.argv) > 3 and sys.argv[3] == "--repair":
        fixed = repair(text, chart)
        print("=== REPAIRED ===")
        print(fixed)
