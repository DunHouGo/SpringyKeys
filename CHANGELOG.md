# 更新日志

## 2026-04-27

### SpringyKeys
- 根据提交 `61769714d1197af48f422287462007d3fa488600` 所在仓库基线核对当前插件代码。
- 移除 `SpringyKeys.pyp` 中的调试和注册阶段 `print` 输出。
- 将 Bake、Un-Bake、Bake All、Un-Bake All、描述加载失败与注册失败等关键反馈改为 `c4d.gui.MessageDialog`。
- 保留原有弹簧计算与烘焙逻辑，仅调整用户交互提示方式。
