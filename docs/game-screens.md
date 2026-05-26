# Starsavior Game Screens

This document captures the screenshots and rules described by the user during
intake mode. It is written as implementation reference material, not as code.

Current primary client size: `2560x1440`.

Event choices are collected separately in `docs/event-database.md`.

Important note: the screenshots were provided in chat, not as local files. The
visual descriptions below should be used for rules and screen understanding.
For exact coordinate calibration, save original screenshots locally later.

## Working Strategy

- During intake mode, record screenshots and rules here or in `TODO.md`.
- Do not implement code until the user says the requirements are complete.
- When implementation starts, classify the current screen first, then OCR only
  that screen's relevant region prefix. Avoid all-region OCR because it can
  make PaddleOCR appear to freeze.

## 1. Route Select / Initial

Observed screenshot:

- Top-left title: `选择旅程`.
- Route number: `001`.
- Route name: `星光引导者`.
- Difficulty selector at bottom-right: `简单`, `一般`, `困难`.
- Active difficulty in the screenshot: `困难`.
- Bottom-right blue button: `开始`.

Flow:

- Click `开始`.
- Next screen is character selection / journey origin.

Implementation notes:

- Current model uses `Screen.INITIAL` for this screen.
- OCR anchors: `选择旅程`, `星光引导者`, route number `001`.
- Click target: `开始` button.

## 2. Character Select / Journey Origin

Observed screenshot:

- Top-left title: `旅程起点`.
- Left side shows selected character details and stats.
- Right side shows scrollable character list.
- Bottom-right blue button: `选择`.
- Example selected character in screenshots: `贝尔・莉丝`.
- Example route summary bottom-left: `星光引导者`, difficulty `困难`.

Flow:

- If the desired/selected character is already selected, click `选择`.
- Otherwise click the desired character in the list, then click `选择`.
- Next screen is blessing setup.

Implementation notes:

- Selected character can be inferred from the large left-side character panel
  or from the highlighted list item.
- Character list OCR may need names, rank/grade, specialty, and selected state.

## 3. Blessing Setup

Observed screenshot:

- Still under top-left title `旅程起点`.
- Character shown large in center/right.
- Left stats show attributes such as `力量`, `体力`, `韧性`, `专注`, `保护`.
- Two blessing slots appear as dark card-shaped slots with `+`.
- Bottom-right buttons include `自动装备`, search icon, and disabled/enabled
  `确认`.

Rules from user:

- Blessings increase character attributes.
- Strength/power characters should receive more `力量`.
- Stamina/tank characters should receive more `耐力` or equivalent stamina
  blessing.

Flow:

- Open the first empty blessing slot.
- Choose a blessing from the blessing archive.
- Repeat for the second slot.
- When both slots are filled and `确认` is enabled, click `确认`.
- Next screen is Arcana / journey start.

Implementation notes:

- Need to detect empty vs occupied blessing slots.
- Need to read current character build direction from config/state, not from
  this screen alone.

## 4. Blessing Choice / Star Archive

Observed screenshots:

- Top-left section label: `星辰档案`.
- Top filter/dropdown shows `能力值祝福`.
- Blessing cards show:
  - main attribute text such as `力量:45`, `力量:35`, `体力:35`
  - numeric score below portrait, such as `8,657`, `8,442`, `5,845`
  - rank badge such as `A`, `B+`, `B`
- Right detail panel shows selected blessing name and blessing icons.
- Bottom-right blue button: `确认`.

Rules from user:

- There are two blessing slots.
- Single blessing max value is `50`.
- Higher value is better.
- Power/strength characters prefer `力量`.
- Stamina/tank characters prefer `耐力` / stamina.
- If main attribute and value tie, prefer the one with more small/sub
  blessings.
- Example:
  - A `力量:35` blessing without a small blessing is worse than a `力量:35`
    blessing with a small blessing.

Flow:

- Pick best matching blessing.
- Confirm.
- Return to blessing setup.

Implementation notes:

- Need OCR for card attribute/value.
- Need visual or OCR detection for sub-blessing icons on the right detail panel.
- Card score under portrait is not the primary selection rule for blessing;
  main attribute value and sub-blessing count matter more.

