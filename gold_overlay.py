"""
桌面悬浮窗 - 积存金行情
透明背景 / 极简 / 可拖动 / 自动刷新
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== 路径 ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "watchlist.json")

# ========== 配置 ==========
REFRESH_INTERVAL = 10
MAX_WORKERS = 4
FONT_PRICE = ("Microsoft YaHei", 18, "bold")
FONT_LABEL = ("Microsoft YaHei", 10)
FONT_SMALL = ("Microsoft YaHei", 9)
FONT_TINY = ("Microsoft YaHei", 8)
WINDOW_WIDTH = 200
TITLE_HEIGHT = 26
PADDING = 10
BG = "#101018"
CARD_BG = "#1a1a28"
GOLD_CLR = "#ffd700"
UP_CLR = "#00e676"
DOWN_CLR = "#ff5252"
GRAY_CLR = "#888899"
TRANSPARENCY = 0.85

# ========== 默认自选列表 ==========
DEFAULT_WATCHLIST = [
    {"symbol": "nf_AU0",  "label": "积存金",  "unit": "元/克",  "type": "futures"},
]

# ========== 新浪数据解析 ==========

SINA_URL = "https://hq.sinajs.cn/list={symbol}"
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn"
}


def fetch_raw(symbol):
    """获取新浪原始数据"""
    url = SINA_URL.format(symbol=symbol)
    req = urllib.request.Request(url, headers=SINA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("gbk")
            if '"' not in text:
                return None
            return text.split('"')[1].split(",")
    except urllib.error.URLError as e:
        print(f"[网络错误] {symbol}: {e.reason}")
        return None
    except (ValueError, UnicodeDecodeError) as e:
        print(f"[解析错误] {symbol}: {e}")
        return None
    except Exception as e:
        print(f"[未知错误] {symbol}: {e}")
        return None


def parse_any(parts, symbol, label, unit):
    """通用解析器：根据 symbol 前缀自动判断数据格式"""
    if not parts or len(parts) < 2:
        return None

    try:
        # --- A股 (sh/sz 6位数字) ---
        if symbol[:2] in ("sh", "sz") and len(symbol) == 8:
            # 格式: 名称,今开,昨收,最新价,最高,最低,买价,卖价,成交量,成交额,...
            name = parts[0]
            price = float(parts[3]) if parts[3] else 0
            prev_close = float(parts[2]) if parts[2] else price
            high = float(parts[4]) if parts[4] else 0
            low = float(parts[5]) if parts[5] else 0
            volume = int(float(parts[8])) if parts[8] else 0
            amount = float(parts[9]) if parts[9] else 0
            change = round(price - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2) if prev_close else 0
            display_label = f"{label or name}"
            return {
                "symbol": symbol, "label": display_label, "price": price,
                "change": change, "change_pct": change_pct,
                "high": high, "low": low,
                "volume": volume, "amount": amount,
                "unit": unit or "元", "prev_close": prev_close, "is_stock": True
            }

        # --- 港股 (r_hk 或 hk) ---
        if "hk" in symbol.lower():
            # 港股格式: 英文名,今开,昨收,最新价,最高,最低,...
            name = parts[1] if len(parts) > 1 else label
            price = float(parts[6]) if len(parts) > 6 and parts[6] else 0
            prev_close = float(parts[3]) if len(parts) > 3 and parts[3] else price
            high = float(parts[4]) if len(parts) > 4 and parts[4] else 0
            low = float(parts[5]) if len(parts) > 5 and parts[5] else 0
            change = round(price - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2) if prev_close else 0
            return {
                "symbol": symbol, "label": label, "price": price,
                "change": change, "change_pct": change_pct,
                "high": high, "low": low,
                "unit": unit or "HKD", "prev_close": prev_close, "is_stock": True
            }

        # --- 外汇/期货/商品 (hf_) ---
        if symbol.startswith("hf_"):
            p = parts
            if symbol == "USDCNY":
                # 格式: 时间,最新价,昨收,买价,卖价,最高,最低,...
                price = float(p[1]) if p[1] else 0
                prev_close = float(p[2]) if p[2] else price
                high = float(p[5]) if len(p) > 5 and p[5] else 0
                low = float(p[6]) if len(p) > 6 and p[6] else 0
            else:
                # 通用 hf_ 格式: 最新价,昨收,买价,卖价,最高,最低,时间,昨收2,...
                price = float(p[0]) if p[0] else 0
                prev_close = float(p[1]) if p[1] else price
                high = float(p[4]) if len(p) > 4 and p[4] else 0
                low = float(p[5]) if len(p) > 5 and p[5] else 0
            change = round(price - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2) if prev_close else 0
            return {
                "symbol": symbol, "label": label, "price": price,
                "change": change, "change_pct": change_pct,
                "high": high, "low": low,
                "unit": unit or "", "prev_close": prev_close, "is_stock": False
            }

        # --- 国内期货 (nf_) 如沪金 ---
        # 数据格式: 品种名,时间,昨结算,最高,?,?,最新价,开盘,?,?,最低,...
        # 例: 黄金连续,150000,881.000,899.660,878.340,890.660,890.520,...
        if symbol.startswith("nf_"):
            p = parts
            price = float(p[5]) if len(p) > 5 and p[5] else 0         # 最新价
            prev_close = float(p[2]) if len(p) > 2 and p[2] else price # 昨结算
            high = float(p[3]) if len(p) > 3 and p[3] else 0           # 最高
            # 最低: 扫描找最小值
            low_val = 999999
            for j in [4, 9, 10]:
                try:
                    v = float(p[j]) if len(p) > j and p[j] else 0
                    if 0 < v < low_val:
                        low_val = v
                except (ValueError, IndexError):
                    pass
            low = low_val if low_val < 999999 else 0
            # 成交量: 找大数值
            volume = 0
            for j in [8, 9, 12, 13]:
                try:
                    v = float(p[j]) if len(p) > j and p[j] else 0
                    if v > 100 and volume == 0:
                        volume = int(v)
                except (ValueError, IndexError):
                    pass
            change = round(price - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2) if prev_close else 0
            return {
                "symbol": symbol, "label": label, "price": price,
                "change": change, "change_pct": change_pct,
                "high": high, "low": low,
                "volume": volume,
                "unit": unit or "元/克", "prev_close": prev_close, "is_stock": True
            }

        # --- 美股 (gb_) ---
        if symbol.startswith("gb_"):
            p = parts
            price = float(p[1]) if len(p) > 1 and p[1] else 0
            prev_close = float(p[2]) if len(p) > 2 and p[2] else price
            high = float(p[4]) if len(p) > 4 and p[4] else 0
            low = float(p[5]) if len(p) > 5 and p[5] else 0
            change = round(price - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2) if prev_close else 0
            return {
                "symbol": symbol, "label": label, "price": price,
                "change": change, "change_pct": change_pct,
                "high": high, "low": low,
                "unit": unit or "USD", "prev_close": prev_close, "is_stock": True
            }

        # --- fallback: 尝试按位置解析 ---
        price = float(parts[1]) if len(parts) > 1 and parts[1] else 0
        prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else price
        change = round(price - prev_close, 2)
        change_pct = round(change / prev_close * 100, 2) if prev_close else 0
        return {
            "symbol": symbol, "label": label, "price": price,
            "change": change, "change_pct": change_pct,
            "unit": unit or "", "prev_close": prev_close, "is_stock": False
        }

    except (ValueError, IndexError):
        return None


# ========== 配置管理 (含窗口位置) ==========

def load_config():
    """加载配置（自选列表 + 窗口位置）"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"watchlist": DEFAULT_WATCHLIST.copy(), "window_x": -1, "window_y": -1}


