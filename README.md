# Springy Keys (Cinema 4D Tag)

Springy Keys is a Cinema 4D Expression Tag that adds spring/inertia behavior to an object’s animated **P/S/R** (Position / Scale / Rotation).

I have ported the plugin to Cinema 4D Python to enable extended support and reduce ongoing development overhead for end users.

You can find the original plugin here: [Springy Keys](https://github.com/insydium/CDTools/tree/main)

You can also get the latest python version in [boghma](https://boghma.com) plugins

## Original author: [Cactus Dan](https://github.com/insydium/CDTools/tree/main)

<img src="https://insydium.ltd/site/assets/files/1708/cactus-dan.jpg" width=50%>

## What it is for

- Add secondary motion to hand-keyed or baked animation.
- Make transforms feel less mechanical (soft follow-through).
- Add subtle overshoot and damping without editing F-curves.

## How to use

1. Copy the whole folder into one of your Cinema 4D plugin locations.
2. Restart Cinema 4D.
3. In Cinema 4D, add the tag to an object:

## About Cactus Dan
Dan was a self-taught programmer who mastered complex mathematical concepts to create these tools. Beyond his technical skills, he was known for his cowboy lifestyle, spending his last years exploring the Utah desert on horseback.

## Repository Purpose
We are making these source files available in memory of Cactus Dan, ensuring his work lives on within the 3D community.

---

## License & Usage
This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0) License**.  

- You are **free to use, modify, and share** the code.  
- **Commercial use is strictly prohibited.**  
- You **must credit Cactus Dan** as the original creator.  

For full details, see the **[Creative Commons License](https://creativecommons.org/licenses/by-nc/4.0/)**.

This project is shared with the community to keep Dan’s work alive.


### Tag Properties

- **Position**
  - Enables spring effect on position.
  - If disabled, position stays exactly on the animated target.

- **Scale**
  - Enables spring effect on scale.
  - If disabled, scale stays exactly on the animated target.

- **Rotation**
  - Enables spring effect on rotation.
  - If disabled, rotation stays exactly on the animated target.

- **Strength**
  - Internally used as a blend factor.

### Forces

- **Split Forces (P/S/R)**
  - When **off**: Position stiffness/damping/mass are also used for Scale and Rotation.
  - When **on**: Position/Scale/Rotation each have their own stiffness/damping/mass.

#### Forces

- **Stiffness**
  - Higher values pull harder toward the target (snappier).

- **Damping**
  - Higher values reduce oscillation faster.

- **Mass**
  - Higher values make motion heavier/slower to respond.


## Credits

Original concept/plugin credited in project notes to **Cactus Dan**.
