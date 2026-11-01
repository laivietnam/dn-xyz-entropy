#!/usr/bin/env python3
"""Delta-neutral funding giữa trade.xyz (dex `xyz`) và Entropy (dex `io`) trên Hyperliquid.

CHỈ ĐỌC: chỉ gọi https://api.hyperliquid.xyz/info. Không gọi /exchange, không xin khóa, không đặt lệnh.
Chỉ thư viện chuẩn Python 3.9+ — không cài thêm gì.

    python3 dn.py ma-chung                                   # mã có ở cả 2 sàn + thông số
    python3 dn.py cham NBIS --long xyz --short io --lev 3 --margin 1000   # chấm 4 tiêu chí trước khi vào
    python3 dn.py funding NBIS --long xyz --short io --days 30 --size 10000  # backtest funding ròng
    python3 dn.py vi-the --user 0x...                        # đọc vị thế DN đang giữ (2 chân, ký quỹ, TP/SL)
    python3 dn.py pnl --user 0x... --since 2026-10-29        # lãi/lỗ thật từng vòng: giá + funding − phí

Sai địa chỉ ví thì API không báo lỗi — trả rỗng trông như "không có vị thế". Script luôn in lại địa chỉ.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import time
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.hyperliquid.xyz/info"
DEXES = ("xyz", "io")
NAME = {"xyz": "trade.xyz", "io": "Entropy"}
MIN_ORDER_USD = 10.0  # sàn từ chối lệnh dưới $10 (tính theo giá đặt)

# Phí UI (mức cơ bản, chưa giảm ref/stake) của mã bật Growth mode — xem NBIS trên UI ngày 29/10/2026.
# Mã KHÔNG bật Growth mode: ước tính gấp 10 lần — CHƯA kiểm trên UI. Phí của anh em có thể khác: dùng --taker/--maker.
FEE_TAKER_BPS = 0.9
FEE_MAKER_BPS = 0.3


# ─── Gọi API ─────────────────────────────────────────────────────────────────
def post(payload: dict, retries: int = 3):
    for i in range(retries):
        try:
            req = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))  # 429 (hỏi quá dày) / 5xx (sàn bảo trì) thường tự hết


def now_ms() -> int:
    return int(time.time() * 1000)


_SPECS: dict[str, dict] = {}


def specs() -> dict[str, dict]:
    if not _SPECS:
        for d in DEXES:
            for u in post({"type": "meta", "dex": d})["universe"]:
                if u.get("isDelisted"):
                    continue
                _SPECS[u["name"]] = {
                    "sz_dec": int(u["szDecimals"]),
                    "max_lev": int(u["maxLeverage"]),
                    "margin_mode": u.get("marginMode", "cross"),
                    "growth": u.get("growthMode") == "enabled",
                }
    return _SPECS


def common() -> list[str]:
    names = {d: {n.split(":")[1] for n in specs() if n.startswith(d + ":")} for d in DEXES}
    return sorted(names["xyz"] & names["io"])


def book(coin: str):
    lv = post({"type": "l2Book", "coin": coin})["levels"]
    side = lambda L: [(float(x["px"]), float(x["sz"])) for x in L]
    return side(lv[0]), side(lv[1])


def mid(coin: str) -> float:
    b, a = book(coin)
    return (b[0][0] + a[0][0]) / 2


def walk(levels, usd: float) -> float | None:
    """Giá trung bình nếu ăn `usd` vào sổ lệnh; None nếu 20 mức giá không đủ."""
    left, cost, qty = usd, 0.0, 0.0
    for px, sz in levels:
        take = min(left, px * sz)
        cost += take
        qty += take / px
        left -= take
        if left <= 1e-9:
            return cost / qty
    return None


def candles(coin: str, interval: str, days: int) -> list[dict]:
    t = now_ms()
    return post({"type": "candleSnapshot",
                 "req": {"coin": coin, "interval": interval, "startTime": t - days * 86_400_000, "endTime": t}})


def funding_hist(coin: str, start: int) -> dict[int, float]:
    """{giờ (ms // 3.6e6): fundingRate} — lật trang 500 dòng."""
    out, t = {}, start
    while True:
        h = post({"type": "fundingHistory", "coin": coin, "startTime": t})
        if not h:
            return out
        for x in h:
            out[x["time"] // 3_600_000] = float(x["fundingRate"])
        if len(h) < 500:
            return out
        t = h[-1]["time"] + 1


def funding_net(sym: str, long_dex: str, short_dex: str, days: int) -> list[tuple[int, float]]:
    """[(giờ, funding ròng)] cho DN mua `long_dex` / bán `short_dex`. Dương = mình nhận.
    Bên long trả funding dương, bên short nhận funding dương → ròng = rate(short) − rate(long)."""
    start = now_ms() - days * 86_400_000
    a, b = funding_hist(f"{long_dex}:{sym}", start), funding_hist(f"{short_dex}:{sym}", start)
    return [(h, b[h] - a[h]) for h in sorted(set(a) & set(b))]


def liq_move(lev: float, max_lev: int, is_long: bool) -> float:
    """Giá chạy ngược bao nhiêu (tỉ lệ) thì lệnh ký quỹ riêng bị thanh lý — công thức tài liệu HL.
    Ký quỹ duy trì = 1/2 ký quỹ ở đòn bẩy tối đa."""
    l = 1 / (2 * max_lev)
    avail = 1 / lev - l
    return avail / (1 - l) if is_long else avail / (1 + l)


def fee_bps(coin: str, taker: float, maker: float) -> tuple[float, float]:
    k = 1 if specs()[coin]["growth"] else 10
    return taker * k, maker * k


def pages(payload: dict, start: int, page: int, key) -> list[dict]:
    """Lật trang lịch sử. Trang sau bắt đầu từ mốc giờ cuối của trang trước (KHÔNG +1: nhiều lần khớp
    chung 1 mili-giây), rồi bỏ trùng theo `key`."""
    out, seen, t = [], set(), start
    while True:
        h = post({**payload, "startTime": t})
        new = [x for x in h if key(x) not in seen]
        seen |= {key(x) for x in new}
        out += new
        if len(h) < page or not new:
            return out
        t = max(x["time"] for x in h)


def positions(user: str, dex: str) -> dict[str, dict]:
    out = {}
    for ap in post({"type": "clearinghouseState", "user": user, "dex": dex}).get("assetPositions", []):
        p = ap["position"]
        szi = float(p["szi"])
        if szi == 0:
            continue
        value = float(p["positionValue"])
        out[p["coin"]] = {
            "szi": szi, "entry": float(p["entryPx"] or 0), "value": value,
            "liq": float(p["liquidationPx"]) if p.get("liquidationPx") else None,
            "margin": float(p["marginUsed"]),  # ĐÃ gồm lãi/lỗ chưa chốt (kiểm thật 29/10/2026)
            "upnl": float(p["unrealizedPnl"]), "lev": float(p["leverage"]["value"]),
            "lev_type": p["leverage"]["type"], "mark": value / abs(szi),
        }
    return out


def usd(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}${abs(x):,.2f}"


def check_user(user: str) -> str:
    u = user.strip()
    if not (u.startswith("0x") and len(u) == 42):
        raise SystemExit(f"Địa chỉ ví không hợp lệ: {u!r} (cần 0x + 40 ký tự)")
    return u.lower()


# ─── Lệnh ────────────────────────────────────────────────────────────────────
def cmd_ma_chung(a) -> None:
    sp = specs()
    print(f"Mã có ở cả trade.xyz (xyz) và Entropy (io) — đọc lúc {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC\n")
    print(f"{'Mã':<8} {'Đòn bẩy tối đa xyz/io':<22} {'Ký quỹ xyz / io':<34} Growth mode xyz/io")
    for s in common():
        x, i = sp[f"xyz:{s}"], sp[f"io:{s}"]
        print(f"{s:<8} {str(x['max_lev']) + 'x / ' + str(i['max_lev']) + 'x':<22} "
              f"{x['margin_mode'] + ' / ' + i['margin_mode']:<34} {'có' if x['growth'] else 'không'} / {'có' if i['growth'] else 'không'}")
    print("\nstrictIsolated = không rút/nạp ký quỹ được → không cân ký quỹ giữa 2 chân được → loại.")


def cmd_cham(a) -> None:
    sym, lev, margin = a.sym.upper(), a.lev, a.margin
    if a.long == a.short:
        raise SystemExit("--long và --short phải là 2 sàn khác nhau (xyz / io)")
    if sym not in common():
        raise SystemExit(f"{sym} không có ở cả 2 sàn. Mã chung: {', '.join(common())}")
    sp = {d: specs()[f"{d}:{sym}"] for d in DEXES}
    notional = margin * lev
    print(f"DN {sym}: mua {NAME[a.long]} / bán {NAME[a.short]} · x{lev} · ký quỹ ${margin:,.0f}/chân "
          f"→ mỗi chân ${notional:,.0f}\n")
    for d in DEXES:
        if lev > sp[d]["max_lev"]:
            print(f"⛔ x{lev} vượt mức tối đa x{sp[d]['max_lev']} của {d}:{sym}")
            return
    res = []
    # 1) Thanh khoản Entropy (chân khó khớp): KL TB 7 ngày, giả sử mình được 1/2 khối lượng mỗi phía
    vol = st.mean(float(k["v"]) * float(k["c"]) for k in candles(f"io:{sym}", "1d", 7))
    fill_min = notional / max(vol / 1440 / 2, 1e-9)
    res.append(("Thanh khoản Entropy", fill_min <= a.max_fill,
                f"KL TB 7 ngày ${vol / 1e6:.2f}M/ngày → chờ khớp ${notional:,.0f} {'dưới 1' if fill_min < 1 else f'~{fill_min:.0f}'} phút (ngưỡng {a.max_fill:g})"))
    # 2) Funding 30 ngày đúng chiều đã chọn; mã mới lên < 28 ngày dữ liệu thì không chấm đạt
    net = [r for _, r in funding_net(sym, a.long, a.short, 30)]
    f = lambda h: sum(net[-h:]) * notional
    apr = sum(net) / max(len(net), 1) * 24 * 365 * 100
    days = len(net) / 24
    res.append(("Funding 30 ngày", sum(net) > 0 and days >= 28,
                f"3 ngày {usd(f(72))} · 7 ngày {usd(f(168))} · 30 ngày {usd(f(720))} (~{apr:+.1f}%/năm trên giá trị)"
                + ("" if days >= 28 else f" · ⚠️ mới có {days:.0f} ngày dữ liệu")))
    # 3) Rút/nạp ký quỹ được
    strict = [d for d in DEXES if sp[d]["margin_mode"] == "strictIsolated"]
    res.append(("Rút được ký quỹ", not strict,
                "cả 2 chân rút/nạp ký quỹ được" if not strict else f"{', '.join(strict)} là strictIsolated — không cân ký quỹ được"))
    # 4) Khoảng cách tới giá thanh lý so với dao động ngày lớn nhất 30 ngày
    rng = max((float(k["h"]) / float(k["l"]) - 1) * 100 for k in candles(f"xyz:{sym}", "1d", 30))
    lm = {d: liq_move(lev, sp[d]["max_lev"], a.long == d) * 100 for d in DEXES}
    worst = min(lm.values())
    res.append(("Giá thanh lý", worst > rng,
                f"chân yếu nhất bị thanh lý khi giá chạy ngược ~{worst:.1f}% · dao động ngày lớn nhất 30 ngày {rng:.1f}%"))
    for n, ok, d in res:
        print(f"{'✅' if ok else '⚠️'} {n}: {d}")

    # Chi phí cả vòng (mở + đóng) theo cách: chờ (Maker) bên Entropy + khớp ngay (Taker) bên trade.xyz theo phần $500
    tk, _ = fee_bps(f"xyz:{sym}", a.taker, a.maker)
    _, mk = fee_bps(f"io:{sym}", a.taker, a.maker)
    b, ak = book(f"xyz:{sym}")
    xm = (b[0][0] + ak[0][0]) / 2
    slip = sum(((walk(L, a.chunk) or L[-1][0]) / xm - 1) * s for L, s in ((ak, 1), (b, -1)))
    cost = notional * (2 * (mk + tk) / 1e4 + slip)
    ib, ia = book(f"io:{sym}")
    im = (ib[0][0] + ia[0][0]) / 2
    gap = (im / xm - 1) * 1e4
    depth = lambda L, ref: sum(px * sz for px, sz in L if abs(px / ref - 1) <= 0.0025)
    print(f"\n• Chi phí cả vòng mở + đóng (chờ Entropy, khớp ngay trade.xyz theo phần ${a.chunk:,.0f}): ~${cost:.2f}"
          f" (phí taker {tk:.2f} / maker {mk:.2f} bps)")
    print(f"• Giá Entropy đang {'cao' if gap > 0 else 'thấp'} hơn trade.xyz {abs(gap):.1f} bps")
    print(f"• Sổ Entropy trong ±25 bps: mua ${depth(ib, im):,.0f} · bán ${depth(ia, im):,.0f}")
    print(f"• Bị thanh lý khi giá chạy ngược: " + " · ".join(f"{NAME[d]} {lm[d]:.1f}%" for d in DEXES))
    bad = [n for n, ok, _ in res if not ok]
    print("\n" + (f"⚠️ Trượt: {', '.join(bad)}." if bad else "Đạt cả 4 tiêu chí.")
          + " Đây là số đo, không phải khuyến nghị vào lệnh.")


def cmd_funding(a) -> None:
    sym = a.sym.upper()
    rows = funding_net(sym, a.long, a.short, a.days)
    if not rows:
        raise SystemExit(f"Không có dữ liệu funding chung cho {sym}")
    size = a.size
    day = {}
    for h, r in rows:
        d = datetime.fromtimestamp(h * 3600, timezone(timedelta(hours=a.tz))).date()
        day[d] = day.get(d, 0.0) + r * size
    vals = list(day.values())
    tot = sum(vals)
    hours = len(rows)
    apr = sum(r for _, r in rows) / hours * 24 * 365 * 100
    cum, peak, dd, run, worst_run = 0.0, 0.0, 0.0, 0, 0
    for v in vals:
        cum += v
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
        run = run + 1 if v < 0 else 0
        worst_run = max(worst_run, run)
    first, last = min(day), max(day)
    print(f"Funding ròng {sym}: mua {NAME[a.long]} / bán {NAME[a.short]} · ${size:,.0f}/chân · "
          f"{first:%d/%m/%Y} → {last:%d/%m/%Y} ({hours} giờ, UTC{a.tz:+d})\n")
    print(f"• Tổng: {usd(tot)}  (~{apr:+.1f}%/năm trên giá trị 1 chân)")
    print(f"• Ngày có lợi: {sum(v > 0 for v in vals)}/{len(vals)} · tệ nhất {usd(min(vals))} · tốt nhất {usd(max(vals))}")
    print(f"• Chuỗi ngày âm dài nhất: {worst_run} · sụt lớn nhất của funding cộng dồn: {usd(dd)}")
    print("  (ngày đầu/cuối có thể thiếu giờ)\n\nTheo tuần (bắt đầu thứ Hai):")
    wk: dict = {}
    for d, v in day.items():
        k = d - timedelta(days=d.weekday())
        wk.setdefault(k, [0.0, 0])
        wk[k][0] += v
        wk[k][1] += 1
    for k in sorted(wk):
        v, n = wk[k]
        print(f"  {k:%d/%m}  {usd(v):>10}" + ("" if n == 7 else f"  ({n} ngày)"))
    print("\nTheo tháng:")
    mo: dict = {}
    for d, v in day.items():
        mo.setdefault((d.year, d.month), [0.0, 0])
        mo[(d.year, d.month)][0] += v
        mo[(d.year, d.month)][1] += 1
    for (y, m), (v, n) in sorted(mo.items()):
        print(f"  {m:02d}/{y}  {usd(v):>10}  ({n} ngày, ~{v / n * 365 / size * 100:+.1f}%/năm)")
    print("\nFunding quá khứ không hứa hẹn gì cho tương lai. Chưa trừ phí vào/ra và chênh giá 2 sàn.")


def cmd_vi_the(a) -> None:
    user = check_user(a.user)
    pos = {d: positions(user, d) for d in DEXES}
    print(f"Ví {user}\n")
    syms = sorted({c.split(":")[1] for d in DEXES for c in pos[d]})
    if not syms:
        print("Không có vị thế nào trên trade.xyz và Entropy (sai địa chỉ cũng ra như vậy — kiểm lại).")
        return
    trig = {d: [o for o in post({"type": "frontendOpenOrders", "user": user, "dex": d}) if o.get("isTrigger")]
            for d in DEXES}
    for s in syms:
        legs = {d: pos[d].get(f"{d}:{s}") for d in DEXES}
        print(f"■ {s}")
        for d, p in legs.items():
            if not p:
                print(f"  {NAME[d]}: không có")
                continue
            dist = abs(p["mark"] - p["liq"]) / p["mark"] * 100 if p["liq"] else float("nan")
            m0 = p["entry"] * abs(p["szi"]) / p["lev"]  # ký quỹ lúc mở (ước theo giá vào + đòn bẩy)
            n_tp = sum(1 for o in trig[d] if o.get("coin") == f"{d}:{s}")
            print(f"  {NAME[d]}: {'MUA' if p['szi'] > 0 else 'BÁN'} {abs(p['szi'])} · ${p['value']:,.0f} · "
                  f"x{p['lev']:g} {p['lev_type']} · ký quỹ ${p['margin']:,.2f} (~{p['margin'] / m0:.0%} lúc mở) · "
                  f"lãi/lỗ theo mark {usd(p['upnl'])} · cách thanh lý {dist:.1f}% · TP/SL trên sàn: {n_tp}")
        io_p, xyz_p = legs["io"], legs["xyz"]
        if not io_p or not xyz_p:
            print("  ⚠️ Chỉ có 1 chân — không phải DN (hoặc chân kia đã bị thanh lý/đóng).")
            continue
        gap = abs(io_p["szi"] + xyz_p["szi"]) * io_p["mark"]
        if io_p["szi"] * xyz_p["szi"] > 0:
            print("  ⚠️ 2 chân CÙNG chiều — không phải DN.")
        elif gap >= MIN_ORDER_USD:
            print(f"  ⚠️ 2 chân lệch nhau ~${gap:,.0f}")
        lose = min(legs, key=lambda d: legs[d]["margin"])
        win = "xyz" if lose == "io" else "io"
        W, L = legs[win], legs[lose]
        removable = W["margin"] - max(W["value"] / W["lev"], 0.1 * W["value"])
        if removable > 1:
            print(f"  Chân {NAME[win]} có thể rút ra ~${removable:,.2f} tiền lời để nạp chân {NAME[lose]} "
                  "(công thức tài liệu HL; sàn có thể đòi giữ lại nhiều hơn)")
        if not any(o.get("coin") in (f"io:{s}", f"xyz:{s}") for d in DEXES for o in trig[d]):
            print("  ⚠️ Không có TP/SL nào trên sàn cho mã này — nếu máy/bot canh chết thì không còn lớp cứu.")
    print("\nSố đọc từ sàn lúc này. Lãi/lỗ theo mark khác giá khớp thật — xem lệnh `pnl`.")


def cmd_pnl(a) -> None:
    user = check_user(a.user)
    tz = timezone(timedelta(hours=a.tz))
    since = int(datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=tz).timestamp() * 1000)
    t = lambda ms: datetime.fromtimestamp(ms / 1000, tz).strftime("%d/%m %H:%M")
    fills = [f for f in pages({"type": "userFillsByTime", "user": user}, since, 2000, lambda f: f["tid"])
             if f["coin"].split(":")[0] in DEXES]
    fund = pages({"type": "userFunding", "user": user}, since, 500, lambda x: (x["time"], x["delta"]["coin"]))

    # Tách vòng: mở khi cả 2 chân của mã đang 0 mà có lệnh khớp, đóng khi cả 2 về 0.
    # Gom lệnh cùng mã cùng mili-giây (thứ tự trong cùng mốc không đáng tin).
    by: dict[str, list[dict]] = {}
    pos: dict[str, dict[str, float]] = {}
    batches: dict[tuple[str, int], list[dict]] = {}
    for f in fills:
        batches.setdefault((f["coin"].split(":")[1], f["time"]), []).append(f)
    for (sym, tm), fs in sorted(batches.items(), key=lambda kv: kv[0][1]):
        p = pos.setdefault(sym, {d: 0.0 for d in DEXES})
        if all(abs(v) < 1e-9 for v in p.values()):
            by.setdefault(sym, []).append({"sym": sym, "start": tm, "end": tm, "closed": False,
                                           "pnl": 0.0, "fee": 0.0, "fund": 0.0, "dexes": set()})
        r = by[sym][-1]
        for f in fs:
            dex = f["coin"].split(":")[0]
            p[dex] = round(p[dex] + float(f["sz"]) * (1 if f["side"] == "B" else -1), 9)
            r["pnl"] += float(f["closedPnl"])
            r["fee"] += float(f["fee"])
            r["dexes"].add(dex)
        r["end"] = tm
        r["closed"] = all(abs(v) < 1e-9 for v in p.values())
    for x in fund:
        dex, _, sym = x["delta"]["coin"].partition(":")
        if dex not in DEXES:
            continue
        for r in by.get(sym, []):
            if r["start"] <= x["time"] and (not r["closed"] or x["time"] <= r["end"]):
                r["fund"] += float(x["delta"]["usdc"])
                break
    rounds = [r for rs in by.values() for r in rs if len(r["dexes"]) == 2]  # chỉ vòng có lệnh ở cả 2 sàn

    print(f"Ví {user} · từ {a.since} (UTC{a.tz:+d})\n")
    if not rounds:
        print("Chưa có vòng DN nào (cần lệnh khớp ở cả trade.xyz và Entropy cùng mã).")
        return
    total = 0.0
    for r in sorted(rounds, key=lambda r: r["start"]):
        line = f"{usd(r['pnl'])} giá đã chốt · funding {usd(r['fund'])} · phí {usd(-r['fee'])}"
        net = r["pnl"] + r["fund"] - r["fee"]
        if r["closed"]:
            print(f"■ {r['sym']} {t(r['start'])} → {t(r['end'])} (đã đóng): {usd(net)}\n  {line}")
        else:
            mid_pnl = 0.0
            for d in DEXES:
                p = positions(user, d).get(f"{d}:{r['sym']}")
                if p:
                    mid_pnl += (mid(f"{d}:{r['sym']}") - p["entry"]) * p["szi"]
            net += mid_pnl
            print(f"■ {r['sym']} từ {t(r['start'])} (đang mở): tạm tính {usd(net)}\n  {line} · "
                  f"chênh giá 2 chân theo giá giữa sổ lệnh {usd(mid_pnl)}")
        total += net
    print(f"\nTổng: {usd(total)}")
    print("Giá = giá khớp thật + giá giữa sổ lệnh cho phần đang mở (không theo mark). "
          "Lệnh tay cùng mã trong lúc giữ DN sẽ bị gộp vào vòng. Hoàn phí ref (nếu có) không tính ở đây.")


def main() -> None:
    ap = argparse.ArgumentParser(description="DN funding trade.xyz × Entropy — chỉ đọc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ma-chung", help="mã có ở cả 2 sàn")

    def pair(p):
        p.add_argument("sym")
        p.add_argument("--long", choices=DEXES, default="xyz")
        p.add_argument("--short", choices=DEXES, default="io")

    p = sub.add_parser("cham", help="chấm 4 tiêu chí trước khi vào")
    pair(p)
    p.add_argument("--lev", type=int, required=True)
    p.add_argument("--margin", type=float, required=True, help="ký quỹ MỖI chân ($)")
    p.add_argument("--max-fill", type=float, default=30, help="ngưỡng phút chờ khớp bên Entropy")
    p.add_argument("--chunk", type=float, default=500, help="khớp ngay trade.xyz theo phần bao nhiêu $")
    p.add_argument("--taker", type=float, default=FEE_TAKER_BPS, help="phí taker bps (mã Growth mode)")
    p.add_argument("--maker", type=float, default=FEE_MAKER_BPS, help="phí maker bps (mã Growth mode)")

    p = sub.add_parser("funding", help="backtest funding ròng")
    pair(p)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--size", type=float, default=10_000, help="giá trị mỗi chân ($)")
    p.add_argument("--tz", type=int, default=7, help="múi giờ để chia ngày (mặc định UTC+7)")

    p = sub.add_parser("vi-the", help="đọc vị thế DN của 1 ví")
    p.add_argument("--user", required=True)

    p = sub.add_parser("pnl", help="lãi/lỗ thật từng vòng DN")
    p.add_argument("--user", required=True)
    p.add_argument("--since", required=True, help="YYYY-MM-DD")
    p.add_argument("--tz", type=int, default=7)

    a = ap.parse_args()
    {"ma-chung": cmd_ma_chung, "cham": cmd_cham, "funding": cmd_funding,
     "vi-the": cmd_vi_the, "pnl": cmd_pnl}[a.cmd](a)


if __name__ == "__main__":
    main()
