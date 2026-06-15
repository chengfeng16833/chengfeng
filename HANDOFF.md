# 交接文档 — 在新机器(笔记本)上继续 Starsavior Trainer

> 写于 2026-06-14。给笔记本上的新会话(Claude)+ 用户看。
> 项目已全部推到 GitHub: https://github.com/chengfeng16833/chengfeng (master 分支)。
> **新会话开始前请先读: 本文件 + `协作守则.md` + `docs/superpowers/plans/2026-06-14-flow-state-machine.md`。**

---

## 0. 一句话状态

截图驱动的《星之救世主》PC 自动养成 bot。**已能在台式机(2560×1440)上无人值守跑完整整一局**(赛前→训练循环→D-DAY→终局),今天刚修完十几个实跑卡点 + 上线提速全家桶 + 采集模式。下一步大工程是按 FlowGuard 蓝图加流程状态机根治误判。

---

## 1. 笔记本环境搭建(按顺序)

```powershell
# 1) 克隆
git clone https://github.com/chengfeng16833/chengfeng.git
cd chengfeng

# 2) Python: 需 3.12(台式机用的 3.12.13)。笔记本若没有, 装 3.12。
#    注意: 台式机用的是 codex-runtime 自带 python, 笔记本用你自己装的 python 即可。
python --version   # 确认 3.12.x

# 3) 装依赖(paddle 较大, 首次几分钟; 国内加 -i 清华镜像)
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4) PaddleOCR 模型: 首次运行会自动下载到 ~/.paddlex/(几十 MB), 联网即可。

# 5) 自检: 跑测试(应 450 全绿)
python -B -m unittest discover -s tests
```

依赖说明见 `requirements.txt`:winsdk/keyboard/opencv 是可选(缺了优雅降级,不崩)。
**winsdk 强烈建议装**(混合 OCR 提速 35-60×);缺它会自动退回纯 Paddle(慢但能跑)。

---

## 2. ⚠️ 第一件事:分辨率/坐标重校准(最大的坑)

**所有按钮/区域坐标都是 2560×1440 校准的**(`config/regions/2560x1440.json`,400+ 区域)。
笔记本游戏窗口**只要不是 2560×1440,坐标全错,点不中**。

- 代码有按窗口尺寸缩放区域的逻辑(`scale_region_profile`),**等比分辨率**(如 1920×1080,16:9)大概率能用,先试;
- 但 UI 在不同分辨率下**布局可能非等比变化**,缩放后仍可能偏 → 要逐画面校准;
- 校准方法(本 session 反复用、几乎一击命中):
  1. `python -B tools/_capture_live.py screenshots/check.png` 抓当前帧(精确标题匹配,非侵入);
  2. `Read` 截图看按钮真实位置;
  3. `python -B tools/_diag_prejourney_frame.py screenshots/check.png` 跑「分类→解析→决策」全管线,看 bot 把画面认成什么、决定点哪;
  4. `python -B tools/_diag_region_ocr.py <图> <区域名>` 单区域 OCR + 裁剪图,定坐标;
  5. 改 `config/regions/2560x1440.json`(或新建笔记本分辨率的 profile),重验。
- **强烈建议**:笔记本第一局用 `--collect` 采集模式跑(见下),它把每个新画面截图存 `screenshots/flow_collect/`,一次性看清所有画面在笔记本分辨率下长什么样、坐标偏多少。

---

## 3. 怎么跑

游戏窗口标题必须含 `StarSavior`,窗口化(非全屏独占),停在「选择旅程」画面起跑最稳。

**标准跑(台式机验证过的命令)**:
```powershell
python -B -m starsavior_trainer.cli.live_loop `
  --window-title StarSavior --use-paddle --hybrid-mode --ocr-engine hybrid `
  --prejourney --character 艾芬黛尔 --interval 1.0 --max-iterations 2000 --execute
```

**采集模式(笔记本第一次跑强烈建议, 攒真实流程图 + 看坐标偏移)**:在上面基础上加 `--collect`。
输出: `screenshots/flow_collect/`(每个新画面截图)+ `logs/flow_map.jsonl`(转移序列)。

关键参数:
- `--character 名字`: 自动从 `config/characters.json` 名册带出**走线(力量/体力)+ 形态(ANOTHER/COSMIC)**,不用手传 build。名册没有的角色回退 balanced(会提示)。
- `--execute`: 真点击。**不加 = 预演**(只识别决策不点, 安全, 笔记本首次建议先预演看决策对不对)。
- 难度: 默认**锁困难**(用户要求只跑困难)。
- `--polite-idle 10`: 礼让模式(你一动键鼠 bot 暂停, 空闲 10s 续), 边用电脑边挂。
- 急停: **鼠标甩到屏幕任一角**(最可靠, 不依赖键盘); 或 F12(需 keyboard 库)。

---

## 4. 当前进度 / 待办

**能跑通**: 赛前全流程(主界面→菜单→难度→选角→职业筛选→刻印→支援卡→旅程起点→入场确认→快转设定)、训练循环、D-DAY(交易/评鉴战/跳过战斗)、终局(旅程结束→结算→全新祝福→最终结果)。450 单测全绿。

**待办(按价值)**:
1. **FlowGuard 流程状态机**(大工程, 蓝图已备: `docs/superpowers/plans/2026-06-14-flow-state-machine.md`)
   — 根治"无状态逐帧瞎猜"导致的误判/卡死。用 `logs/flow_map.jsonl` 采集数据填状态表。**这是下一个主线工程**。
