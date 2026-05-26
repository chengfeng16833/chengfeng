# Starsavior Event Database

This is the document-first event database collected during intake mode. It is
not executable code yet.

Purpose:

- Record event titles, option text, known effects, and recommended choices.
- Preserve screenshots/rules provided by the user so implementation does not
  depend on chat history.
- Later convert stable entries into a structured data file or policy table.

Current source status:

- User-provided screenshots and rules are the primary confirmed source.
- User-provided Tencent Docs sheet:
  `https://docs.qq.com/sheet/DSVBESGNncW5oVEJx`
- Tencent Docs title was read as:
  `Star Savior困难跑马＆支援卡事件查询表`
- Tencent Docs public read API exposes compressed sheet data and is currently
  the best correction source for event titles/options/effects.
- User-provided Bilibili opus:
  `https://www.bilibili.com/opus/1182617076046495767?spm_id_from=333.1387.0.0&jump_opus=1`
- Direct Bilibili public API access currently returned anti-bot error `-352`.
- A GameKee event article was located as a likely mirror/reference:
  `https://www.gamekee.com/starsavior/697126_309610.html`
- The GameKee page is rendered as a SPA, but search/browser indexing exposed
  readable text. Imported rows below should be treated as external-guide data
  until verified against in-game screenshots.

## Web Extraction Progress

Date: 2026-05-15.

Skill/tool path tried:

- Loaded the Browser skill and used the in-app browser against the GameKee page.
- Bilibili opus direct extraction is currently blocked by anti-bot behavior, so
  the Bilibili link remains a source pointer rather than an extracted source.
- GameKee page DOM exposes readable table rows, including event timing, title,
  option, cost/gate, reward, and negative effect columns.
- Images from the guide have not been imported yet. For now, the database should
  rely on event titles/options/effects; screenshots can be attached later if
  needed for OCR anchors.

External reference currently usable:

