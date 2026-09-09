#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_daxian_map_qa.py — 大限换算训练题生成器（开源版）
程序化零 LLM：从排盘引擎 daxianPalaceMap（权威映射）出题，杜绝手写出题幻觉。
system 段注入权威锚（逆排规则+12限命宫序列+目标大限完整映射），训练目标="照抄/调用权威"。
用法: python3 gen_daxian_map_qa.py --count 50 [--seed 42] [--out daxian_map_qa.jsonl]
"""
import argparse, json, random, subprocess, sys, os

ENGINE = os.environ.get("ZIWEI_ENGINE", os.path.expanduser("~/ziwei-chart/ziwei_chart.js"))
SHORT = ["命", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "官禄", "田宅", "福德", "父母"]
ANCHOR = (
    "【权威锚·大限宫位映射铁律】大限十二宫与本命十二宫同序逆排：大限兄弟=大限命宫地支-1的本命宫，"
    "夫妻=地支-2，依次至父母=地支-11。命宫↔迁移/兄弟↔仆役/夫妻↔官禄/子女↔田宅/财帛↔福德/疾厄↔父母为对宫（地支相冲）。"
    "所有大限换算题答案照抄下方映射表，禁止心算。"
)


def run_engine(y, mo, d, h, g):
    p = subprocess.run(["node", ENGINE, str(y), str(mo), str(d), str(h), g],
                       capture_output=True, timeout=60)
    if p.returncode != 0:
        return None
    return json.loads(p.stdout)


def qa_for_chart(chart):
    dpm = chart.get("daxianPalaceMap") or []
    if not dpm:
        return []
    seq = "、".join(g["mingPalace"] for g in dpm)
    out = []
    for g in dpm:
        k = g["daxianIndex"]
        rng = g["range"]
        mp = {m["daxian"]: m for m in g["map"]}
        # 目标大限完整映射（system 锚）
        full = "；".join(f"大限{m['daxian']}={m['benming']}({m['zhi']})" for m in g["map"])
        sys_anchor = (ANCHOR + f" 本盘12大限命宫序列：{seq}。"
                      f" 第{k}大限({rng[0]}-{rng[1]}岁)完整映射：{full}。")
        cases = [
            # ① 正向单宫 ×2（随机挑两宫）
            # ② 反查 ×2
            # ③ 命宫落点 ×1
            # ④ 对宫 ×1
            # ⑤ 完整映射复述 ×1
        ]
        idxs = random.sample(range(12), 2)
        for i in idxs:
            m = g["map"][i]
            cases.append((
                f"第{k}大限（{rng[0]}-{rng[1]}岁）的{m['daxian']}宫，对应本命哪个宫？",
                f"本命{m['benming']}（地支{m['zhi']}）"))
        for i in idxs:
            m = g["map"][i]
            cases.append((
                f"本命{m['benming']}宫在第{k}大限里是什么宫？",
                f"大限{m['daxian']}宫"))
        cases.append((
            f"第{k}大限的命宫落在本命哪个宫？",
            f"本命{g['mingPalace']}（地支{g['map'][0]['zhi']}）"))
        cases.append((
            f"第{k}大限命宫的对宫（即大限迁移宫）对应本命哪个宫？",
            f"本命{mp['迁移']['benming']}（地支{mp['迁移']['zhi']}）"))
        cases.append((
            f"请写出第{k}大限十二宫与本命宫的完整映射。",
            full))
        cases.append((
            "大限十二宫按什么方向、什么顺序排列？",
            "与本命十二宫同序逆排（地支递减）：大限兄弟=大限命宫地支-1，夫妻=地支-2，依次到父母=地支-11。"))
        for u, a in cases:
            out.append({"messages": [
                {"role": "system", "content": sys_anchor},
                {"role": "user", "content": u},
                {"role": "assistant", "content": a},
            ]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="daxian_map_qa.jsonl")
    ap.add_argument("--check", type=int, default=0, help="只验前N盘输出到stdout(调试)")
    args = ap.parse_args()
    random.seed(args.seed)
    # 通用示例盘打底（金标准验收可用固定盘，此处仅示例）
    births = [(1990, 7, 14, 12, "male"), (1990, 12, 24, 1, "female")]
    while len(births) < args.count + 3:
        y = random.randint(1950, 2010)
        mo = random.randint(1, 12)
        d = random.randint(1, 28)
        h = random.randint(0, 23)
        g = random.choice(["male", "female"])
        births.append((y, mo, d, h, g))
    total = 0
    charts = 0
    if args.check:
        births = births[:args.check]
        out_f = sys.stdout
    else:
        out_f = open(args.out, "w", encoding="utf-8")
    for (y, mo, d, h, g) in births:
        c = run_engine(y, mo, d, h, g)
        if not c or not c.get("success"):
            continue
        charts += 1
        qas = qa_for_chart(c)
        for q in qas:
            out_f.write(json.dumps(q, ensure_ascii=False) + "\n")
            total += 1
    if not args.check:
        out_f.close()
        print(f"✅ {charts} 盘 → {total} 题 → {args.out}")
    else:
        print(f"✅ 抽样 {charts} 盘 → {total} 题（未写文件）", file=sys.stderr)


if __name__ == "__main__":
    main()