## 5. Arcana / Journey Start

Observed screenshot:

- Still under top-left title `旅程起点`.
- Arcana cards are shown on the right.
- Bottom-right blue button: `旅程起点`.
- Adjacent button: `自动旅程`.
- Bottom-left route summary still shows `星光引导者`.

Rules from user:

- Arcana card setup is basically fixed.
- Ignore the Arcana cards for now.
- Click `旅程起点`.

Flow:

- Click `旅程起点`.
- Entry confirmation dialog appears.

Implementation notes:

- Do not implement Arcana optimization yet.
- Treat this as a fixed pass-through screen.

## 6. Entry Confirm Dialog

Observed screenshot:

- Modal title: `入场确认`.
- Route name: `星光引导者`.
- Difficulty badge: `困难`.
- Message: `是否要进行旅程?`
- Buttons: `取消`, `确认`.

Rules:

- Click blue `确认`.

Flow:

- After confirming, event fast-forward setting appears.

Implementation notes:

- OCR anchors: `入场确认`, route name, `是否要进行旅程`.
- Click target: blue `确认`.

## 7. Event Fast-Forward Setting

Observed screenshot:

- Modal title: `事件快转设定`.
- Three cards:
  - `不快转`
  - `仅快转已观赏的事件`
  - `快转所有事件`
- Blue selected state/checkmark should be on `快转所有事件`.
- Bottom blue button: `决定`.

Rules from user:

- Fixed choice is `快转所有事件`.

Flow:

- If `快转所有事件` is not selected, click that card.
- Once selected, click `决定`.

Implementation notes:

- Visual selected state/checkmark is important.
- OCR anchors: modal title and the three option labels.

## 8. Dialogue / Story Skip

Observed screenshot variants:

1. Full story background:
   - Bright background scene.
   - Top-right text button: `SKIP`.
   - Bottom text area includes location/story text, example `星云观测机构NOA`.

2. Journey HUD dialogue:
   - Main journey HUD remains visible.
   - Top-left shows distance/month/event information.
   - Top-center/top-right has several HUD icons.
   - Skip position is different from the full story background.
   - Example bottom text: `罗莎莉亚获得了 星之祝福!`

Rules from user:

- Always skip all story/dialogue.
- Skip button position can change.

Flow:

- Detect dialogue variant.
- Click the visible/current skip control.
- Continue until gameplay/reward screen appears.

Implementation notes:

- Do not use one global hardcoded skip coordinate.
- Use dialogue variant and screen anchors to choose the correct skip region.
- Some HUD skip controls may be icon-only, so OCR text alone may not work.

## 9. First Relic / Reward Choice

Observed screenshot before selection:

- Top-left title: `选择奖励`.
- Three reward cards:
  - left: `软绵绵的玩偶朋友`
  - middle: `烦人的布谷鸟时钟`
  - right: `平衡的天秤`
- All show score/cost value `12`.
- Left card may have `推荐` label.
- Bottom-center button `选择完成` is disabled/grey.
- Top-right status: `未选择`.

Observed screenshot after selecting middle card:

- Middle card `烦人的布谷鸟时钟` is highlighted with gold glow.
- Bottom-center `选择完成` becomes blue/enabled.
- Top-right still visually shows `未选择` in the provided screenshot, so button
  color is the more reliable confirmation signal.

Rules from current project/user context:

- This first reward screen is fixed.
- Choose the middle card: `烦人的布谷鸟时钟`.
- After it is selected and `选择完成` turns blue, click `选择完成`.

Flow:

- If the fixed relic is not selected, click middle card.
- If the blue `选择完成` button is active, click it.

Implementation notes:

- This screen differs from later generic relic selection.
- Do not use highest score here because all three shown options have score
  `12` and the intended choice is fixed.
- Later relic screens should use their own scoring rules.

## 10. Training Hub / Action Main Screen

Observed screenshot:

- This screen appears after clicking `选择完成` on the first relic reward.
- It is the first layer of the training phase, not the five-training selection
  screen itself.
