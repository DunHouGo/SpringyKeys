# Springy Keys 用户指南

## 插件作用

Springy Keys 是一个 Cinema 4D 表达式标签，用于给对象的 Position、Scale、Rotation 动画增加弹簧、惯性和跟随感。  
它适合给关键帧动画增加柔和拖尾、回弹和阻尼效果，而不需要手动编辑大量 F-Curve。

## 参数说明

### 基础开关

#### Position
控制是否对位置通道启用弹簧效果。

#### Scale
控制是否对缩放通道启用弹簧效果。

#### Rotation
控制是否对旋转通道启用弹簧效果。

#### Strength
控制最终弹簧结果与原始动画之间的混合强度。

### Forces

#### Split Forces (P/S/R)
关闭时，位置、缩放、旋转共用同一组刚度、阻尼和质量参数。  
开启时，位置、缩放、旋转可以分别设置独立参数。

### Position Forces

#### Stiffness
数值越大，回弹拉回目标的力度越强。

#### Damping
数值越大，振荡衰减越快。

#### Mass
数值越大，运动越重，响应越慢。

### Scale Forces

#### Stiffness
控制缩放通道的回弹强度。

#### Damping
控制缩放通道的阻尼强度。

#### Mass
控制缩放通道的惯性重量。

### Rotation Forces

#### Stiffness
控制旋转通道的回弹强度。

#### Damping
控制旋转通道的阻尼强度。

#### Mass
控制旋转通道的惯性重量。

### Bake

#### Bake Keys
把当前预览时间范围内的弹簧结果烘焙成对象的 PSR 关键帧，并暂时锁定弹簧计算。

#### Un-Bake Keys
恢复 Bake 之前保存的原始 PSR 关键帧，并重新启用弹簧计算。

#### Bake All
对当前文档内所有 Springy Keys 标签执行 Bake Keys。

#### Un-Bake All
对当前文档内所有 Springy Keys 标签执行 Un-Bake Keys。
