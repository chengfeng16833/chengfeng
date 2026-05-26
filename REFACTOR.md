# 重构待办（REFACTOR）

记录已识别但**有意延后**的重构项，避免打断主功能开发。每项标注启动条件。

## 待物理搬迁（阶段2遗留）
- [ ] 将19个画面的parse_X/decide_X/_has_X 物理搬迁到对应handler文件
- 启动条件：主流程实跑稳定（能跑完整run 5次以上无识别错误）
- 预计工作量：多轮+逐画面测试

> 背景：阶段2用了**委托式**注册表——`screens/__init__.py` 里的 handler 转发到现有的
> `parse_X`/`decide_X`/`_has_X_signature`（行为 1:1，零回归风险）。分发已统一走注册表
> （classifier/policy/live_loop 不再有 if/elif 硬路由）。物理搬迁 = 把每个画面的逻辑真正
> 挪进 `screens/<screen>.py`，原函数改为转发壳，给 screen_reader.py 瘦身。届时分发层无需
> 再动，逐画面搬 + 逐画面测即可。
> 附带：live_loop 的蓝键 builder（`_BLUE_PARSERS`）也在本地，搬迁时一并移入 handler。

## 其他待办（来自代码体检报告，本周不做）
- [ ] **属性名映射**：内部名 power/stamina/guts/wisdom/speed 与游戏术语 力量/体力/韧性/专注/保护 不一致，易误导。统一或集中注释映射表。（维度2，中）
- [ ] **拆分 screen_reader.py**（1356行，混了 OCR基础设施/文字工具/各画面parser/颜色检测）。与物理搬迁一起做更顺。（维度1，中）
- [ ] **颜色检测收口**：`_detect_red_text`/`_detect_yellow_text`/`_is_blue_region` 等从 screen_reader 移到 vision.py。（维度1，中）
- [ ] **魔法数字集中**：classifier 置信度阈值(0.5/0.6/0.7/0.75)、颜色阈值(mean>=85/stddev>=45、HSV范围)集中到 DetectionConfig 并加注释。（维度3，小）
- [ ] **bat 路径硬编码**：`tools/*.bat`、`启动控制台.bat`、`跑测试.bat` 写死了 python.exe 绝对路径，换机器/用户名会失效。（维度3，低）
- [ ] **capture.py 静默 except**：截图失败的 except（capture.py:25/28）尚未加日志（阶段1只覆盖了 classifier/screen_reader/live_loop）。（维度4，小）
- [ ] **policy.decide_X 的 config 耦合**：决策逻辑依赖 TrainerPolicy.config/实例状态，物理搬迁时需决定 config 如何注入 handler。（维度5，中）

## 已完成
- [x] 阶段1：标准 logging 体系（控制台INFO+文件DEBUG、替换静默吞错误、关键决策INFO日志）
- [x] 阶段2：画面注册表（委托式）——统一分发，去掉 classifier/policy/live_loop 的硬编码 if/elif 路由
