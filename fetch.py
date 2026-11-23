"""事故が集まる地点：警察庁「交通事故統計情報のオープンデータ」本票から、
同じ場所（約50m四方）に事故が集中している地点を数える。"""
import datetime as dt
import io
from collections import defaultdict

from lib import oc

BASE = "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/"
YEARS = 3          # 直近何年分を合算するか
GRID = 0.0005      # 緯度経度の丸め幅（約50m）


def find_years():
    found = []
    for y in range(dt.date.today().year, 2018, -1):
        page = BASE + "%d/opendata_%d.html" % (y, y)
        try:
            html = oc.decode(oc.get(page, retries=1))
        except oc.DataError:
            continue
        hon = oc.links(page, r"honhyo_%d\.csv$" % y, html)
        if hon:
            found.append({"year": y, "page": page, "honhyo": hon[0]})
        if len(found) >= YEARS:
            break
    oc.check(found, "本票CSVが見つかりません")
    return found


KOUDO = BASE + "koudohyou/"
PED = {"61"}                 # 31_当事者種別：61 歩行者
OLD = {"65", "75"}           # 30_年齢：65 65～74歳、75 75歳以上
NIGHT = {"21", "22", "23"}   # 14_昼夜：21 夜－暮、22 夜－夜、23 夜－明


def code_csv(name):
    """警察庁の各種コード表CSV（『コード,区分,備考』の表）→ {コード: 区分}"""
    import csv as _csv
    rows = list(_csv.reader(io.StringIO(oc.decode(oc.get(KOUDO + name)))))
    i = next(i for i, r in enumerate(rows) if r and r[0].strip() == "コード")
    return {r[0].strip().lstrip("0") or "0": r[1].strip() for r in rows[i + 1:] if r and r[0].strip().isdigit()}


def police_prefs():
    """警察の都道府県コード → 正式な都道府県名（北海道の方面はまとめて北海道）"""
    d = code_csv("2_koudohyou_todouhukenkoudo.csv")
    oc.check(len(d) >= 51, "都道府県コード表の件数が想定外です(%d)" % len(d))
    out = {}
    for k, v in d.items():
        name = "北海道" if v.startswith("北海道") else next((p for p in oc.PREF if p.startswith(v)), "")
        oc.check(name, "都道府県名を対応づけられません: %s" % v)
        out[k] = name
    return out


def city_names():
    """総務省の全国地方公共団体コード → {5桁: 市区町村名}。取れなければ空（地点名は都道府県のみになる）。"""
    import openpyxl
    page = "https://www.soumu.go.jp/denshijiti/code.html"
    try:
        for u in oc.links(page, r"\.xlsx?$"):
            wb = openpyxl.load_workbook(io.BytesIO(oc.get(u)), read_only=True, data_only=True)
            names = {}
            for r in (row for ws in wb.worksheets for row in ws.iter_rows(values_only=True)):
                if r and r[0] and len(str(r[0]).strip()) == 6 and str(r[0]).strip().isdigit() and len(r) > 2 and r[2]:
                    names[str(r[0]).strip()[:5]] = str(r[2]).strip()
            if len(names) > 1500:
                return names
    except Exception as e:  # noqa
        oc.log("市区町村名の取得に失敗（都道府県名のみで続行）", e)
    return {}


def dms(v, deg_digits):
    """'431412959' → 43 + 14/60 + 12.959/3600"""
    s = str(v).strip()
    if not s.isdigit():
        return None
    s = s.zfill(deg_digits + 7)
    d, m, sec = int(s[:deg_digits]), int(s[deg_digits:deg_digits + 2]), int(s[deg_digits + 2:]) / 1000
    if m >= 60 or sec >= 60:
        return None
    return d + m / 60 + sec / 3600


