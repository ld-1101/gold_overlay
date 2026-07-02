# 🏅 积存金 · 桌面悬浮窗

银行积存金实时行情悬浮窗，透明可拖动，自动刷新，盈亏实时计算。

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 💰 **实时金价** | 伦敦金 XAU → 汇率换算 → 国内金价 元/克 |
| 📈 **买卖双价** | 买入 = 中间价+点差，卖出 = 中间价−点差 |
| 📊 **盈亏计算** | 输入成本 + 克数，自动算当前盈亏 |
| 🪟 **透明悬浮** | 半透明暗色背景，不遮挡桌面 |
| 🖱️ **随意拖拽** | 标题栏任意位置拖动 |
| 🔄 **自动刷新** | 每 5 秒更新，数据源新浪财经 |
| 💾 **持久存储** | 成本、克数、窗口位置自动保存 |

## 🚀 快速开始

### 直接使用
1. 从 [Releases](../../releases) 下载 `积存金.exe`
2. 双击运行，桌面出现悬浮窗
3. 输入买入成本和持有克数，盈亏自动显示

### 从源码运行
```bash
pip install pillow
python gold_overlay.py
```

### 自行打包
```bash
pip install pyinstaller pillow
pyinstaller --onefile --windowed --icon=gold.ico --name 积存金 gold_overlay.py
```

## 🎛️ 配置

修改 `gold_overlay.py` 顶部：
```python
BUY_SPREAD = 3        # 买入点差(元/克)
SELL_SPREAD = 2       # 卖出点差(元/克)
REFRESH_INTERVAL = 5  # 刷新间隔(秒)
```

## 📡 数据源

| 数据 | 接口 |
|------|------|
| 伦敦金 XAU | `hq.sinajs.cn/list=hf_XAU` |
| 美元汇率 | `hq.sinajs.cn/list=USDCNY` |

换算：`国内金价 = 伦敦金(USD/oz) × 汇率 ÷ 31.1035`

## 🛠️ 技术栈

Python 3.12 · tkinter · PyInstaller · 新浪财经公开接口 · ThreadPoolExecutor 并发

## 📄 License

MIT