- The user says this screen contains many values that affect later racing /
  training strategy.

Top-left route and turn area:

- Route/event title: `参加评鉴战`.
- Distance indicator: `距离目标 6`.
- Turn/month text: example `3月上旬`.
- The turn/month value is important and should be OCR-read later.

Top-center status bar:

- A long green/yellow bar represents current stamina/endurance condition.
- User specifically called this the green `耐力` area.
- Yellow face icon with text `NORMAL` represents mood / `心情`.
- Mood / `心情` color order from low to high:
  - red
  - yellow
  - green
  - blue
- Coin icon with number, example `48`, is current coin count.

Left character status panel:

- Shows current `RANK`, example `RANK 13`.
- Shows five attribute rows:
  - `力量`, example `268/1250`, grade `C+`
  - `体力`, example `34/1250`, grade `G+`
  - `韧性`, example `20/1250`, grade `G`
  - `专注`, example `135/1250`, grade `E+`
  - `保护`, example `10/1250`, grade `G`
- Shows `潜质点数`, example `21`.

Right-side action entries:

- `训练`: enters the training-choice screen.
- `委托`: enters commission selection.
- `休息`: enters rest options.

Bottom navigation:

- `潜质`
- `队伍`
- `背包`

Rules from user:

- The values on this screen affect later racing/training strategy.
- Right-side entries are the entrances to their corresponding option screens.
- Need to track turn/month, stamina/endurance bar, mood / `心情`, coins,
  rank/attributes, and potential points.

Flow:

- From this hub, choose the next action according to policy:
  - usually enter `训练` when training is appropriate
  - enter `休息` when stamina/coins/rules require rest
  - enter `委托` when commission logic says to do so
- The exact high-level action policy is not fully specified yet; record more
  user rules before implementing.

Implementation notes:

- This should likely become a separate typed payload later, distinct from
  `TrainingChoice`.
- Possible future model: `TrainingHubStatus` with fields for turn/month,
  distance_to_goal, stamina bar/color/value, mood / `心情` state/color, coins, rank,
  attributes, potential points, and action entry rectangles.
- For OCR/performance, use a `training_hub` region prefix rather than reading
  all regions.
- The screenshot shown in chat includes the PC window title bar; coordinate
  calibration should be done later against saved local screenshots with a
  consistent capture mode.

Open questions:

- Exact rule for choosing among `训练`, `委托`, and `休息`.
- Whether `距离目标 6` means remaining turns/events or a special race countdown.
- How stamina/endurance should be converted from the bar into a numeric or
  categorical state.
- Whether `NORMAL` text is enough for mood, or color/icon should be primary.

## 11. Training Selection Screen

Observed screenshot:

- Entered by clicking `训练` from the Training Hub.
- Left panel keeps current `RANK`, five attributes, grades, and `潜质点数`.
- Top-left still shows route title, distance, and current turn/month.
- Top-center still shows stamina/endurance bar, mood / `心情`, and coins.
- Right side lists five training entries:
  - `力量训练`
  - `体力训练`
  - `韧性训练`
  - `集中训练`
  - `保护训练`
- Each training entry shows a level such as `Lv.1`.
- The selected/current training can show failure rate, example `失败率 0%`.
- Bottom-right blue button: `训练`.
- The left panel shows blue projected stat gains such as `+20`, `+8`, `+25`.
- Bottom center shows training EXP progress, example `133%`.

Random support/bonus icons:

- Icons/heads near the selected training are random.
- These icons represent which support cards/characters are present on that
  training.
- The support head count and bond state matter for strategy.
- Support bond bars can appear under portraits.
- Bond color/state matters because raising bond to orange can unlock colored
  rings / better training.
- Main-attribute support cards have higher bond priority than non-main-attribute
  support cards.

Training stat mapping from user:

- `力量训练`: large `力量` + small `保护`.
- `体力训练`: large `体力` + small `保护`.
- `韧性训练`: large `保护` + small `力量` + small `体力`.
- `集中训练`: large `集中` / hit-related attribute + small `力量`.
- `保护训练`: large `保护` / resistance-related attribute + small `体力`.

