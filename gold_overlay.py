"""
桌面悬浮窗 - 积存金行情
透明背景 / 极简 / 可拖动 / 自动刷新
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== 路径 ==========
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "watchlist.json")

# ========== 配置 ==========
REFRESH_INTERVAL = 5          # 刷新间隔(秒)
MAX_WORKERS = 4
FONT_PRICE = ("Microsoft YaHei", 18, "bold")
FONT_LABEL = ("Microsoft YaHei", 10)
FONT_SMALL = ("Microsoft YaHei", 9)
FONT_TINY = ("Microsoft YaHei", 8)
WINDOW_WIDTH = 248
TITLE_HEIGHT = 26
PADDING = 10
BG = "#101018"
CARD_BG = "#1a1a28"
GOLD_CLR = "#ffd700"
# ★ 改动1：红涨绿跌
UP_CLR = "#ff5252"     # 红=涨
DOWN_CLR = "#00e676"   # 绿=跌
GRAY_CLR = "#888899"
TRANSPARENCY = 0.85
BUY_SPREAD = 3             # 买入点差
SELL_SPREAD = 2            # 卖出点差

# ========== DeepSeek 余额查询 ==========
DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"


def fetch_deepseek_balance():
    """查询 DeepSeek API 余额，返回 (余额字符串, 是否成功)"""
    # 优先从 os.environ 读取，兜底从注册表读取（解决子进程不继承的问题）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                api_key, _ = winreg.QueryValueEx(k, "DEEPSEEK_API_KEY")
        except Exception:
            pass
    if not api_key:
        return "未设置 DEEPSEEK_API_KEY", False
    try:
        req = urllib.request.Request(
            DEEPSEEK_BALANCE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("is_available") and data.get("balance_infos"):
                for info in data["balance_infos"]:
                    currency = info.get("currency", "")
                    total = info.get("total_balance", "0")
                    topped = float(info.get("topped_up_balance", 0))
                    granted = float(info.get("granted_balance", 0))
                    used = topped + granted - float(total)
                    return f"{currency} ¥{float(total):.2f} 已用¥{used:.2f}", True
            return "无余额数据", False
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return "Key 无效 (401)", False
        return f"请求失败 HTTP {e.code}", False
    except Exception as e:
        return f"网络错误", False

# ========== 默认自选列表 ==========
DEFAULT_WATCHLIST = [
    {"symbol": "hf_XAU",  "label": "国际金价",  "unit": "元/克",  "type": "forex"},
]

# ========== 新浪数据解析 ==========

SINA_URL = "https://hq.sinajs.cn/list={}"
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn"
}


def fetch_raw(symbol):
    """获取新浪原始数据"""
    url = SINA_URL.format(symbol)
    req = urllib.request.Request(url, headers=SINA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
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
        # 映射: [2]=最新价 [6]=昨收 [3]=最高
        if symbol.startswith("nf_"):
            p = parts
            price = float(p[2]) if len(p) > 2 and p[2] else 0         # 最新价
            prev_close = float(p[6]) if len(p) > 6 and p[6] else price # 昨收
            high = float(p[3]) if len(p) > 3 and p[3] else 0           # 最高
            # 最低: 扫描 p[4]~p[10]
            low_val = 999999
            for j in range(4, min(11, len(p))):
                try:
                    v = float(p[j])
                    if 0 < v < low_val:
                        low_val = v
                except (ValueError, IndexError):
                    pass
            low = low_val if low_val < 999999 else 0
            # 成交量
            volume = 0
            for j in [8, 12, 13]:
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
        self.root.title("万能弹窗")
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
        self._sell_price = 0      # 当前卖出价
        self._init_done = False   # 初始化标记
        self._ds_balance = ""     # DeepSeek 余额
        self._ds_ok = False       # DeepSeek 余额获取成功
        # 模块可见性（从配置恢复，默认全部显示）
        self._show_cards = cfg.get("show_cards", True)
        self._show_pl = cfg.get("show_pl", True)
        self._show_ds = cfg.get("show_ds", True)
        # 窗口尺寸（默认 WINDOW_WIDTH × 自动高度，用户可拖拽调整）
        self._win_width = cfg.get("window_width", WINDOW_WIDTH)
        self._win_height = cfg.get("window_height", 0)  # 0 = 自动计算
        # 拖拽状态
        self._resizing = False
        self._resize_start_x = self._resize_start_y = 0
        self._resize_win_w = self._resize_win_h = 0

        self._build_ui()
        self._bind_events()
        self._position_window(cfg.get("window_x", -1), cfg.get("window_y", -1))

        # 恢复输入（初始化阶段不触发盈亏）
        self.var_cost.set(str(cfg.get("cost_price", "")))
        self.var_grams.set(str(cfg.get("grams", "")))
        self._init_done = True

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(300, self.refresh_all)
        self.root.after(500, self._refresh_balance)
        self._update_clock()  # ★ 改动2C：启动时钟

    def _position_window(self, saved_x=-1, saved_y=-1):
        """定位窗口：优先使用保存的位置和尺寸"""
        sw = self.root.winfo_screenwidth()
        w = self._win_width
        h = self._win_height if self._win_height > 0 else self._calc_height()
        self.full_height = h

        if saved_x > 0 and saved_y > 0:
            x, y = saved_x, saved_y
        else:
            x, y = sw - w - 16, 80
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _calc_height(self):
        """根据可见模块计算窗口高度"""
        h = TITLE_HEIGHT  # 标题栏
        if self._show_cards:
            n = len(self.watchlist)
            h += n * 52 + PADDING  # 金价卡片
        if self._show_pl:
            h += 72  # 盈亏区（成本 + 克数 + 结果）
        if self._show_ds:
            h += 36  # DeepSeek 余额
        h += 12  # 底部留白
        return max(h, 80)

    def _recalc_height(self):
        h = self._calc_height()
        self.full_height = h
        w = self._win_width
        self.root.geometry(f"{w}x{h}")

    # ---- UI ----
    def _build_ui(self):
        self.main_frame = tk.Frame(self.root, bg=BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题栏：可拖拽 + 关闭按钮
        tb = tk.Frame(self.main_frame, bg=CARD_BG, height=TITLE_HEIGHT)
        tb.pack(fill=tk.X)
        tb.pack_propagate(False)

        self.title_lbl = tk.Label(tb, text="万能弹窗", font=("Microsoft YaHei", 9, "bold"),
                                  bg=CARD_BG, fg=GOLD_CLR)
        self.title_lbl.pack(side=tk.LEFT, padx=(8, 0), pady=(3, 0))

        # ★ 改动2A：时钟
        self.clock_lbl = tk.Label(tb, text="", font=("Consolas", 9),
                                  bg=CARD_BG, fg="#888888")
        self.clock_lbl.pack(side=tk.RIGHT, padx=(0, 8), pady=(3, 0))

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

        # 盈亏区
        self.pl_frame = tk.Frame(self.main_frame, bg=CARD_BG, padx=8, pady=4)
        self.pl_frame.pack(fill=tk.X, pady=(0, 4))

        r1 = tk.Frame(self.pl_frame, bg=CARD_BG)
        r1.pack(fill=tk.X)
        tk.Label(r1, text="成本", font=FONT_TINY, bg=CARD_BG, fg="#888888").pack(side=tk.LEFT)
        self.var_cost = tk.StringVar()
        self.var_cost.trace("w", lambda *a: self._on_input_change())
        self.entry_cost = tk.Entry(r1, bg="#0a0a15", fg="#ffd700", insertbackground="#ffd700",
                                    font=("Consolas", 9), width=8, justify=tk.RIGHT,
                                    textvariable=self.var_cost)
        self.entry_cost.pack(side=tk.LEFT, padx=4)
        tk.Label(r1, text="元/克", font=FONT_TINY, bg=CARD_BG, fg="#666666").pack(side=tk.LEFT)

        tk.Label(r1, text="克数", font=FONT_TINY, bg=CARD_BG, fg="#888888").pack(side=tk.LEFT, padx=(8, 0))
        self.var_grams = tk.StringVar()
        self.var_grams.trace("w", lambda *a: self._on_input_change())
        self.entry_grams = tk.Entry(r1, bg="#0a0a15", fg="#ffd700", insertbackground="#ffd700",
                                     font=("Consolas", 9), width=6, justify=tk.RIGHT,
                                     textvariable=self.var_grams)
        self.entry_grams.pack(side=tk.LEFT, padx=4)
        tk.Label(r1, text="克", font=FONT_TINY, bg=CARD_BG, fg="#666666").pack(side=tk.LEFT)

        # 盈亏显示
        r2 = tk.Frame(self.pl_frame, bg=CARD_BG)
        r2.pack(fill=tk.X, pady=(4, 0))
        tk.Label(r2, text="盈亏", font=FONT_TINY, bg=CARD_BG, fg="#888888").pack(side=tk.LEFT)
        self.lbl_pl = tk.Label(r2, text="—", font=("Microsoft YaHei", 11, "bold"),
                               bg=CARD_BG, fg="#888888")
        self.lbl_pl.pack(side=tk.LEFT, padx=6)

        # DeepSeek 余额（独立 frame，挂 main_frame 下，可单独隐藏）
        self.ds_frame = tk.Frame(self.main_frame, bg=CARD_BG, padx=8, pady=2)
        self.ds_frame.pack(fill=tk.X, pady=(4, 0))
        self.lbl_ds = tk.Label(self.ds_frame, text="DeepSeek 查询中...", font=("Microsoft YaHei", 9),
                               bg=CARD_BG, fg="#888888")
        self.lbl_ds.pack(side=tk.LEFT)

        # 按配置显示/隐藏模块
        if not self._show_cards:
            self.card_frame.pack_forget()
        if not self._show_pl:
            self.pl_frame.pack_forget()
        if not self._show_ds:
            self.ds_frame.pack_forget()

        # 右下角拖拽手柄
        self._grip = tk.Label(self.main_frame, text="⤡", font=("Microsoft YaHei", 8),
                              bg=BG, fg="#444455", cursor="size_nw_se")
        self._grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self._grip.bind("<Button-1>", self._start_resize)
        self._grip.bind("<B1-Motion>", self._do_resize)
        self._grip.bind("<ButtonRelease-1>", self._end_resize)

    # ---- 窗口缩放 ----
    def _start_resize(self, e):
        self._resizing = True
        self._resize_start_x = e.x_root
        self._resize_start_y = e.y_root
        self._resize_win_w = self.root.winfo_width()
        self._resize_win_h = self.root.winfo_height()

    def _do_resize(self, e):
        if not self._resizing:
            return
        dw = e.x_root - self._resize_start_x
        dh = e.y_root - self._resize_start_y
        new_w = max(180, self._resize_win_w + dw)
        new_h = max(60, self._resize_win_h + dh)
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{new_w}x{new_h}+{x}+{y}")

    def _end_resize(self, e):
        self._resizing = False
        self._win_width = self.root.winfo_width()
        self._win_height = self.root.winfo_height()
        self._save_dimensions()

    def _save_dimensions(self):
        try:
            cfg = load_config()
            cfg["window_width"] = self._win_width
            cfg["window_height"] = self._win_height
            save_config(cfg)
        except Exception:
            pass

    def _bind_events(self):
        self.root.bind("<Button-3>", self._context_menu)

    def _start_drag(self, e):
        self._drag_start_x = e.x_root
        self._drag_start_y = e.y_root
        self._drag_win_x = self.root.winfo_x()
        self._drag_win_y = self.root.winfo_y()

    def _do_drag(self, e):
        dx = e.x_root - self._drag_start_x
        dy = e.y_root - self._drag_start_y
        self.root.geometry(f"+{self._drag_win_x + dx}+{self._drag_win_y + dy}")

    def _context_menu(self, e):
        m = tk.Menu(self.root, tearoff=0, bg="#16213e", fg="#d0d0d0",
                    activebackground="#0f3460")
        m.add_command(label="🔄 刷新行情", command=self.refresh_all)
        m.add_command(label="💎 刷新 DeepSeek 余额", command=self._refresh_balance)
        m.add_separator()
        # 模块显示切换
        c = "✅" if self._show_cards else "⬜"
        m.add_command(label=f"{c} 金价卡片", command=self._toggle_cards)
        c = "✅" if self._show_pl else "⬜"
        m.add_command(label=f"{c} 盈亏计算", command=self._toggle_pl)
        c = "✅" if self._show_ds else "⬜"
        m.add_command(label=f"{c} DeepSeek", command=self._toggle_ds)
        m.add_separator()
        t = self.root.attributes("-topmost")
        m.add_command(label=f"{'✅' if t else '⬜'} 置顶", command=self._toggle_topmost)
        m.add_command(label="⭐ 自选管理", command=self._open_settings)
        m.add_separator()
        m.add_command(label="❌ 退出", command=self._on_close)
        m.post(e.x_root, e.y_root)

    # ---- 模块切换 ----
    def _toggle_topmost(self):
        self.root.attributes("-topmost", not self.root.attributes("-topmost"))

    def _toggle_cards(self):
        self._show_cards = not self._show_cards
        self._reorder_frames()
        self._save_visibility()

    def _toggle_pl(self):
        self._show_pl = not self._show_pl
        self._reorder_frames()
        self._save_visibility()

    def _toggle_ds(self):
        self._show_ds = not self._show_ds
        self._reorder_frames()
        self._save_visibility()

    def _reorder_frames(self):
        """确保 frame 排列顺序：card_frame → pl_frame → ds_frame"""
        for f in (self.card_frame, self.pl_frame, self.ds_frame):
            f.pack_forget()
        if self._show_cards:
            self.card_frame.pack(fill=tk.BOTH, expand=True)
        if self._show_pl:
            self.pl_frame.pack(fill=tk.X, pady=(0, 4))
        if self._show_ds:
            self.ds_frame.pack(fill=tk.X, pady=(4, 0))
        self._recalc_height()

    def _save_visibility(self):
        try:
            cfg = load_config()
            cfg["show_cards"] = self._show_cards
            cfg["show_pl"] = self._show_pl
            cfg["show_ds"] = self._show_ds
            save_config(cfg)
        except Exception:
            pass

    def _on_close(self):
        self.running = False
        try:
            cfg = load_config()
            cfg["window_x"] = self.root.winfo_x()
            cfg["window_y"] = self.root.winfo_y()
            cfg["window_width"] = self.root.winfo_width()
            cfg["window_height"] = self.root.winfo_height()
            cfg["watchlist"] = self.watchlist
            cfg["cost_price"] = self.entry_cost.get().strip()
            cfg["grams"] = self.entry_grams.get().strip()
            cfg["show_cards"] = self._show_cards
            cfg["show_pl"] = self._show_pl
            cfg["show_ds"] = self._show_ds
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
        """并发拉取数据，自动换算伦敦金 USD/oz → RMB/克"""
        try:
            # 始终拉取汇率用于换算
            syms_to_fetch = set(item["symbol"] for item in self.watchlist)
            syms_to_fetch.add("USDCNY")

            raw_data = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(fetch_raw, sym): sym
                           for sym in syms_to_fetch}
                for future in as_completed(futures):
                    sym = futures[future]
                    try:
                        raw_data[sym] = future.result()
                    except Exception:
                        raw_data[sym] = None

            # 解析汇率
            usdcny_rate = 7.2  # fallback
            usdcny_parts = raw_data.get("USDCNY")
            if usdcny_parts:
                usdcny_parsed = parse_any(usdcny_parts, "USDCNY", "", "")
                if usdcny_parsed:
                    usdcny_rate = usdcny_parsed.get("price", 7.2)

            results = []
            for item in self.watchlist:
                sym = item["symbol"]
                parts = raw_data.get(sym)
                if parts:
                    parsed = parse_any(parts, sym,
                                       item.get("label", sym),
                                       item.get("unit", ""))
                    if parsed:
                        # 伦敦金：换算 元/克，加银行点差
                        if sym == "hf_XAU":
                            mid = parsed["price"] * usdcny_rate / 31.1035
                            mid_prev = parsed["prev_close"] * usdcny_rate / 31.1035
                            parsed["buy"] = round(mid + BUY_SPREAD, 2)
                            parsed["sell"] = round(mid - SELL_SPREAD, 2)
                            parsed["price"] = round(mid, 2)
                            parsed["prev_close"] = round(mid_prev, 2)
                            parsed["change"] = round(mid - mid_prev, 2)
                            parsed["change_pct"] = round(
                                parsed["change"] / mid_prev * 100, 2
                            ) if mid_prev else 0
                            parsed["unit"] = "元/克"
                        results.append(parsed)

            self.prices = results
        except Exception:
            self.prices = []
        finally:
            # 无论如何都要回到主线程重置状态
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

        # 更新盈亏：始终取第一条数据的卖出价
        sell = 0
        if self.prices:
            sell = self.prices[0].get("sell", 0)
        self._sell_price = sell
        self._save_inputs()  # 首次成功拉取后存盘
        self.root.after(100, self._update_pl)

    # ---- 卡片 key: 用 label（同名符号靠标签区分） ----
    def _card_key(self, d):
        return d.get("label", d.get("symbol", "?"))

    def _create_card_widgets(self, d):
        """紧凑卡片：买/卖同行 + 涨跌"""
        card = tk.Frame(self.card_frame, bg=CARD_BG, padx=8, pady=4)
        card.pack(fill=tk.X, pady=(0, 2))

        # 行1: 名称 | 涨跌
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

        # 行2: 买入 ｜ 卖出
        r2 = tk.Frame(card, bg=CARD_BG)
        r2.pack(fill=tk.X)
        buy = d.get("buy", d.get("price", 0))
        w_price = tk.Label(r2, text=f"{buy:,.2f}", font=FONT_PRICE,
                           bg=CARD_BG, fg=GOLD_CLR)
        w_price.pack(side=tk.LEFT)
        tk.Label(r2, text="买", font=FONT_TINY,
                 bg=CARD_BG, fg="#886644").pack(side=tk.LEFT, padx=(2, 8))

        sell = d.get("sell", 0)
        w_sell = tk.Label(r2, text=f"{sell:,.2f}", font=("Microsoft YaHei", 12),
                          bg=CARD_BG, fg="#aaaaaa")
        w_sell.pack(side=tk.LEFT)
        tk.Label(r2, text="卖  " + d.get("unit", ""), font=FONT_TINY,
                 bg=CARD_BG, fg="#555566").pack(side=tk.LEFT, padx=(2, 0))

        return {
            "frame": card,
            "label": w_label, "buy": w_price, "sell": w_sell,
            "change": w_change,
        }

    def _update_card_widgets(self, widgets, d):
        widgets["label"].config(text=d.get("label", ""))
        buy = d.get("buy", d.get("price", 0))
        widgets["buy"].config(text=f"{buy:,.2f}")
        sell = d.get("sell", 0)
        widgets["sell"].config(text=f"{sell:,.2f}")
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

    # ---- 盈亏计算 ----
    def _on_input_change(self):
        """输入成本/克数时即时存盘 + 更新盈亏"""
        if not self._init_done:
            return
        self._update_pl()
        self._save_inputs()

    def _save_inputs(self):
        """即时持久化成本/克数"""
        try:
            cfg = load_config()
            cfg["watchlist"] = cfg.get("watchlist", self.watchlist)
            cfg["cost_price"] = self.var_cost.get().strip()
            cfg["grams"] = self.var_grams.get().strip()
            save_config(cfg)
        except Exception:
            pass

    def _update_pl(self):
        try:
            cost = float(self.var_cost.get().strip())
            grams = float(self.var_grams.get().strip())
        except ValueError:
            self.lbl_pl.config(text="—", fg="#888888")
            return

        if self._sell_price <= 0 or grams <= 0:
            self.lbl_pl.config(text="等待金价...", fg="#888888")
            return

        pl = (self._sell_price - cost) * grams
        pl_pct = (self._sell_price - cost) / cost * 100 if cost > 0 else 0
        clr = UP_CLR if pl >= 0 else DOWN_CLR
        sign = "+" if pl > 0 else ""
        self.lbl_pl.config(
            text=f"{sign}{pl:,.2f} 元  ({sign}{pl_pct:,.2f}%)", fg=clr)

    # ★ 改动2B：时钟更新方法
    def _update_clock(self):
        now = datetime.now().strftime("%H:%M:%S")
        self.clock_lbl.config(text=now)
        self.root.after(1000, self._update_clock)

    # ---- DeepSeek 余额 ----
    def _refresh_balance(self):
        """在子线程查询余额，主线程更新 UI"""
        def _fetch():
            txt, ok = fetch_deepseek_balance()
            self.root.after(0, lambda: self._update_balance(txt, ok))
        threading.Thread(target=_fetch, daemon=True).start()

    def _update_balance(self, txt, ok):
        self._ds_balance = txt
        self._ds_ok = ok
        self.lbl_ds.config(text=txt, fg="#00e676" if ok else "#ff5252")
        # 每 5 分钟刷新一次余额
        if self.running:
            self.root.after(300000, self._refresh_balance)

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