def save_config(config):
    """保存配置"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ========== 主窗口 ==========

class TickerOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("积存金")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", TRANSPARENCY)
        self.root.configure(bg=BG)

        cfg = load_config()
        self.watchlist = cfg.get("watchlist", DEFAULT_WATCHLIST.copy())
        if not isinstance(self.watchlist, list) or len(self.watchlist) == 0:
            self.watchlist = DEFAULT_WATCHLIST.copy()

        self.prices = []
        self.cards = {}           # key(标签) -> {"frame", "label", "price", ...}
        self.drag_x = self.drag_y = 0
        self.full_height = 100
        self.running = True
        self._fetching_lock = threading.Lock()
        self._fetching = False

        self._build_ui()
        self._bind_events()
        self._position_window(cfg.get("window_x", -1), cfg.get("window_y", -1))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(300, self.refresh_all)

    def _position_window(self, saved_x=-1, saved_y=-1):
        """定位窗口：优先使用保存的位置"""
        sw = self.root.winfo_screenwidth()
        n = len(self.watchlist)
        h = TITLE_HEIGHT + n * 52 + PADDING + 4
        h = max(h, 80)
        self.full_height = h

        if saved_x > 0 and saved_y > 0:
            x, y = saved_x, saved_y
        else:
            x, y = sw - WINDOW_WIDTH - 16, 80
        self.root.geometry(f"{WINDOW_WIDTH}x{h}+{x}+{y}")

    def _recalc_height(self):
        n = len(self.watchlist)
        h = TITLE_HEIGHT + n * 52 + PADDING + 4
        h = max(h, 80)
        self.full_height = h
        self.root.geometry(f"{WINDOW_WIDTH}x{h}")

    # ---- UI ----
    def _build_ui(self):
        self.main_frame = tk.Frame(self.root, bg=BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题栏：可拖拽 + 关闭按钮
        tb = tk.Frame(self.main_frame, bg=CARD_BG, height=TITLE_HEIGHT)
        tb.pack(fill=tk.X)
        tb.pack_propagate(False)

        self.title_lbl = tk.Label(tb, text="积存金", font=("Microsoft YaHei", 9, "bold"),
                                  bg=CARD_BG, fg=GOLD_CLR)
        self.title_lbl.pack(side=tk.LEFT, padx=(8, 0), pady=(3, 0))

        # ✕ 关闭
        close_btn = tk.Label(tb, text="✕", font=("Microsoft YaHei", 9),
                             bg=CARD_BG, fg="#885555", cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=(0, 6), pady=(3, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#ff5252"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg="#885555"))

        # 整个标题栏可拖拽
        for w in (tb, self.title_lbl):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.configure(cursor="fleur")

        # 卡片区
        self.card_frame = tk.Frame(self.main_frame, bg=BG, padx=8, pady=4)
        self.card_frame.pack(fill=tk.BOTH, expand=True)

        self.loading_lbl = tk.Label(self.card_frame, text="⏳ 加载中...",
                                     font=FONT_SMALL, bg=BG, fg="#555555")
        self.loading_lbl.pack(pady=20)

    def _bind_events(self):
        self.root.bind("<Button-3>", self._context_menu)

    def _start_drag(self, e):
        self.drag_x, self.drag_y = e.x_root, e.y_root

    def _do_drag(self, e):
        dx = e.x_root - self.drag_x
        dy = e.y_root - self.drag_y
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")
        self.drag_x, self.drag_y = e.x_root, e.y_root

    def _bind_events(self):
        self.title_lbl.bind("<Button-1>", self._start_drag)
        self.title_lbl.bind("<B1-Motion>", self._do_drag)
        self.root.bind("<Button-3>", self._context_menu)

    def _start_drag(self, e):
        self.drag_x, self.drag_y = e.x, e.y

    def _do_drag(self, e):
        dx = e.x_root - self.drag_x
        dy = e.y_root - self.drag_y
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")
        self.drag_x, self.drag_y = e.x_root, e.y_root

    def _context_menu(self, e):
        m = tk.Menu(self.root, tearoff=0, bg="#16213e", fg="#d0d0d0",
                    activebackground="#0f3460")
        m.add_command(label="🔄 刷新", command=self.refresh_all)
        t = self.root.attributes("-topmost")
        m.add_command(label=f"{'✅' if t else '⬜'} 置顶", command=self._toggle_topmost)
        m.add_separator()
        m.add_command(label="❌ 退出", command=self._on_close)
        m.post(e.x_root, e.y_root)

    def _toggle_topmost(self):
        self.root.attributes("-topmost", not self.root.attributes("-topmost"))

    def _on_close(self):
        self.running = False
        # 保存窗口位置
        try:
            cfg = load_config()
            cfg["window_x"] = self.root.winfo_x()
            cfg["window_y"] = self.root.winfo_y()
            cfg["watchlist"] = self.watchlist
            save_config(cfg)
        except Exception:
            pass
        self.root.destroy()

    # ---- 数据刷新 ----
    def _schedule_next(self):
        """使用 after 调度下一次刷新，替代线程 sleep"""
        if self.running:
            self.root.after(REFRESH_INTERVAL * 1000, self.refresh_all)

    def refresh_all(self):
        """入口：防重复触发"""
        with self._fetching_lock:
            if self._fetching:
                return
            self._fetching = True

        if self.loading_lbl.winfo_exists():
            self.loading_lbl.config(text="⏳ 刷新中...")
        threading.Thread(target=self._fetch_all, daemon=True).start()

    def _fetch_all(self):
        """并发拉取所有标的数据（去重符号）"""
        # 去重：同符号只请求一次
        unique_syms = {}
        for item in self.watchlist:
            sym = item["symbol"]
            if sym not in unique_syms:
                unique_syms[sym] = []
            unique_syms[sym].append(item)

        raw_data = {}  # symbol -> parts
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_raw, sym): sym
                       for sym in unique_syms}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    raw_data[sym] = future.result()
                except Exception:
                    raw_data[sym] = None

        # 每个 watchlist 条目生成一条结果
        results = []
        for item in self.watchlist:
            sym = item["symbol"]
            parts = raw_data.get(sym)
            if parts:
                parsed = parse_any(parts, sym,
                                   item.get("label", sym),
                                   item.get("unit", ""))
                if parsed:
                    results.append(parsed)

        self.prices = results
        self.root.after(0, self._update_display)

    # ---- UI 增量更新 ----
    def _update_display(self):
        """增量更新卡片：复用已有 widget，只改文字和颜色"""
        # 隐藏加载提示
        if self.loading_lbl.winfo_exists():
            self.loading_lbl.pack_forget()

        if not self.prices:
            if self.loading_lbl.winfo_exists():
                self.loading_lbl.config(text="❌ 获取失败")
            self._fetching = False
            self._schedule_next()
            return

        seen = set()
        for d in self.prices:
            key = self._card_key(d)
            seen.add(key)

            if key in self.cards:
                self._update_card_widgets(self.cards[key], d)
                # 保持卡片顺序
                self.cards[key]["frame"].pack_forget()
                self.cards[key]["frame"].pack(fill=tk.X, pady=(0, 2))
            else:
                self.cards[key] = self._create_card_widgets(d)

        # 移除不在当前数据中的旧卡片
        for key in list(self.cards):
            if key not in seen:
                self.cards[key]["frame"].destroy()
                del self.cards[key]

        self._fetching = False
        self._schedule_next()

    # ---- 卡片 key: 用 label（同名符号靠标签区分） ----
    def _card_key(self, d):
        return d.get("label", d.get("symbol", "?"))

    def _create_card_widgets(self, d):
        """紧凑卡片：名称 + 价格涨跌"""
        card = tk.Frame(self.card_frame, bg=CARD_BG, padx=8, pady=3)
        card.pack(fill=tk.X, pady=(0, 2))

        # 行1: 银行名称 ｜ 涨跌幅
        r1 = tk.Frame(card, bg=CARD_BG)
        r1.pack(fill=tk.X)
        w_label = tk.Label(r1, text=d.get("label", ""), font=FONT_SMALL,
                           bg=CARD_BG, fg="#cccccc")
        w_label.pack(side=tk.LEFT)

        change_txt, change_clr = self._format_change(
            d.get("change"), d.get("change_pct"))
        w_change = tk.Label(r1, text=change_txt, font=FONT_TINY,
                            bg=CARD_BG, fg=change_clr)
        w_change.pack(side=tk.RIGHT)

        # 行2: 价格 ｜ 单位
        r2 = tk.Frame(card, bg=CARD_BG)
        r2.pack(fill=tk.X)
        price = d.get("price", 0)
        price_str = f"{price:,.2f}" if isinstance(price, (int, float)) else "N/A"
        w_price = tk.Label(r2, text=price_str, font=FONT_PRICE,
                           bg=CARD_BG, fg=GOLD_CLR)
        w_price.pack(side=tk.LEFT)
        w_unit = tk.Label(r2, text=d.get("unit", ""), font=FONT_TINY,
                          bg=CARD_BG, fg="#555566")
        w_unit.pack(side=tk.RIGHT, pady=(4, 0))

        return {
            "frame": card,
            "label": w_label, "unit": w_unit,
            "price": w_price, "change": w_change,
        }

    def _update_card_widgets(self, widgets, d):
        widgets["label"].config(text=d.get("label", ""))
        widgets["unit"].config(text=d.get("unit", ""))

        price = d.get("price", 0)
        price_str = f"{price:,.2f}" if isinstance(price, (int, float)) else "N/A"
        widgets["price"].config(text=price_str)

        chg_txt, chg_clr = self._format_change(
            d.get("change"), d.get("change_pct"))
        widgets["change"].config(text=chg_txt, fg=chg_clr)

    @staticmethod
    def _format_change(change, change_pct):
        if change is None:
            return "", GRAY_CLR
        clr = UP_CLR if change >= 0 else DOWN_CLR
        sign = "+" if change > 0 else ""
        txt = f"{sign}{change:.2f}"
        if change_pct is not None:
            ps = "+" if change_pct >= 0 else ""
            txt += f"  {ps}{change_pct:.2f}%"
        return txt, clr

    def run(self):
        self.root.mainloop()

    # ---- 设置窗口 ----
    def _open_settings(self):
        SettingsWindow(self)


# ========== 设置窗口 ==========

class SettingsWindow:
    def __init__(self, parent: TickerOverlay):
        self.parent = parent
        self.win = tk.Toplevel(parent.root)
        self.win.title("⭐ 自选管理")
        self.win.geometry("420x420")
        self.win.configure(bg="#1a1a2e")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)

        # 居中
        self.win.update_idletasks()
        px = parent.root.winfo_x() + parent.root.winfo_width() // 2 - 210
        py = parent.root.winfo_y() + 30
        self.win.geometry(f"+{max(0, px)}+{max(0, py)}")

        self._build()
        self.win.grab_set()
        self.win.focus_force()

    def _build(self):
        pad = {"padx": 12, "pady": 6}

        # 标题
        hdr = tk.Frame(self.win, bg="#1a1a2e")
        hdr.pack(fill=tk.X, **pad)
        tk.Label(hdr, text="⭐ 自选列表管理", font=("Microsoft YaHei", 13, "bold"),
                 bg="#1a1a2e", fg="#ffd700").pack(side=tk.LEFT)
        tk.Label(hdr, text="双击删除 | 右键清空",
                 font=("Microsoft YaHei", 8), bg="#1a1a2e", fg="#555555").pack(side=tk.RIGHT)

        # 列表
        list_frame = tk.Frame(self.win, bg="#1a1a2e")
        list_frame.pack(fill=tk.BOTH, expand=True, **pad)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                   bg="#0f0f1a", fg="#d0d0d0",
                                   selectbackground="#0f3460",
                                   font=("Microsoft YaHei", 10),
                                   activestyle="none",
                                   height=14)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        # 填充列表
        self._refresh_list()

        # 双击删除
        self.listbox.bind("<Double-Button-1>", lambda e: self._delete_selected())
        self.listbox.bind("<Button-3>", lambda e: self._clear_all())

        # 添加区
        add_frame = tk.LabelFrame(self.win, text="➕ 添加自选", bg="#1a1a2e",
                                   fg="#aaaaaa", font=("Microsoft YaHei", 9))
        add_frame.pack(fill=tk.X, **pad)

        row1 = tk.Frame(add_frame, bg="#1a1a2e")
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="代码:", font=("Microsoft YaHei", 9),
                 bg="#1a1a2e", fg="#888888").pack(side=tk.LEFT)
        self.entry_symbol = tk.Entry(row1, bg="#0f0f1a", fg="#ffffff",
                                      insertbackground="#ffffff",
                                      font=("Consolas", 10), width=14)
        self.entry_symbol.pack(side=tk.LEFT, padx=(4, 12))

        tk.Label(row1, text="名称:", font=("Microsoft YaHei", 9),
                 bg="#1a1a2e", fg="#888888").pack(side=tk.LEFT)
        self.entry_label = tk.Entry(row1, bg="#0f0f1a", fg="#ffffff",
                                     insertbackground="#ffffff",
                                     font=("Microsoft YaHei", 10), width=12)
        self.entry_label.pack(side=tk.LEFT, padx=4)

        # 快捷代码提示
        row2 = tk.Frame(add_frame, bg="#1a1a2e")
        row2.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row2, text="单位:", font=("Microsoft YaHei", 9),
                 bg="#1a1a2e", fg="#888888").pack(side=tk.LEFT)
        self.entry_unit = tk.Entry(row2, bg="#0f0f1a", fg="#ffffff",
                                    insertbackground="#ffffff",
                                    font=("Microsoft YaHei", 10), width=8)
        self.entry_unit.pack(side=tk.LEFT, padx=4)
        self.entry_unit.insert(0, "元")

        add_btn = tk.Button(row2, text="✅ 添加", bg="#0f3460", fg="#ffffff",
                            font=("Microsoft YaHei", 9), padx=8, pady=1,
                            activebackground="#1a5276", relief=tk.FLAT,
                            cursor="hand2",
                            command=self._add_symbol)
        add_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # 快速模板
        tip_frame = tk.Frame(add_frame, bg="#1a1a2e")
        tip_frame.pack(fill=tk.X, pady=(4, 2))
        tk.Label(tip_frame, text="快捷:", font=("Microsoft YaHei", 8),
                 bg="#1a1a2e", fg="#555555").pack(side=tk.LEFT)

        quick_items = [
            ("黄金", "nf_AU0", "积存金"),
            ("黄金", "hf_XAU", "伦敦金"),
            ("外汇", "hf_SI", "白银"),
            ("外汇", "hf_CL", "原油"),
            ("沪深", "sh600519", "茅台"),
            ("港股", "r_hk00700", "腾讯"),
            ("美股", "gb_aapl", "苹果"),
            ("美股", "gb_tsla", "特斯拉"),
            ("指数", "sz399006", "创业板指"),
        ]
        for cat, sym, name in quick_items[:5]:  # 显示5个最常用的
            t = tk.Label(tip_frame, text=f" {name}", font=("Microsoft YaHei", 8),
                         bg="#1a1a2e", fg="#4499cc", cursor="hand2")
            t.pack(side=tk.LEFT, padx=(2, 0))
            t.bind("<Button-1>", lambda e, s=sym, n=name: self._quick_fill(s, n))
            t.bind("<Enter>", lambda e, lb=t: lb.configure(fg="#66bbff"))
            t.bind("<Leave>", lambda e, lb=t: lb.configure(fg="#4499cc"))

        # 底部按钮
        btm = tk.Frame(self.win, bg="#1a1a2e")
        btm.pack(fill=tk.X, **pad)
        tk.Button(btm, text="🔄 重置默认", bg="#333344", fg="#aaaaaa",
                  font=("Microsoft YaHei", 9), padx=8,
                  activebackground="#444466", relief=tk.FLAT, cursor="hand2",
                  command=self._reset_default).pack(side=tk.LEFT)
        tk.Button(btm, text="💾 保存并刷新", bg="#0f3460", fg="#ffffff",
                  font=("Microsoft YaHei", 9, "bold"), padx=12,
                  activebackground="#1a5276", relief=tk.FLAT, cursor="hand2",
                  command=self._save_and_close).pack(side=tk.RIGHT)

        # 绑定回车键
        self.entry_symbol.bind("<Return>", lambda e: self._add_symbol())
        self.entry_label.bind("<Return>", lambda e: self._add_symbol())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    def _quick_fill(self, sym, name):
        self.entry_symbol.delete(0, tk.END)
        self.entry_symbol.insert(0, sym)
        self.entry_label.delete(0, tk.END)
        self.entry_label.insert(0, name)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for item in self.parent.watchlist:
            sym = item["symbol"]
            lbl = item.get("label", sym)
            unit = item.get("unit", "")
            self.listbox.insert(tk.END, f"{lbl}  [{sym}]  {unit}")

    def _add_symbol(self):
        sym = self.entry_symbol.get().strip()
        lbl = self.entry_label.get().strip() or sym
        unit = self.entry_unit.get().strip() or "元"
        if not sym:
            messagebox.showwarning("提示", "请输入代码", parent=self.win)
            return

        # 去重
        for item in self.parent.watchlist:
            if item["symbol"] == sym:
                messagebox.showinfo("提示", f"代码 {sym} 已存在", parent=self.win)
                return

        self.parent.watchlist.append({"symbol": sym, "label": lbl, "unit": unit})
        self._refresh_list()
        self.entry_symbol.delete(0, tk.END)
        self.entry_label.delete(0, tk.END)

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            if idx < len(self.parent.watchlist):
                del self.parent.watchlist[idx]
                self._refresh_list()

    def _clear_all(self):
        if messagebox.askyesno("确认", "清空所有自选？\n可通过「重置默认」恢复", parent=self.win):
            self.parent.watchlist.clear()
            self._refresh_list()

    def _reset_default(self):
        if messagebox.askyesno("确认", "恢复默认自选列表？\n当前自定义列表将被覆盖", parent=self.win):
            self.parent.watchlist = DEFAULT_WATCHLIST.copy()
            self._refresh_list()

    def _save_and_close(self):
        cfg = load_config()
        cfg["watchlist"] = self.parent.watchlist
        save_config(cfg)
        self.parent._recalc_height()
        self.parent._position_window()
        # 清空旧卡片，强制重建
        for w in self.parent.cards.values():
            w["frame"].destroy()
        self.parent.cards.clear()
        self.parent.refresh_all()
        self.win.destroy()


# ========== 入口 ==========

def main():
    TickerOverlay().run()


if __name__ == "__main__":
    main()
