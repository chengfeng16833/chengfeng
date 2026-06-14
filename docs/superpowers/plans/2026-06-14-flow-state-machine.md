# FlowGuard 流程状态机蓝图(2026-06-14)

> 来源: 多 agent workflow(10 agent 并行审计 33 画面 + 4 子流程 + 综合)产出。
> 用户拍板: **先用 `--collect` 采集真实完整流程**(补全评鉴战胜利/休息/盲区画面),
> 再用真实数据校准本蓝图的 STATE_TABLE, 然后按"步骤0→6"增量实施。
> 根治目标: 今天实跑的 15+ 次误判/卡死(无状态逐帧瞎猜导致)。

## 定位: 不改现有文件的"夹层"

现链路: `live_loop` → `classify_hybrid()` → `policy.decide()` → `HANDLERS[screen].decide()`(无状态逐帧)。
FlowGuard = 新模块 `starsavior_trainer/flow_guard.py`, 只在 live_loop 加约 6 处调用点夹进去;
HANDLERS/classifier/policy/models **一行不动**。可直接复用:
- `classifier._read_anchor_regions(image, profile, ocr, names=(...))` — 按需只读收窄锚集(快验基础)
- `ANCHOR_REGIONS_BY_SCREEN` — 每画面→该读哪些锚(现成映射)
- `Observation.source` — 复核结果写 `source="flowguard"` 便于日志区分

## 状态定义: FlowState(流程节点, 非每画面一状态)

每个 FlowState 声明四个集合:
- `expected_next`: 预期紧接的画面(快验优先)
- `self_loop`: 允许停本画面自循环(INITIAL 两步、找角色滚动、TRAINING_SELECT 逐卡检视、两步弹窗)
- `interrupts`: 全局随时可插入、不算异常(GAME_MENU/CONFIRM_DIALOG/SKIP_BATTLE_CONFIRM/REWARD/DIALOGUE/GOAL_LIST/REGION_MOVE/EVENT_CHOICE/RELIC_CHOICE)
- `forbidden`: 流程上不可能到达、出现即判误判(**否决自信误判的核心**)

关键状态表(节选, 覆盖今天卡死区; 完整表用采集数据补全):

| FlowState | Screen | expected_next | forbidden(否决用) |
|---|---|---|---|
| ROUTE_INITIAL | INITIAL | CHARACTER_SELECT | TRAINING_HUB, JOURNEY_START, SUPPORT_* |
| CHAR_SELECT | CHARACTER_SELECT | FILTER_DIALOG, BLESSING_SETUP | **SUPPORT_***, JOURNEY_START, TRAINING_*, BATTLE, REWARD |
| JOURNEY_START_ST | JOURNEY_START | CONFIRM_DIALOG | **CHARACTER_SELECT**(今天死循环源), TRAINING_* |
| IN_RUN_HUB | TRAINING_HUB | TRAINING_SELECT, REST_SUBMENU, COMMISSION_SELECT, SHOP, BATTLE, DIALOGUE | MAIN_*, INITIAL, CHARACTER_SELECT, BLESSING_*, JOURNEY_START, SUPPORT_* |
| BATTLE_FLOW | BATTLE | BATTLE_RESULT, GOAL_LIST, SKIP_BATTLE_CONFIRM | **EVENT_FAST_FORWARD_SETTING**(否决"确认弹窗→快转"), TRAINING_SELECT |
| FAIL_RESULT_ST | BATTLE_RESULT | TRAINING_HUB, GOAL_LIST, JOURNEY_END | **TRAINING_SELECT 直跳**(否决"FAIL页→大厅点空白") |

## 识别策略: 三段式

- **Phase A 预期快验**: 取 `current_state` 的 expected_next∪self_loop∪interrupts → 合并成收窄锚集 → 只 OCR 这一小撮 → 命中即返回(比 _HOT_ANCHORS 还窄且语义对路 = 快+准)。
- **Phase B 预期落空回退**: A 没命中 → 原样调 `classify_hybrid`(全套指纹+OCR金字塔+视觉劈分), 能力不退化。
- **Phase C 流程否决**: 候选 ∈ forbidden → 拒绝 → ①取预期内次优命中 / ②强制纯Paddle复核(复用现有看门狗通路) / ③仍 forbidden 返回 UNKNOWN, 绝不喂 decide。

对照今天三大卡死的否决路径:
- 支援卡→character_select: JOURNEY_START_ST 禁 CHARACTER_SELECT → 不进滚动找人 → 根治死循环
- FAIL结算→大厅点空白: BATTLE_FLOW/FAIL_RESULT_ST 禁 TRAINING_SELECT 直跳 → 触发复核
- 确认弹窗→快转设置: 非"刚点快转入口"的态禁 EVENT_FAST_FORWARD_SETTING → 蓝键误判被拒

## 转移更新

decide 之后、execute 之前算转移("刚点了训练"才能预期"下一帧 TRAINING_SELECT")。
**数据驱动**: 靠下一帧实际识别的画面驱动转移(不硬编码"点了什么"), 状态机与识别互为印证。
interrupts 记 `return_state`, 弹窗处理完回主干。识别到 INITIAL/CHARACTER_SELECT → reset()(对齐 round_tracker)。

## 增量实施步骤(每步可独立测试绿, 不破坏现有整局)

0. **纯新增零风险**: 建 flow_guard.py + test_flow_guard.py。只实现 FlowState 枚举 + STATE_TABLE + 纯函数 is_forbidden/is_expected/next_state。表驱动测试覆盖今天三类卡死否决。不改任何现有文件。
1. **影子模式(不改判定)**: live_loop 加 guard.observe() 只写 logs/flow_transitions.jsonl + 打印 state/expected/forbidden, 绝不改 observation/decide。实跑一局核对标记与真实卡死点是否吻合(校准 STATE_TABLE)。可随时回滚。
2. **开启否决(降级到现有兜底)**: forbidden 命中 → 复用现有 force_detailed_classify(纯Paddle复核, 已测试过的路径)。用静态截图测试否决/放行。
3. **预期快验提速(独立开关 --flow-fast)**: Phase A 收窄锚集, 命中即返回否则回退。mock OCR 计数验证省了金字塔。
4. **转移驱动 + interrupts 来路记忆**: 弹窗处理完回主干态。序列回放测试。
5. **调试截图 + 配额**: veto/unexpected/连续否决时存 screenshots/flow/(配额防写爆)。
6. **全程实跑验收**: --flow-fast 跑完整局, 对照 flow_transitions.jsonl 确认 15+ 卡死不复现; 误否决只调数据表不改逻辑。

## 调试可观测性

logs/flow_transitions.jsonl 每次转移一行: ts/iteration/from_state/to_state/screen/confidence/source/phase/unexpected/vetoed_screen/veto_reason/round。
截图仅在 veto/unexpected/连续否决 时存(带配额), 正常转移不存(省IO), 误判帧自动攒进调试库。

## 与采集数据的衔接

本蓝图的 STATE_TABLE 基于**现有 33 画面**设计 → 必有盲区(评鉴战胜利、休息全流程、未知画面)。
`--collect` 跑出的 `logs/flow_map.jsonl`(真实转移序列)+ `screenshots/flow_collect/`(真实画面)
= 校准/补全 STATE_TABLE 的权威数据。**先采集, 再填表, 后实施**。
