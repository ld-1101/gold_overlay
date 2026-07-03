# 🪟 万能弹窗 · 桌面悬浮窗

极简桌面悬浮窗，实时金价 + DeepSeek 余额 + 盈亏计算，透明可拖动，模块自由切换。

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 💰 **国际金价** | 伦敦金 XAU → 汇率换算 → 元/克，买/卖双价显示 |
| 🤖 **DeepSeek 余额** | 自动读取 `DEEPSEEK_API_KEY` 环境变量，显示 API 余额 |
| 📊 **盈亏计算** | 输入成本 + 克数，自动算当前盈亏 |
| 🧩 **模块切换** | 右键菜单自由开关：金价卡片 / 盈亏计算 / DeepSeek |
| 🪟 **透明悬浮** | 半透明暗色背景，置顶显示不遮挡 |
| 🖱️ **随意拖拽** | 标题栏任意位置拖动 |
| 🔄 **自动刷新** | 金价每 5 秒 / 余额每 5 分钟，数据源新浪财经 |
| 💾 **持久存储** | 成本、克数、窗口位置、模块显隐自动保存 |

## 🚀 快速开始

### 环境变量
```powershell
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxx"   # 可选，用于显示余额
```

### 从源码运行
```bash
pip install pyinstaller
python gold_overlay.py
```

### 打包为 EXE
```bash
pyinstaller --onefile --windowed --icon=gold.ico --name 万能弹窗 gold_overlay.py
```

## 🖱️ 右键菜单

| 选项 | 说明 |
|------|------|
| 🔄 刷新行情 | 手动刷新金价 |
| 💎 刷新 DeepSeek 余额 | 手动刷新 API 余额 |
| ✅ 金价卡片 | 切换金价显示 |
| ✅ 盈亏计算 | 切换盈亏计算器 |
| ✅ DeepSeek | 切换余额显示 |
| ✅ 置顶 | 窗口置顶 |
| ⭐ 自选管理 | 管理自选列表 |

## 📁 项目结构

| 文件 | 用途 |
|------|------|
| `gold_overlay.py` | 主程序 |
| `gold.ico` | 图标 |
| `启动悬浮窗.bat` | 启动脚本 |
| `show_data.py` | 调试用数据查看 |
| `数据源.html` | 数据源说明 |
| `watchlist.json` | 运行时配置（自动生成） |

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