2. **组合圣遗物确诊**: 实跑日志显示组合逻辑从没触发(全走按分数选)。已放宽逻辑+加诊断日志(`relic_options=...team=..attr=..`),但"是否识别出卡面『队员全体』"需要一张**组合圣遗物真帧**才能确诊。下次遇到看日志。
3. **笔记本坐标重校准**(见第 2 节)。
4. **窗口最小化自愈**: 游戏被最小化时 bot 崩(`invalid client rect 0x0`)。可加"检测最小化→自动恢复窗口"健壮性。

---

## 5. 血泪教训 / 关键机制知识(改代码前必看, 否则重蹈覆辙)

**协作铁律**(详见 `协作守则.md`):
- **先抓真帧再改代码**, 别盲改(本项目最贵的教训)。
- **改完代码必须重启 bot**(Python 不热加载, 否则测的是旧逻辑)。
- 卡住时 pause 是安全态(不点击), **多等几帧看是否自愈, 别急着杀**。

**游戏机制(用户确认, 决定策略对错)**:
- **失败率全训练通用**(由疲劳决定): 任一训练卡读到失败率≥30%, 说明全部都高 → **直接回大厅休息**, 换训练是白点。
- **休息**: 有金币**必选 60 金币的冥想室**(回体力多), 30 金币露宿是金币不够时的不得已。
- **训练策略(力量角色)**: 前 12 回合属性给得少、彩圈基本不出 → 任务是**跟支援卡人头练(刷好感)**, 候选只看 力量/韧性; 12 回合后好感满了开始出彩圈 → **主属性彩圈 > 韧性彩圈 > 人头≥4 > 主属性保底**。体力角色把主属性换成体力。
- **目标是 RANK**, 偏科无所谓(一局打满属性上限本就要尽全力, 没法兼顾)。
- **评鉴战**: 打赢直接给奖励画面(无独立胜利结算页), 打输才有"训练失败/重新挑战"页。**只跑困难难度**。
- **人头列**: 是"当前选中训练"共享的固定列(右上), 只能读选中卡 → 前期策略靠**轮询逐个选中读人头数**比较。
- **支援卡/卡组/好友卡**: 用户**人工配置**, bot 在支援卡画面永远直接点「旅程起点」, 不碰卡组。

**识别的坑(已修, 别改回去)**:
- 多画面**共用标题**「旅程起点」(选角/刻印/支援卡)→ 必须 hybrid(视觉)区分, 纯 OCR 分不开。
- 高亮/选中的卡名 OCR 会乱码 → 别名留最稳片段; 终局标题"目标/全新祝福"OCR 把字读错 → 用中段稳片段。
- 快引擎(WinRT)会**自信地读错中文小字**(conf=1.0 不触发回退)→ payload 精读固定用 Paddle, 只分类用快引擎。
- 一堆"确认弹窗/结算页"被蓝键 fallback 误判成快转设定 → 各自加专属锚 priority=1 抢先。
- **精准单点防误触**: 确认类画面点 1 次→验是否切→没切才补点, 绝不在切换瞬间盲点连发(鼠标多点极易触发下个界面)。剧情类才 0.5s 间隔慢连点。
- **unknown 转场只点底部中央继续位, 永不点屏幕中心**(中心是角色立绘/危险区, 点了误触菜单)。
- 精确窗口标题匹配: 桌面开着含 "starsavior" 的文件夹窗口会被截胡 → `find_window` 已改精确相等优先。

---

## 6. 关键文件地图

| 文件 | 作用 |
|---|---|
| `starsavior_trainer/cli/live_loop.py` | 主循环(截图→分类→解析→决策→执行→等待 + 采集/礼让/看门狗/burst) |
| `starsavior_trainer/classifier.py` | 画面识别(三级锚金字塔 `_HOT_ANCHORS`/`_FAST_ANCHORS` + `_has_X_signature` 签名) |
| `starsavior_trainer/screen_reader.py` | OCR 解析 `parse_X`(各画面 payload) |
| `starsavior_trainer/policy.py` | 决策 `decide_X` + 训练/圣遗物/事件/休息策略 + `PolicyConfig`(阈值/坐标) |
| `starsavior_trainer/screens/__init__.py` | 画面注册表 HANDLERS(每画面 anchor/parse/decide 三件套) |
| `starsavior_trainer/prejourney.py` | 赛前流程决策(难度/职业筛选/刻印/支援卡) |
| `starsavior_trainer/ocr.py` | OCR 引擎(Paddle/WinRT/Hybrid 混合) |
| `config/regions/2560x1440.json` | **所有坐标**(笔记本不同分辨率要校准这里) |
| `config/characters.json` | 角色名册(走线+形态自动带出) |
| `config/profiles/` | 训练/事件/商店/技能 数据库 |
| `tools/_*.py` | 调试工具(抓帧/裁剪/单帧诊断/区域OCR), 见第 2 节 |
| `docs/superpowers/plans/2026-06-14-flow-state-machine.md` | **FlowGuard 状态机蓝图(下一步主线工程)** |
| `docs/prejourney-flow.md` | 赛前流程知识(整理自用户 docx) |
| `STATUS.md` / `协作守则.md` | 历史进度盘点 / 协作约定+血泪复盘 |

---

## 7. 新会话怎么接手(给笔记本上的 Claude)

1. 读本文件 + `协作守则.md` + FlowGuard 蓝图。
2. 跑 `python -B -m unittest discover -s tests` 确认 450 全绿(环境 OK)。
3. 确认笔记本游戏分辨率 → 若非 2560×1440, 先按第 2 节校准(或新建 profile)。
4. **先预演**(不加 `--execute`)跑几帧看决策对不对, 再真跑。
5. 真跑用 `--collect` 采集 + 全程值守(抓帧诊断卡点 → 改代码 → 重启), 像本 session 一样小步修。
6. 分工: 用户跑/授权, 你诊断+改; 危险操作(真点击/推送)先确认。
