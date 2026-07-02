import urllib.request
from datetime import datetime

headers = {'Referer': 'https://finance.sina.com.cn'}

# 伦敦金
req = urllib.request.Request('https://hq.sinajs.cn/list=hf_XAU', headers=headers)
xp = urllib.request.urlopen(req, timeout=4).read().decode('gbk').split('"')[1].split(',')
x_price = float(xp[0])   # 最新价
x_prev = float(xp[1])    # 昨收
x_time = xp[6] if len(xp) > 6 else '?'

# 汇率
req = urllib.request.Request('https://hq.sinajs.cn/list=USDCNY', headers=headers)
up = urllib.request.urlopen(req, timeout=4).read().decode('gbk').split('"')[1].split(',')
u_price = float(up[1])   # 最新价
u_prev = float(up[2])    # 昨收

# 换算国内金价
OZ2G = 31.1035
rmb = x_price * u_price / OZ2G
rmb_prev = x_prev * u_prev / OZ2G
chg = rmb - rmb_prev
pct = chg / rmb_prev * 100

sign = '+' if chg > 0 else ''
print(f'更新时间: {datetime.now().strftime("%H:%M:%S")}')
print(f'伦敦金时间: {x_time}')
print()
print(f'========== 国内金价(估算) ==========')
print(f'  💰 {rmb:.2f} 元/克')
print(f'  📈 {sign}{chg:.2f}  {sign}{pct:.2f}%')
print()
print(f'========== 原始数据 ==========')
print(f'  伦敦金: {x_price:.2f} USD/oz (昨收 {x_prev:.2f})')
print(f'  汇  率: {u_price:.4f} (昨收 {u_prev:.4f})')
print(f'  换  算: {x_price:.2f} × {u_price:.4f} ÷ {OZ2G} = {rmb:.2f}')
