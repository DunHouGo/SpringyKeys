# Springy Keys User Guide

## Overview

Springy Keys is a Cinema 4D expression tag that adds spring, inertia, and follow-through behavior to animated Position, Scale, and Rotation channels.  
It is useful for turning rigid keyframed motion into softer, more organic motion without manually reshaping many F-Curves.

## Parameters

### Main Controls

#### Position
Enables or disables the spring effect for the position channels.

#### Scale
Enables or disables the spring effect for the scale channels.

#### Rotation
Enables or disables the spring effect for the rotation channels.

#### Strength
Controls how strongly the spring result is blended with the original animation.

### Forces

#### Split Forces (P/S/R)
When disabled, Position, Scale, and Rotation share the same stiffness, damping, and mass values.  
When enabled, each transform group can use its own force settings.

### Position Forces

#### Stiffness
Higher values pull the motion back toward the target more aggressively.

#### Damping
Higher values reduce oscillation faster.

#### Mass
Higher values make the motion feel heavier and slower to react.

### Scale Forces

#### Stiffness
Controls the spring pull strength for scale.

#### Damping
Controls how quickly scale oscillation settles.

#### Mass
Controls the inertia weight for scale.

### Rotation Forces

#### Stiffness
Controls the spring pull strength for rotation.

#### Damping
Controls how quickly rotation oscillation settles.

#### Mass
Controls the inertia weight for rotation.

### Bake

#### Bake Keys
Bakes the spring result into PSR keyframes over the current preview range and temporarily locks the spring forces.

#### Un-Bake Keys
Restores the original PSR keyframes saved before baking and re-enables the spring forces.

#### Bake All
Runs Bake Keys on every Springy Keys tag in the current document.

#### Un-Bake All
Runs Un-Bake Keys on every Springy Keys tag in the current document.
