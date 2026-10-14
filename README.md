# CATS More Features — Experimental Fork

> [!WARNING]
> **目前仍在测试阶段，可能存在较多 bug，尚不适合视为稳定版本。**
> 定时启动已有实际游戏测试；Stop、冷却恢复、加油及完成后关闭游戏/关机等功能仍需持续验证。
> 自动化测试通过并不代表所有游戏场景都可靠，请先在能观察和及时中断的情况下测试。
>
> **This fork is under active testing and may contain many bugs. It is not a stable release.**
> Scheduled start has been tested in game, but stopping, cooldown recovery, refuelling and completion actions
> still need broader real-game testing. Passing automated tests does not guarantee reliable unattended operation.

This is [kxdxzr's experimental fork](https://github.com/kxdxzr/CATS_more_features) of
[mck-9061/CATS](https://github.com/mck-9061/CATS). The original CATS project and its authors deserve credit
for the carrier administration and traversal functionality.

## 本 fork 的新增功能 / What's new

- **定时启动**：使用日期选择器和时、分、秒调节框，支持 `Now`、`+10 min`、`+1 hour` 快捷按钮。
  取消勾选 `Scheduled start` 即立即启动，时间使用电脑本地时间。
- **完成后操作**：在 Options → `When route completes` 中选择保持打开、关闭游戏和 CATS，或关闭电脑。
- **Stop 修复**：先发送取消信号、释放自动化按住的键并保存进度，必要时结束整棵后端进程树；
  确认退出后才允许再次 Run，旧任务的输出和退出回调不会干扰新任务。
- **启动冷却恢复**：从最近的 journal 恢复跳跃状态，等待已有跳跃及冷却后再导航；定时启动也会检查。
- **续跑与 journal 处理**：保存位置同步回界面，区分历史事件与新请求，处理 journal 分卷和未写完的记录。
- **普通航母加油导航调整**：移除货物转移序列中多余的四次 `e`；Squadron 序列未修改。
- **配置与构建改进**：自动加油关闭时氚货位允许为空；无需 Frontier client ID 即可构建并使用遍历功能。

## 新功能使用方法 / Using this fork

1. 按 [building.md](building.md) 构建 GUI 和后端，并按文档布置运行目录。
2. 启动 **`CATS-new.exe`**。旧版 `CATS.exe` 或上游发布包不会自动获得这些功能。
3. 配好路线和 Journal Dir；启用自动加油时填写有效的 Tritium slot。
4. 需要定时时，勾选 `Scheduled start` 并选择日期和时间，再点 Run。
   到点后还会进行原有准备倒计时及冷却检查，不保证到点瞬间就发送导航按键。
5. 在 Options → `When route completes` 选择完成后行为：

| 选项 | 行为 |
| --- | --- |
| `Keep game and CATS open` | 路线结束后保留游戏和 GUI。 |
| `Close game and CATS` | 确认路线完成后请求游戏正常退出；15 秒未退出则结束游戏进程，确认退出后关闭当前 CATS 应用。关闭失败会报错并保留 GUI。 |
| `Shut down computer (30 second countdown)` | 完成后调用 Windows 30 秒关机倒计时，可用 `shutdown /a` 取消。 |

**Stop 只停止 CATS 自动操作，不会取消已在游戏中提交的舰队航母跳跃。**
手动停止或运行出错不会按成功完成路线来触发完成后操作。

### 配置兼容与测试范围

安装目录的 `settings/settings.ini` 支持：

```ini
scheduled-start=
completion-action=keep-open
shutdown-on-complete=False
```

- `scheduled-start` 为空或过去时间时立即启动；文本配置兼容 `YYYY-MM-DD HH:MM[:SS]`。
- `completion-action` 可选 `keep-open`、`close-apps`、`shutdown`。
  新键存在时以新键为准；没有新键的旧配置会读取 `shutdown-on-complete`。
- 冷却保守按 journal 到达事件后的 **300 秒**计算。缺少到达记录且无已知待执行跳跃时，先等待 300 秒。
- 单元测试覆盖 journal 状态恢复、事件匹配、取消、按键释放和完成操作；Windows 集成测试使用模拟父子进程
  检查 Stop/立即重启，并在真 onefile exe 的定时与冷却等待阶段验证取消。
- **完整路线、不同游戏菜单/加油模式及真实完成后退出/关机仍需进一步实测，bug 修复也可能带来回归。**

请在本 fork 的 [Issues](https://github.com/kxdxzr/CATS_more_features/issues) 中提供复现步骤、相关设置和日志片段。
测试命令、构建要求及目录布局见 [building.md](building.md)。

---

## Original CATS overview
CATS is an Elite Dangerous fleet carrier auto-plotter, autojumper, and flight computer.
<br>
This app also allows you to view stats about carriers across multiple accounts.

## Features
### Admin interface
* View name, callsign, credits, fuel, current system and other stats for multiple carriers.
* Manage as many of your own personal carriers as you want.
* View cargo and market data for your carriers.
* Get carrier data from Frontier's API.
### Traversal system
* Automatic jump plotting
* Supports all personal and squadron carriers, including Drake-, Fortune-, Victory-, Nautilus-, and Javelin-class carriers
* Tritium restocking
* Route time estimations
* GUI
* Keeps track of jump time (in case a jump is longer than 15 minutes)
* Discord integration
* Import routes from the Spansh fleet carrier router
* Generate routes between two systems automatically using Spansh's API
* Checks if you have enough Tritium for the route (personal carriers only)

## Limitations
* This only works on Windows and probably won't be ported to anything else.
* It also only works with PC accounts running on Odyssey (The admin interface also works with Live Horizons, but the traversal system is Odyssey-only for now)
* The autopilot has experimental support for displays running at resolutions other than 1920x1080, though most resolutions haven't been tested.
* Elite Dangerous should be running on your primary monitor in fullscreen.
* Officially supported resolutions can be found in the `resolutions.md` file.
* Elite needs to be using the default keybinds - if you've got custom keybinds, or are using a controller or HOTAS, you should back up your binds then reset to default keyboard+mouse.

## Installation
For this experimental fork, follow [building.md](building.md) to build and deploy both executables.
Do not assume an upstream installer contains this fork's changes. The original upstream release bundles
the admin panel and traversal system, but its binaries are separate from the features described above.

## Traversal system usage
### Refuelling setup
Read this section carefully and follow the instructions, as refuelling needs to have the options set correctly in order to function.

### Refuelling compatibility note
Game updates and menu changes can break the input sequences. This fork adjusts the ordinary carrier
cargo-transfer sequence, but refuelling remains experimental and the different modes still need in-game verification.

#### Using a PERSONAL carrier
* Fill the carrier's tritium depot to full (1000 tritium).
* Use a ship with at least 200 cargo capacity.
* Fill your ship's cargo hold with tritium FROM your carrier.
* In the cargo transfer menu on your carrier, there will be 2 entries for tritium. Locate the entry with tritium in the CARRIER, not in the ship.
* If this entry is in the first 8 items, i.e. you can reach it without pressing S:
  * In the CATS options, set the "Refuelling mode" to "Personal (First 8 items)".
  * Count how many times you have to press W to get to that entry from the "Confirm Items Transfer" button.
  * Enter this number in the "Tritium slot" option in CATS.
* If the entry is not in the first 8 items:
    * In the CATS options, set the "Refuelling mode" to "Personal (After 8 items)".
    * Back out of the transfer menu, then go back into it.
    * Press W, then count how many times you have to press S to get to that entry.
    * Enter this number in the "Tritium slot" option in CATS.

#### Using a SQUADRON carrier
* In the CATS options, set the "Refuelling mode" to "Squadron".
* Fill the carrier's tritium depot to full (1000 tritium).
* Use a ship with at least 200 cargo capacity.
* Fill your ship's cargo hold with tritium.
* Go to the squadron bank menu and select the Commodities section.
* Hover over the top commodity in the list.
* Count how many times you have to press S to get to the tritium you want to use (if it's at the top, this would be 0).
* Enter this number in the "Tritium slot" option in CATS.

### Starting the route
* Dock with your carrier.
* Make sure your cursor is over the "Carrier Services" option, and that your internal panel (right) is on the home tab.
* Open the traversal system. Fill in the options:
  * Journal Dir: The directory of your Elite Dangerous journal files.
  * Route: Put each system on a new line. Alternatively, import from a plain text list of systems, or a CSV from Spansh's FC plotter.
* Check the options menu:
  * Automatically plot jumps: If unchecked, you'll instead receive a pop-up telling you to plot a jump when it's time.
  * Determine Tritium requirements when automatically findng route: Requires a carrier to be added to the admin interface.
  * Power saving mode: EXPERIMENTAL. Will close and re-open the game between jumps. Requires the Steam version of Elite Dangerous.
* Select the starting point: If you're already at a system on the route, select it here. Otherwise select "Before first system in route".
* Click "Run CATS", then tab to the Elite Dangerous window. It should now start to plot jumps.

## Traversal system disclaimer
Use of programs like this is technically against Frontier's TOS. While they haven't yet banned people for automating carrier jumps, the developer does not take any responsibility for any actions that could be taken against your account.<br>
Use of the admin interface without the traversal system carries no risk, as it's simply reading from FDev's API.

<br><br>
o7