Terminology note:

- The user described these as five training types and their stat outputs.
- Earlier project naming may use power/stamina/guts/wisdom/protection; later
  implementation should align the code names with the actual in-game labels.

Strategy rules from user:

- `韧性训练` gives the most complete total three-dimensional stat improvement,
  so running more defense-style training in normal runs is a known strategy.
- In hard routes this is not necessarily wrong, but too much `韧性训练` can leave
  main-attribute training proficiency too low to reach the `1250` cap.
- Stamina management:
  - max stamina is `100`.
  - each training costs `15` stamina.
  - when stamina is below `50`, training failure probability starts increasing.
  - failure rate above `20%` is usually too risky.
  - if failure rate is above `20%`, train only when the value is high enough,
    such as two or more colored rings; otherwise prefer stable rest.
  - The user notes that gambling is sometimes necessary for a very strong run:
    if the gamble fails, restart the run.
- Early rest rule:
  - First 6 turns are not an absolute no-rest rule.
  - Usually coins are limited, so avoid sleeping/resting if training is still
    acceptable.
  - If there are enough coins, prefer the 60-coin meditation-room style option.
  - If early mood is not full and stamina is unsuitable for training, or mood is
    bad but the run is still worth saving, the 30-coin mood-recovery option can
    be chosen.
- Rest/sleep options:
  - Option 1: free/cheap sleep; has a chance to lower mood.
  - Option 2: costs `30` coins; restores `30` stamina and +1 mood stage.
    Great success restores `50` stamina and +2 mood stages.
  - Option 3: costs `60` coins; restores `60` stamina and has a chance to cure
    debuffs. Great success restores `80` stamina and has a chance to cure
    debuffs.
  - Usually choose option 3 to save rest turns and recover more stamina.
- First 12 turns, before the first camp:
  - prioritize `力量训练` and `体力训练`
  - use `韧性训练` as secondary/support
  - first goal is raising bond for support cards matching the main stat
    (`力量` or `体力`)
  - second goal is raising proficiency for the needed main-stat training
- `集中训练` and `保护训练`:
  - consider them when they have 3 or more support heads
  - especially if those supports have not yet reached colored-ring bond state
  - they can also recover a small amount of stamina
- Bond priorities:
  - raising bond to orange enables colored rings
  - main-attribute support card bond has higher priority than non-main supports
  - target before first camp: three main-attribute support cards reach green
    bond
  - target by end of first camp: all those main supports reach orange and can
    produce colored rings
- First camp:
  - bonus trainings are `韧性`, `集中`, and `保护`
  - if main attribute has no colored ring or no high-efficiency training,
    practice more `韧性` to raise overall stats
  - early `韧性训练` also helps aim for `175` defense/protection by the third
    camp turn to recover mood
  - do not force that threshold if the alternative stamina-cost option gives a
    small speed-skill discount
- Second camp:
  - attack/power role chooses the upper beach option
  - beach gives `攻击/力量` and `集中` training bonus
  - life/stamina role chooses the lower winter hot spring option
  - winter hot spring gives `体力` and `保护/命抗` training bonus

Implementation notes:

- This screen needs more than the old simple `TrainingChoice(name, stat_gain,
  ring, fail_rate, target)` model.
- Later implementation may need a richer `TrainingOption` payload:
  - training type
  - main and secondary stat gains
  - failure rate
  - training level
  - training EXP/proficiency
  - support head count
  - support identities if OCR/vision can identify them
  - support bond colors/states
  - colored-ring state
  - active camp/route phase
- Do not implement this strategy until all camp/event/rest rules are collected.

Open questions:

- Exact names/code mapping for `集中` and `保护` versus earlier model names.
- Exact phases/turn numbers for first camp and second camp.
- How to detect camp state from the screen.
- How to classify support bond colors from the portrait bars.
- How to identify whether a support is main-attribute or non-main-attribute.

## 12. Post-Training Result / Story Event

Observed screenshot:

