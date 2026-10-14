# CATS More Features — Experimental Fork

> [!WARNING]
> **This fork is under active testing and may contain many bugs. It is not a stable release.**
> Scheduled start has been tested in game, but stopping, cooldown recovery, refuelling and completion actions
> still need broader real-game testing. Passing automated tests does not guarantee reliable unattended operation.

This is [kxdxzr's experimental fork](https://github.com/kxdxzr/CATS_more_features) of
[mck-9061/CATS](https://github.com/mck-9061/CATS). The original CATS project and its authors deserve credit
for the carrier administration and traversal functionality.

## What's new in this fork

- **Scheduled start:** choose a date and adjust hours, minutes and seconds, with `Now`, `+10 min` and `+1 hour`
  shortcuts. Uncheck `Scheduled start` to start immediately. All scheduled times use your computer's local time.
- **Completion actions:** keep everything open, close the game and CATS, or shut down the computer through
  Options → `When route completes`.
- **Stop fixes:** request cancellation, release held automation keys and save progress, with a process-tree
  termination fallback. Run is enabled only after exit is confirmed; old output and exit callbacks cannot stop a new run.
- **Startup cooldown recovery:** recover carrier state from recent journals and wait for an existing jump and
  cooldown before navigating, including when a scheduled start is reached.
- **Resume and journal handling:** synchronize saved progress with the GUI, distinguish historical events from
  new requests, and handle journal rotation and partially written records.
- **Personal carrier refuelling adjustment:** remove four redundant `e` presses from the cargo-transfer sequence.
  Squadron sequences have not been changed.
- **Configuration and build improvements:** allow an empty tritium slot when automatic refuelling is disabled,
  and build/use journal-based traversal without a Frontier client ID.

## Using this fork

1. Download the Windows beta ZIP from [Releases](https://github.com/kxdxzr/CATS_more_features/releases),
   extract the entire archive to a writable folder, and read `START_HERE.txt`. Alternatively, build both
   executables and arrange the runtime directory as described in [building.md](building.md).
2. Start **`CATS-new.exe`**. The old `CATS.exe` and upstream releases do not include this fork's features.
3. Configure your route and Journal Dir. Set a valid Tritium slot if automatic refuelling is enabled.
4. For a delayed start, check `Scheduled start`, choose the date/time, then click Run. The usual startup
   countdown and carrier cooldown checks still apply; navigation input may begin later than the selected time.
5. Select an action in Options → `When route completes`:

| Option | Behaviour |
| --- | --- |
| `Keep game and CATS open` | Leave the game and GUI open after the route finishes. |
| `Close game and CATS` | After confirmed route completion, request normal game exit. Terminate the game if it is still running after 15 seconds, then close the current CATS application once exit is confirmed. Failure keeps the GUI open to report the error. |
| `Shut down computer (30 second countdown)` | Schedule a Windows shutdown after route completion. Use `shutdown /a` to cancel the countdown. |

**Stop stops CATS automation; it does not cancel a carrier jump already submitted in the game.**
Stopping manually or encountering an error does not count as successful route completion and does not trigger a completion action.

### Configuration compatibility and testing status

The installation's `settings/settings.ini` supports:

```ini
scheduled-start=
completion-action=keep-open
shutdown-on-complete=False
```

- An empty or past `scheduled-start` starts immediately. Text configuration accepts `YYYY-MM-DD HH:MM[:SS]`.
- `completion-action` accepts `keep-open`, `close-apps` or `shutdown`. It takes precedence when present;
  older configurations without it fall back to `shutdown-on-complete`.
- Cooldown is conservatively calculated as **300 seconds** after a journal arrival event. If no arrival record
  or known pending jump can be recovered, startup waits 300 seconds first.
- Unit tests cover journal state recovery, event matching, cancellation, key release and completion actions.
  Windows integration tests use synthetic parent/child processes to check Stop and immediate restart, and
  verify cancellation of the real onefile backend during scheduled-start and cooldown waits.
- **Full routes, different game menus/refuelling modes, and real game-exit/shutdown actions still require
  further in-game testing. Fixes may introduce regressions.**

Please report bugs in this fork's [Issues](https://github.com/kxdxzr/CATS_more_features/issues), including
reproduction steps, relevant settings and log excerpts. See [building.md](building.md) for test commands,
build requirements and deployment layout.

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
Download the Windows beta ZIP from this fork's [Releases](https://github.com/kxdxzr/CATS_more_features/releases),
extract all files, and launch `CATS-new.exe`. The portable beta requires 64-bit Windows and .NET Framework 4.7.2
or newer; a separate Python installation is not required. Read the testing warning and `START_HERE.txt` before running.

To build from source, follow [building.md](building.md). Do not assume an upstream installer contains this fork's changes.

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
