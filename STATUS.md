# Starsavior Trainer — 真实进度盘点

> 最后更新：2026-05-26 · 基于代码现状核对（screens/ · config/regions/2560x1440.json · tests/ · policy.py · screen_reader.py）
> 取代旧版 TODO.md 的进度描述。本文不包装，有问题如实写。

---

## 1. 画面进度总览

图例：✅完成 · ⚠️部分/未验证 · ❌未做 · N/A不适用

| 画面 (Screen) | 区域坐标 | parser | decide | handler注册 | 攻略表/事件库 | 实跑验证过 |
|---|---|---|---|---|---|---|
| INITIAL | ✅ | ✅(内联) | ✅ | ✅ | N/A | ⚠️ |
| CHARACTER_SELECT | ✅ | ✅ | ✅ | ✅ | ✅ characters.json | ⚠️ |
| BLESSING_SETUP | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| BLESSING_CHOICE | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| JOURNEY_START | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| CONFIRM_DIALOG | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| EVENT_FAST_FORWARD_SETTING | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| DIALOGUE | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| TRAINING_HUB | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| TRAINING_SELECT | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| EVENT_CHOICE | ✅ | ✅ | ✅ | ✅ | ✅ events.json(22事件) | ⚠️ |
| COMMISSION_SELECT | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| POST_TRAINING | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ |
| RELIC_CHOICE | ✅ | ✅ | ✅ | ✅ | ❌ relic_combos.json未接入 | ⚠️ |
| REST_SUBMENU | ✅ | ✅ | ✅ 两步+选项规则 | ✅ | N/A | ⚠️ 仅静态/单测 |
| SHOP | ⚠️ 未核对 | ✅ | ✅ | ✅ | N/A | ❌ |
| BATTLE | ⚠️ 未核对 | ✅ | ✅ | ✅ | N/A | ❌ |
| REGION_MOVE | ⚠️ 未核对 | ✅ | ✅ | ✅ | N/A | ❌ |
| SKILL_SELECT | ⚠️ 未核对 | ✅ | ⚠️ 规则待补 | ✅ | N/A | ❌ |

**列说明（重要，避免误读）：**
- **区域坐标**：✅ = 已用真实截图校准并 OCR 验证过；⚠️未核对 = JSON 里有坐标但**是估算值**，没拿真实截图核对过，可能点偏。
- **parser / decide / handler**：全 19 画面都已实现并注册（阶段2注册表）。SKILL_SELECT 的 decide 只是基础框架，**没有完整决策规则**（潜质学什么、何时触发都没定）。
- **实跑验证过**：这一列**整体偏弱，请重点看**。
  - ⚠️ = 仅用**静态截图**跑通了"分类→解析→决策"，或在**早期一次旧实跑日志**里出现过；但**没有**在当前代码状态下的**持续干净实跑**里确认。
  - ❌ = 从未以任何形式验证过（无截图验证、无实跑）。
  - **没有任何画面是 ✅**：因为目前**没有一次确认成功的完整 run**（详见第 3 节）。

---

## 2. 已完成的基础设施

- ✅ **日志体系（阶段1）**：`logging_setup.py`，控制台 INFO + `logs/YYYY-MM-DD.log` DEBUG，UTF-8；13 处静默吞错误改为 debug 日志；关键决策点（分类/决策/点击）INFO 日志。
- ✅ **画面注册表（阶段2，委托式）**：`screens/base.py`(协议) + `screens/__init__.py`(HANDLERS 19画面 + ANCHOR_HANDLERS 有序9签名)。classifier/policy/live_loop 已去掉硬编码 if/elif，统一走注册表。注：现有画面逻辑仍物理留在 screen_reader/policy（委托转发），物理搬迁延后。
- ✅ **颜色检测收口（阶段3）**：7 个像素/颜色检测函数收口到 `vision.py`，14 个颜色阈值常量提取+注释；screen_reader 别名重导出保持兼容。
- ✅ **单元测试 148 个**（`pytest tests/ -v` 全过，0.8 秒）：
  - policy 50（决策规则：训练/事件/委托/休息/选角/祝福/遗物等）
  - screen_reader 69（各画面 parser）
  - classifier 18（画面分类/签名）
  - regions_and_vision 6、blessing_inspector 3、executor 2
  - 注：测试用**假 OCR/合成数据**，不跑真实 PaddleOCR；覆盖"逻辑正确性"，**不覆盖真实截图识别准确率**。
- ✅ **离线 harness**：demo 模式（内置观测）+ manifest 模式（标注数据）均可跑；三次重构均用它做字节级回归对比。
- ⚠️ **攻略表/事件数据库使用情况**：
  - ✅ `config/events.json`（22 事件 + 每事件 default_rules）：**已接入** decide_event（按 build profile 选推荐项 + OCR 标题模糊匹配）。
  - ✅ `config/characters.json`（45 角色 + 职业→培养方向）：**已接入** GUI 选角下拉。
  - ❌ `config/relic_combos.json`：**无代码加载**（遗物决策目前只按分数）。
  - ❌ `config/event_timeline.json`：**无代码加载**（事件出现时间表，纯参考）。
  - ❌ `screenshots/事件/*.png`：你做的事件攻略**表格截图**（非游戏画面），是 events.json 的来源参考，未被代码直接使用；且部分事件**标题与实机 OCR 对不上**（见风险）。
