# 积存金——桌面小组件开发

## 项目定位

Windows 桌面悬浮窗小组件，用于实时显示金价和盈亏计算。极简、透明、可拖动、自动刷新。

## 技术栈

- Python 3.12 + tkinter（无第三方 UI 库）
- PyInstaller 单文件打包（`--onefile --windowed`）
- 新浪财经 `hq.sinajs.cn` 免费公开接口
- `ThreadPoolExecutor` 并发请求
- 数据存储：JSON 文件持久化（`watchlist.json`）

## 数据流

```
hf_XAU (伦敦金 USD/oz)  +  USDCNY (汇率)
       ↓
  中间价 = XAU × CNY ÷ 31.1035
       ↓
  买入价 = 中间价 + BUY_SPREAD
  卖出价 = 中间价 - SELL_SPREAD
       ↓
  盈亏 = (卖出价 - 成本) × 克数
```

## 核心约束

- **窗口**：`overrideredirect(True)` 无边框 + `-alpha 0.85` 半透明
- **刷新**：`root.after()` 定时器，不可用 `while+sleep`
- **线程**：网络请求在子线程，UI 更新必须 `root.after(0, callback)`
- **持久化**：`sys.frozen` 判断 PyInstaller 路径，配置存 EXE 同目录
- **防抖**：`_fetching_lock` 防止重复请求堆积
- **UI 更新**：复用 widget `.config()`，禁止 `destroy()` 后重建

## 修改点差

```python
BUY_SPREAD = 3    # 买入点差(元/克)
SELL_SPREAD = 2   # 卖出点差(元/克)
```

## 打包命令

```bash
pyinstaller --onefile --windowed --icon=gold.ico --name 积存金 gold_overlay.py
```

## 项目文件

| 文件 | 用途 |
|------|------|
| `gold_overlay.py` | 主程序 |
| `gold.ico` | 金色图标 |
| `启动悬浮窗.bat` | 启动脚本 |
| `show_data.py` | 调试用数据查看 |
| `watchlist.json` | 运行时配置（自动生成） |