- [GameKee: 救援之旅全难度事件及奖励](https://www.gamekee.com/starsavior/697126_309610.html)
- [Tencent Docs: Star Savior困难跑马＆支援卡事件查询表](https://docs.qq.com/sheet/DSVBESGNncW5oVEJx)

Clean rows successfully observed from the webpage:

```text
困难 / 3月上旬 / 评价赛准备
1. 平衡天平: 攻击受伤-3% / 被击增伤+3% (10层)
2. 布谷鸟钟: 基础攻击命中后 100% 几率挂毒
3. 人偶遗留图腾: [XX2号] 普攻获盾；HP吸收率+15%

困难 / 3月中旬 / 物资补给
1. 满意度调查表 (力): 力量+10, 回合开始加算速度
2. 满意度调查表 (生): 生命+10, 回合开始加算速度
3. 满意度调查表 (体): 体力+10, 回合开始加算速度

困难 / 3月中旬 / 闲暇时间
1. 限量甜点: 古币 -100; 状态 +1, 潜在点 +20
2. 观看电影: 古币 -60; 特典海报 (初始速+5%), 潜在点 +30/60
3. 郊外野餐: 耐力 -40; [力量/生命/体力 +20] + [保护/专注 +10]

困难 / 3月中旬 / 神秘石像
1. 向剑祈祷: 力量+20, 体力-20, 石像之剑
```

Clean rows successfully observed from Tencent Docs:

```text
三月中旬（随机事件） / 自由时间
1. 咱们去吃个期间限定的甜点吧
   cost: 消耗旧硬币50
   reward: 心情+1或心情+2; 技能点+10
2. 我们去看最新的电影吧
   cost: 消耗旧硬币30
   reward: 潜在要点+15或+30; 获得「特别海报」
3. 拿个三明治去野餐吧
   cost: 体力 -20
   reward: 力量/生命/耐力+10 or +20; 命中/命抗+5 or +10
4. 今天就这样休息吧
   reward: 体力+5 or +10

三月中旬（随机事件） / 拯救集团供应
1. 让我们选择食物。
   reward: 力量 +10; 获得「满意度问卷」
2. 让我们选择一个蓬松的枕头
   reward: 生命 +10
3. 让我们选择辛辣食物
   reward: 耐力 +10

三月中旬（随机事件） / 神秘石像
1. 我向剑祈祷。
   reward: 力量 +20; 生命 -20; 获得「石像之剑」
2. 为鲜花祈祷。
   reward: 力量 -20; 生命 +20; 获得「石像之花」
3. 我不祈祷。
   reward: 无
```

Implementation note:

- These rows should become structured event data later, but while intake mode is
  active they stay as Markdown.
- Because the guide uses reward names rather than in-game option sentences in
  some rows, OCR matching may need both event-title matching and fuzzy option
  aliases.

## Event Entry Format

Each event should be recorded with:

- `event_id`: stable English id for code/data later.
- `title`: exact OCR title shown in-game.
- `category`: route event, post-training event, camp event, shop event, etc.
- `trigger`: when this event appears.
- `options`: exact option text in display order.
- `known_effects`: observed or sourced result for each option.
- `recommended_choice`: rule for choosing an option.
- `fallback`: what to do if the build or OCR is unclear.
- `sources`: screenshot, user rule, external guide, or unknown.
- `status`: confirmed, partially confirmed, or needs verification.

## Generic Event Choice Priority

When an event is not in this database and the option effects can be inferred
from OCR text, use the broad fallback priority:

1. Recover stamina / body.
2. Recover or improve mood / `心情`.
3. Gain useful attributes.

Important: fixed events in this database override the generic priority.

## Known Events

### training_direction

- `title`: `训练的方向性`
- `category`: fixed post-first-training event
- `trigger`: appears after completing the first training
- `status`: confirmed by user screenshot and user rule

Options:

1. `对攻击有帮助的训练教材`
2. `对生存有帮助的训练教材`
3. `有助于应对各种状况的训练教材`

Recommended choice:

- Attack/power build: choose option 1.
- Life/stamina build: choose option 2.
- Balanced/unknown build: not confirmed; safest behavior should be configurable
  or pause until user chooses a default.

Notes:

- Option text is literal enough to classify directly.
- This event should be handled before generic event priority.

Sources:

- User screenshot.
- User rule: first option for attack characters, second option for life
  characters.

### rescue_supply

Correction note: this older entry was originally based on screenshot wording and
GameKee guide wording. Tencent Docs corrects the canonical title/options/effects
in `rescue_supply_corrected` below. Treat this old entry as an alias/reference
only.

- `title`: `救援团补给`
- `aliases`: `物资补给`
- `category`: route event
- `trigger`: appeared on `3月中旬`, after the first training-direction event in
  the observed run
- `status`: partially confirmed by user screenshot, effects sourced from
  external guide

Observed dialogue:

`NOA的补给品送到了。但因为预算不足，只能使用其中一样。`

Options:

1. `选营养剂吧。`
2. `选蓬松的枕头吧。`
3. `选香辣的食物吧。`

Known effects:

- Option 1: `满意度调查表 + 力量 +10`.
- Option 2: `满意度调查表 + 生命 +10`.
- Option 3: `满意度调查表 + 体力 +10`.

Recommended choice:

- Attack/power build: choose option 1.
- Life/stamina build: choose option 2.
- If current need is stamina/body or build is unclear, option 3 may be useful,
  but default is not confirmed.

Fallback:

- Pause or choose configured default until effects are confirmed.

Sources:

- User screenshot.
- GameKee external guide row for `物资补给`.

### rescue_supply_corrected

- `title`: `拯救集团供应`
- `aliases`: `救援团补给`, `物资补给`
- `category`: route random event
- `trigger`: `三月中旬（随机事件）`
- `status`: corrected by Tencent Docs sheet; partially confirmed by user
  screenshot

Observed dialogue:

`NOA的补给品送到了。但因为预算不足，只能使用其中一样。`

Options and effects:

1. `让我们选择食物。`
   - reward: `力量 +10`, `获得「满意度问卷」`
2. `让我们选择一个蓬松的枕头`
   - reward: `生命 +10`
3. `让我们选择辛辣食物`
   - reward: `耐力 +10`

Recommended choice:

- Attack/power build: choose option 1.
- Life/stamina build: choose option 2.
- If current need is stamina/body, option 3 may be useful.
- Sheet note: `自己看角色选`.

Sources:

- User screenshot.
- Tencent Docs sheet row for `拯救集团供应`.

### free_time_march_mid

- `title`: `自由时间`
- `category`: route random event
- `trigger`: `三月中旬（随机事件）`
- `status`: sourced from Tencent Docs sheet

Options and effects:

1. `咱们去吃个期间限定的甜点吧`
   - cost: `消耗旧硬币50`
   - reward: `心情+1或心情+2`, `技能点+10`
2. `我们去看最新的电影吧`
   - cost: `消耗旧硬币30`
   - reward: `潜在要点+15或+30`, `获得「特别海报」`
3. `拿个三明治去野餐吧`
   - cost: `体力 -20`
   - reward: `力量/生命/耐力+10 or +20`, `命中/命抗+5 or +10`
4. `今天就这样休息吧`
   - reward: `体力+5 or +10`

Recommended choice:

- The sheet note says the author's habit is option 4 for stamina.
- Option 2's poster can be valuable if later poster-triggered events happen.
- Final policy should consider coins, stamina, mood, and whether poster synergy
  is still possible.

Sources:

- Tencent Docs sheet.

### mysterious_stone_statue

- `title`: `神秘石像`
- `category`: route random event
- `trigger`: `三月中旬（随机事件）`
- `status`: sourced from Tencent Docs sheet

Options and effects:

1. `我向剑祈祷。`
   - reward: `力量 +20`, `生命 -20`, `获得「石像之剑」`
2. `为鲜花祈祷。`
   - reward: `力量 -20`, `生命 +20`, `获得「石像之花」`
3. `我不祈祷。`
   - reward: `无`

Recommended choice:

- Attack/power build: choose option 1.
- Life/stamina build: choose option 2.
- Unknown build: option 3 or pause, depending on safe mode.

Sources:

- Tencent Docs sheet.

## Imported External Guide Rows

Source: GameKee `救援之旅全难度事件及奖励`.

These rows are imported as guide data, not yet verified against local
screenshots. They should eventually be converted into structured event data with
source and confidence fields.

### Normal Difficulty Samples

| Timing | Event | Option | Cost / Gate | Reward | Negative |
| --- | --- | --- | --- | --- | --- |
| random | 训练失败 | 暂时休息 | none | 耐力 +5 | - |
| random | 训练失败 | 坚持到底 | 耐力 -20 | 潜在要点 +18, 聪明救赎者 | - |
| random | 训练失败 | 使用活力药水 | requires potion | 耐力 +15, 潜在要点 +10 | - |
| random | 意外事故 | auto | very low probability | - | 状态 -1, 耐力 -15, 全属性 -5 |
| random | 初期型强化剂 | 红色药水 | 古币 -20 | 大成功: 全属性 +20 or 耐力 +20 | 魔力脱落, 属性 -10 |
| random | 初期型强化剂 | 蓝色药水 | 古币 -20 | 耐力 +10, 高尔迪乌斯之剑 | 状态 -1 |
| random | 初期型强化剂 | 黄色药水 | 古币 -20 | 潜在要点 +20/30, 古币 +30, 耐力 +10 | 急性低迷 |
| random | 意料外的鼓励 | 汗水不背叛 | 耐力 -10 | 生命/体力 +10, 截止日期 | 过欲 |
| random | 意料外的鼓励 | 再加把劲 | 耐力 -10 | 力量/体力 +5 | - |

### Hard Difficulty Fixed / Scheduled Rows

| Turn | Time | Event | Option | Gate / Cost | Reward | Negative |
| ---: | --- | --- | --- | --- | --- | --- |
| 0 | 开始 | 初始化 | 因子继承 | - | 基础因子, 潜在要点 +7, 初始遗物三选一 | - |
| 1 | 3月上 | 准备阶段 | 剧情回合 | none | 无额外潜在要点补给 | - |
| initial | 初始遗物 | 初始遗物 | 平衡天平 | none | 饰品: 攻击受伤-3%, 被击增伤+3% | - |
| initial | 初始遗物 | 初始遗物 | 布谷鸟钟 | none | 饰品: 普攻命中后 100% 几率挂毒 | - |
| initial | 初始遗物 | 初始遗物 | 蓬松人偶 | none | 饰品: 普攻获盾 | - |
| 2 | 3月中 | 物资补给 | 营养剂 | none | 满意度调查表 + 力量 +10 | - |
| 2 | 3月中 | 物资补给 | 软枕头 | none | 满意度调查表 + 生命 +10 | - |
| 2 | 3月中 | 物资补给 | 辣味食物 | none | 满意度调查表 + 体力 +10 | - |
| 2 | 3月中 | 闲暇时间 | 限量甜点 | 古币 -50 | 状态 +1, 潜在要点 +10 | - |
| 2 | 3月中 | 闲暇时间 | 观看电影 | 古币 -30 | 特典海报, 潜在要点 +15/30 | - |
| 2 | 3月中 | 闲暇时间 | 郊外野餐 | 耐力 -20 | 力量/生命/体力 +10 and 保护/专注 +5 | - |
| 2 | 3月中 | 神秘石像 | 剑祈祷 | none | 力量 +20, 获得石像之剑 | 体力 -20 |
| 2 | 3月中 | 神秘石像 | 花祈祷 | none | 生命 +20, 获得石像之花 | 力量 -20 |
| 4 | 4月上 | 旅程的礼物 | 礼包 A | none | 潜在要点 +7, 补位型遗物奖励 | - |
| 6 | 4月下 | 莉塞特的日常 | 帮忙 | 耐力 -20 | 一日兼职, 古币 +30 | - |
| 6 | 4月下 | 掠夺者讨伐 | 战胜(中级) | battle | 潜在要点 +7, 咖啡券, 防扣10% | 状态 -1 |
| 7 | 4月下 | 基础评价赛 | 目标达成 | settlement | 潜在要点 +7, 因子初步继承 | - |
| 9 | 5月中 | 工坊宣传 | 寻找弱点 | 专注 30/50 | 状态 +1, 仿制剑, 潜在点 +10 on success | 状态 -1 |
| 9 | 5月中 | 工坊宣传 | 以力破法 | 耐力 -20 | 传说救赎者, 仿制剑 | - |
| 9 | 5月中 | 地狱特训 | 拳击/跑步 | 古币 -20 | 对应属性证书 + 对应训练加成 Buff | - |
| 11 | 6月上 | 亲切的礼物 | 属性奖励 | none | 力量/生命/体力 +10 | - |
| 13 | 6月下 | 史莱姆讨伐 | 战胜(中级) | battle | 潜在要点 +15, 属性 +10, 保护折扣 10% | 状态 -1 |
| 14 | 6月下 | 讨伐评价赛 | 因子继承 | settlement | Blue Inh. 继承, 潜在要点 +45 | - |
| 18 | 7月下 | 迷宫探索 | 亲自驾驶 | 保护 50/70 | 体力属性 +15/20, 潜在要点 +15/22 | 状态 -1 |
| 20 | 8月中 | 救命的礼物 | 属性勋章 | none | 力量/生命/体力/保护/专注 +5, 任选其一 | - |
| 27 | 10月中 | 模范的礼物 | 属性奖励 | none | 力量/生命/体力 +10 | - |
| 28 | 10月下 | 脱离兵讨伐 | 战胜(中级) | battle | 潜在要点 +30, 属性 +15, 洞察折扣 10% | - |
| 29 | 10月下 | 竞争评价赛 | 因子继承 | settlement | Blue Inh. 继承, 潜在要点 +45 | - |
| 31 | 11月初 | 排球预赛 | 属性判定 | corresponding gate | 状态 +1, 潜在点 +20/30, 属性加成 | - |
| 33 | 11月下 | 排球决赛 | 属性判定 | corresponding gate | 状态 +1, 潜在点 +20/30, 属性加成 | - |
| 35 | 12月中 | 幸福的礼物 | 属性奖励 | none | 力量/生命/体力 +20 | - |
| 40 | 1月下 | 莉塞特忧郁 | 存钱罐 | requires key | 潜在要点 +22, 速度加成 | 潜在点 +15 if failed/no key |
| 40 | 1月下 | 收藏家现身 | 小绿洲 | requires poster | 提升评分加成 | - |
| 45 | 终点 | 最终赛结算 | 最终评价 | settlement | 星光引导, 属性 +10, 育成结束 | - |

## Events To Import

Target external data source:

- Bilibili opus above, described by the user as containing almost all event
  choices and images.

Import workflow:

1. Capture event title.
2. Capture all option texts in order.
3. Capture effect/outcome for each option.
4. Mark role-specific or phase-specific recommendation.
5. Add screenshot reference if available locally.
6. Mark confidence/status.

Preferred user-provided event data shape:

```text
事件名:
触发时机:
选项1:
效果1:
选项2:
效果2:
选项3:
效果3:
推荐:
截图文件:
```

## Open Questions

- Can the Bilibili opus be exported or copied as text by the user if direct
  browser/API access stays blocked?
- Should unknown/balanced builds pause on fixed role-specific events, or choose
  a configured default?
- Should event database entries live permanently as Markdown, JSON, or YAML once
  implementation begins?