- ✅ **live capture 接入**：`live_loop.py` 用 `capture_window` 截图 → 分类 → 解析 → 决策 → `executor.execute` 点击。支持 dry-run / execute / hybrid / blue 模式。
- ✅ **GUI 控制台**：`cli/gui.py` 分页式，集成训练循环/截图/标定/离线测试/单元测试。
- ✅ **Git**：已建仓 + 3 个阶段提交 + 2 个备份分支（backup-before-refactor / backup-before-phase2）。

---

## 3. 主流程实跑状态

- **live capture 已接入** ✅：代码层面 截图→分类→决策→点击 闭环完整，可 dry-run 也可 execute。
- **是否跑过完整 run？** ❌ **没有确认成功的完整 run。**
  - 你做过**至少一次实跑**：走通了赛前流程（选角→祝福→入场→快转→对话），然后训练后**自动接上事件/委托**时出问题。
  - 那次暴露的事件/委托 bug（卡住/点错/识别错/选错项）**已在本会话修复**（事件底部对齐校准 + 委托分类修复 + 红字闸门逻辑），但**修复后尚未再做一次实跑确认**。
- **会卡在哪？**（基于代码推断，未实测）
  - **耐力耗尽时**：训练失败率 ≥ 阈值后，当前逻辑是"转选次优训练"，若所有训练都超阈值则 `pause`——**不会自动回主界面去休息**（跨画面"高失败率→休息"导航未实现）。这是最可能的卡点。
  - **遇到 SKILL_SELECT（潜质）画面**：决策规则缺失，可能 pause 或乱点。
  - **遇到 REST/SHOP/BATTLE/REGION_MOVE**：坐标是估算值未核对，可能点偏。
- **已知实跑 bug：**
  - 训练后事件/委托处理 → **已修**（本会话），待实跑复验。
  - 其余未知（因为没有干净完整 run 的日志）。

---

## 4. 剩余工作（按优先级）

### 🔴 本周必须做完（阻塞主流程跑通）
| 任务 | 工作量 | 依赖 |
|---|---|---|
| 一次**干净完整实跑验证**（赛前→训练循环→事件→委托 连续跑，看卡在哪） | 大 | 下面几项 |
| **REST_SUBMENU 坐标用真实截图核对 + 验证**（休息是耐力管理刚需） | 中 | — |
| **REGION_MOVE 坐标核对**（流程推进必经） | 小 | — |
| **高失败率→休息 的跨画面导航**（耐力耗尽时回主界面休息，否则会卡 pause） | 中 | REST 校准 |

### 🟡 本周尽量做（不阻塞，但价值高）
| 任务 | 工作量 | 依赖 |
|---|---|---|
| SHOP 坐标核对 + 验证 | 中 | — |
| BATTLE（评鉴战）实跑验证（有截图，parser 已有） | 中 | — |
| 彩环逐卡检测（训练质量；现在整块面板检测，5 卡同值） | 中 | — |
| events.json 事件标题对齐实机（部分标题对不上 → 回退关键词，次优） | 中 | — |

### ⚪ 可延后（已记入 REFACTOR.md）
| 任务 | 工作量 |
|---|---|
| 阶段2遗留：19 画面 parser/decide 物理搬迁到各 handler 文件 | 大 |
| SKILL_SELECT 决策规则（需截图+规则，目前完全没有） | 中 |
| 属性名映射统一（power/speed↔力量/保护 易误导） | 中 |
| 拆 screen_reader.py、魔法数字集中、bat 路径硬编码、capture.py except 日志 | 小~中 |

---

## 5. 风险提示（影响本周完成主脚本）

1. **"实跑验证"整体是最大空白**：没有一次确认的干净完整 run。坐标多为**静态截图校准**，实机的 DPI 缩放、窗口分辨率、动画时序（过场/加载）可能让点击偏位或时机错位——单元测试**完全覆盖不到**这类问题。
2. **耐力耗尽会卡死**：高失败率时没有"回主界面休息"的跨画面逻辑，所有训练超阈值就 `pause`。一旦实跑到中后期耐力低，大概率卡在这里。**这是本周最该先堵的洞。**
3. **4 个画面坐标未经真实截图核对**（SHOP/BATTLE/REGION_MOVE/SKILL_SELECT）：实跑到这些画面可能点偏或识别失败。其中 REGION_MOVE 是主流程必经，优先级高。（REST_SUBMENU 已于 2026-05-26 用真实截图校准 + 两步休息逻辑修复，但仍仅静态截图/单测验证，未实跑确认。）
4. **SKILL_SELECT 决策规则完全缺失**：若潜质画面在实跑中出现，行为不可控。
5. **events.json 部分标题与实机 OCR 不一致**：这些事件会回退到关键词启发式（次优但不崩）；想精确需逐个对齐标题。
6. **OCR 准确率未知**：测试用假 OCR，真实 PaddleOCR 在实机上的识别率（尤其中文小字、失败率数字）没有系统评估过。
7. **screenshots/ 不在 git 备份**（.gitignore 忽略）：你收集的截图和事件攻略表格一旦丢失无法从 git 恢复，建议单独备份。

---

> 一句话总结：**代码骨架（19画面全有 parser/decide/handler + 注册表 + 日志 + 事件库接入）已相当完整，但"能不能在真实游戏里连续跑通一局"尚未验证过——本周重点应是实跑打通 + 堵住耐力耗尽卡死，而不是再加新功能。**