def run():
    years = find_years()
    oc.log("years", [y["year"] for y in years])
    prefcb = police_prefs()
    ped_codes, old_codes, night_codes = PED, OLD, NIGHT
    cnames = city_names()
    cells = defaultdict(lambda: {"n": 0, "dead": 0, "inj": 0, "ped": 0, "old": 0, "la": 0.0, "lo": 0.0, "pref": "", "city": {}})
    pref = defaultdict(lambda: {"n": 0, "dead": 0, "inj": 0, "ped_dead": 0, "night_dead": 0})
    total = bad = 0
    for y in years:
        df = oc.read_csv(oc.get(y["honhyo"], timeout=600))
        c_lat, c_lon = oc.col(df, "緯度"), oc.col(df, "経度")
        c_dead, c_inj = oc.col(df, "死者数"), oc.col(df, "負傷者数")
        c_pref = oc.col(df, "都道府県コード")
        c_ka, c_kb = oc.col(df, "当事者種別", "A"), oc.col(df, "当事者種別", "B")
        c_aa, c_ab = oc.col(df, "年齢", "A"), oc.col(df, "年齢", "B")
        c_dn = oc.col(df, "昼夜", required=False)
        c_city = oc.col(df, "市区町村コード", required=False)
        oc.check(len(df) > 100000, "%d年の本票の件数が少なすぎます(%d)" % (y["year"], len(df)))
        need = [c for c in (c_lat, c_lon, c_dead, c_inj, c_pref, c_ka, c_kb, c_aa, c_ab, c_dn, c_city) if c]
        sub = df[need]
        del df
        for vals in zip(*(sub[c].tolist() for c in need)):
            r = dict(zip(need, vals))
            total += 1
            la, lo = dms(r[c_lat], 2), dms(r[c_lon], 3)
            dead, inj = oc.num(r[c_dead]) or 0, oc.num(r[c_inj]) or 0
            pc = str(r[c_pref]).lstrip("0")
            pn = prefcb.get(pc, "")
            city = ""
            if c_city and pn:
                jis = "%02d%03d" % (oc.PREF.index(pn) + 1, int(oc.num(r[c_city]) or 0))
                city = cnames.get(jis, "")
            is_ped = str(r[c_ka]).lstrip("0") in ped_codes or str(r[c_kb]).lstrip("0") in ped_codes
            is_old = str(r[c_aa]).lstrip("0") in old_codes or str(r[c_ab]).lstrip("0") in old_codes
            p = pref[pn]
            p["n"] += 1; p["dead"] += dead; p["inj"] += inj
            if is_ped: p["ped_dead"] += dead
            if c_dn and str(r[c_dn]).lstrip("0") in night_codes: p["night_dead"] += dead
            if la is None or lo is None or not (20 < la < 46 and 122 < lo < 154):
                bad += 1
                continue
            key = (round(la / GRID), round(lo / GRID))
            c = cells[key]
            c["n"] += 1; c["dead"] += dead; c["inj"] += inj
            c["ped"] += is_ped; c["old"] += is_old
            c["la"] += la; c["lo"] += lo; c["pref"] = pn
            if city:
                c["city"][city] = c["city"].get(city, 0) + 1
    oc.check(bad / max(total, 1) < 0.05, "緯度経度を読めない行が多すぎます(%d/%d)" % (bad, total))
    oc.log("rows", total, "bad", bad, "cells", len(cells))

    pts = []
    for (_, _), c in cells.items():
        if c["n"] < 3:
            continue
        la, lo = c["la"] / c["n"], c["lo"] / c["n"]
        pts.append({
            "place": c["pref"] + (max(c["city"], key=c["city"].get) if c["city"] else ""), "pref": c["pref"], "n": c["n"], "dead": c["dead"], "inj": c["inj"], "ped": c["ped"], "old": c["old"],
            "la": round(la, 5), "lo": round(lo, 5),
            "map": "地図で見る",
            "map_url": "https://maps.gsi.go.jp/#18/%.5f/%.5f/" % (la, lo),
        })
    period = "%d〜%d年" % (years[-1]["year"], years[0]["year"])
    cols_pt = [
        {"key": "place", "label": "場所（市区町村）"},
        {"key": "n", "label": "事故件数", "type": "num", "bar": True},
        {"key": "dead", "label": "死者", "type": "num"},
        {"key": "inj", "label": "負傷者", "type": "num"},
        {"key": "ped", "label": "歩行者が関係", "type": "num"},
        {"key": "map", "label": "場所", "type": "link"},
    ]
    method_pt = ("警察庁の本票（人身事故1件ごとの記録）の%sの緯度経度を、約50m四方のマス目に分けて数えました。"
                 "3件以上のマスが対象です。物損事故は含みません。マス目の区切り方によって、近い地点が2つに分かれることがあります。" % period)

    def rank(rid, title, key, desc, extra_sort=None):
        rows = sorted([x for x in pts if x[key] > 0], key=lambda x: (x[key], x["n"], x["dead"]), reverse=True)[:500]
        return {"id": rid, "tab": title.split("（")[0], "title": title, "desc": desc, "columns": cols_pt, "rows": rows,
                "trend": oc.trend(rows, "pref", 50, "地点", "地点"), "method": method_pt,
                "share_label": "place", "share_value": key}

    R = [
        rank("spot", "人身事故が集まる地点（%s）" % period, "n", "同じ場所でくり返し人身事故が起きている地点です。"),
        rank("ped", "歩行者が巻き込まれる地点", "ped", "歩行者が当事者になった人身事故が多い地点。通学路・生活道路の点検の目安に。"),
        rank("old", "高齢者が関係する事故が多い地点", "old", "当事者のどちらかが65歳以上の人身事故が多い地点。"),
        rank("dead", "死亡事故が起きた地点", "dead", "期間中に死者が出た人身事故が集中している地点。"),
    ]
    prows = []
    for pn, p in pref.items():
        if not pn:
            continue
        prows.append({"pref": pn, "n": p["n"], "dead": p["dead"],
                      "ped_share": (p["ped_dead"] / p["dead"]) if p["dead"] else None,
                      "night_share": (p["night_dead"] / p["dead"]) if p["dead"] else None})
    prows.sort(key=lambda x: (x["ped_share"] or 0), reverse=True)
    R.append({"id": "pref", "tab": "都道府県別", "title": "亡くなった人のうち歩行者が関係した割合（都道府県別）",
              "desc": "死亡事故のうち、歩行者が当事者だった事故の死者の割合。", "rows": prows,
              "columns": [{"key": "pref", "label": "都道府県"},
                          {"key": "ped_share", "label": "歩行者が関係", "type": "num", "fmt": "pct", "bar": True},
                          {"key": "night_share", "label": "夜間", "type": "num", "fmt": "pct"},
                          {"key": "dead", "label": "死者数", "type": "num"},
                          {"key": "n", "label": "人身事故件数", "type": "num"}],
              "method": "本票の死者数を、当事者A・Bのどちらかが歩行者かどうか、昼夜の区分で分けて合計しました（%s）。"
                        "北海道の5方面は北海道にまとめています。" % period,
              "share_label": "pref", "share_value": "ped_share"})

    geo = {}
    byp = defaultdict(list)
    for x in pts:
        byp[x["pref"]].append(x)
    for i, pn in enumerate(sorted(byp, key=lambda k: oc.PREF.index(k) if k in oc.PREF else 99)):
        top = sorted(byp[pn], key=lambda x: x["n"], reverse=True)[:400]
        geo["p%02d" % i] = {"label": pn, "points": [
            [x["la"], x["lo"], x["n"], "%s 人身事故%d件" % (x["place"], x["n"]),
             "死者%d 負傷者%d\n歩行者が関係%d件 高齢者が関係%d件" % (x["dead"], x["inj"], x["ped"], x["old"])] for x in top]}

    meta = {
        "data_period": period,
        "stats": [
            {"label": "対象の人身事故（%s）" % period, "value": total, "unit": "件"},
            {"label": "3件以上集中している地点", "value": len(pts), "unit": "か所"},
            {"label": "そのうち死者が出た地点", "value": sum(1 for x in pts if x["dead"] > 0), "unit": "か所"},
        ],
        "sources": [{"name": "交通事故統計情報のオープンデータ（本票）", "org": "警察庁", "url": y["page"],
                     "license": "公共データ利用規約（第1.0版）", "retrieved": oc.today()} for y in years],
    }
    oc.write(meta, R, geo=geo)


if __name__ == "__main__":
    oc.main(run)