- This appears after clicking the blue `训练` button and completing a training.
- Top-left still shows route title, distance, and turn/month.
- Top-center stamina/endurance bar is lower than before training.
- Top-left event card panel can appear, example:
  - `阿尔克那事件`
  - `下雨天`
- Center/bottom result text can appear, example:
  - `罗莎莉亚的力量提升了。`
- A large stat result icon appears over the character, example:
  - `力量` icon
  - `+10`
- Top-right HUD skip/fast-forward controls are visible.

Rules from user:

- After training, story/event dialogue is likely to trigger.
- When story/event dialogue triggers after training, skip it.
- Track the stamina/endurance consumed by training.
- Training consumption is the same training cost already described: `15`
  stamina per training.

Flow:

- After clicking `训练`, treat stamina as consumed by `15`.
- Reconcile the tracked stamina with the visible stamina bar when OCR/vision can
  read it.
- If a result or story/event screen appears, click through/skip using the
  dialogue skip logic.
- Continue until returning to the training hub or another actionable screen.

Implementation notes:

- This screen is not the same as training selection.
- It is a transient result/event screen and should usually be handled
  automatically.
- The result text and `+N` stat gain can be recorded for state tracking, but
  the first implementation can prioritize returning to the next decision point.
- Avoid double-counting stamina: if the state manager subtracts `15` on training
  click, the post-training reader should reconcile rather than subtract again.
- OCR/visual anchors:
  - top-left event card/title area
  - result text line
  - stat gain icon and `+N`
  - stamina bar after training
  - skip/fast-forward HUD controls

Open questions:

- Whether every training result screen has a visible `+N` result.
- Whether some post-training events require choices instead of only skip.
- Whether stamina is deducted immediately on click or only after the result
  screen resolves.

## 13. Fixed Event: Training Direction

Observed screenshot:

- Appears after completing the first training.
- Top-left event panel:
  - `旅程事件`
  - `训练的方向性`
- Dialogue text:
  - `丽莎带来了可供团员训练参考的教材，该选择哪一边呢？`
- Three right-side choices:
  - `对攻击有帮助的训练教材`
  - `对生存有帮助的训练教材`
  - `有助于应对各种状况的训练教材`

Rules from user:

- This event is fixed after the first training.
- Choice 1 is for attack/power characters.
- Choice 2 is for life/stamina characters.
- The literal option text can be used to understand the choice.
- Choice 3 is a general-purpose/fallback option, but no default rule has been
  requested for choosing it.

Flow:

- Detect event title `训练的方向性`.
- If current build/role is attack or power, choose option 1:
  `对攻击有帮助的训练教材`.
- If current build/role is life/stamina, choose option 2:
  `对生存有帮助的训练教材`.
- After choosing, continue through any follow-up dialogue with skip logic.

Implementation notes:

- This event should override generic event-choice priority rules.
- It needs build/role context from `GameState` or future run config.
- OCR anchors:
  - event title `训练的方向性`
  - option text for all three choices
- Click targets:
  - three option rows on the right.

Open questions:

- Whether balanced/unknown builds should choose option 3 or pause for safety.
- Whether this event can appear again later or only once after first training.

## 14. Later Generic Relic Choice

Known planned rule from earlier TODO:

- OCR relic names/scores.
- Choose the highest score.

Open questions:

- Need screenshots of later non-initial relic screens.
- Need to confirm whether there is a confirm button after selection.
- Need to confirm if score format is always numeric or can include grades.

## Current Uncaptured Screens

The user still needs to provide or describe these before implementation is
considered complete:

- Training hub variants with different stamina/mood/coin states.
- More training selection variants with different support heads, bond colors,
  failure rates, and colored rings.
- Post-training result/event variants, including cases with only result text,
  cases with story/event dialogue, and cases that lead to choices.
- Rest submenu with `冥想室` and `露宿`.
- Event choice screen with multiple text options.
- More event choices with known option effects, to fill `docs/event-database.md`.
- Commission selection screen with red text and Rank.
- Shop screen with item names/prices.
- Region move screen with `移动` button.
- Later generic relic choice screen if it differs from first reward.
