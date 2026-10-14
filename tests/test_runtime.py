import ast
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'TraversalSystem'))
from journalwatcher import JournalWatcher, UTC
from runtimecontrol import RuntimeControl, ControlledInput, Stopped


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.file = self.directory / 'Journal.1.log'
        self.now = dt.datetime.now(UTC)
        self.write('CarrierStats', CarrierID=42, FuelLevel=900)

    def write(self, kind, when=None, **values):
        event = dict(event=kind, timestamp=(when or self.now).isoformat(), **values)
        with self.file.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event) + '\n')

    def arrive(self, when, system='Target', carrier=42):
        self.write('CarrierJump', when, MarketID=carrier, Docked=True,
                   StationType='FleetCarrier', StarSystem=system)

    def test_restart_recovers_cooldown_without_replaying_completion(self):
        self.arrive(self.now - dt.timedelta(seconds=45))
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        self.assertEqual(watcher.readiness(self.now), ('cooldown', 255))
        self.assertFalse(watcher.get_jumped())
        self.assertEqual(watcher.readiness(self.now + dt.timedelta(seconds=256)), ('ready', 0))

    def test_only_new_matching_request_and_arrival_confirm_navigation(self):
        self.write('CarrierJumpRequest', self.now - dt.timedelta(hours=1), CarrierID=42,
                   SystemName='Target', DepartureTime=self.now.isoformat())
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        self.assertEqual(watcher.last_carrier_request(), '')
        watcher.begin_navigation('Target')
        self.write('CarrierJumpRequest', CarrierID=42, SystemName='Wrong', DepartureTime=self.now.isoformat())
        self.assertEqual(watcher.last_carrier_request(), '')
        self.write('CarrierJumpRequest', CarrierID=42, SystemName='Target', DepartureTime=self.now.isoformat())
        self.assertEqual(watcher.last_carrier_request(), 'Target')
        self.arrive(dt.datetime.now(UTC), system='Wrong')
        self.assertFalse(watcher.get_jumped())
        self.arrive(dt.datetime.now(UTC), carrier=99)
        self.assertFalse(watcher.get_jumped())
        self.arrive(dt.datetime.now(UTC))
        self.assertTrue(watcher.get_jumped())

    def test_cancelled_jump_does_not_complete(self):
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        watcher.begin_navigation('Target')
        self.write('CarrierJumpCancelled', dt.datetime.now(UTC), CarrierID=42)
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            watcher.get_jumped()

    def test_partial_event_and_rotation_preserve_pending_jump(self):
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        self.write('CarrierJumpRequest', CarrierID=42, SystemName='Target', DepartureTime=self.now.isoformat())
        watcher.process_journal(self.file)
        self.assertIsNone(watcher.readiness()[1])
        self.file = self.directory / 'Journal.2.log'
        event = dict(event='Location', timestamp=(self.now + dt.timedelta(seconds=70)).isoformat(),
                     MarketID=42, Docked=True, StationType='FleetCarrier', StarSystem='Target')
        text = json.dumps(event)
        self.file.write_text(text[:20], encoding='utf-8')
        watcher.process_journal(self.file)
        self.assertIsNotNone(watcher.pending)
        with self.file.open('a', encoding='utf-8') as stream:
            stream.write(text[20:] + '\n')
        watcher.process_journal(self.file)
        self.assertIsNone(watcher.pending)
        self.assertEqual(watcher.last_system, 'Target')


class ControlTests(unittest.TestCase):
    def test_stop_releases_held_keys_saves_and_blocks_further_input(self):
        control = RuntimeControl()
        keyboard = Mock()
        control.keyboard = keyboard
        control.save_progress = Mock()
        guarded = ControlledInput(keyboard, control)
        guarded.keyDown('ctrl')
        with patch('runtimecontrol.os._exit', side_effect=SystemExit(3)):
            with self.assertRaises(SystemExit):
                control.stop_and_exit()
        keyboard.keyUp.assert_called_once_with('ctrl', _pause=False)
        control.save_progress.assert_called_once()
        with self.assertRaises(Stopped):
            guarded.press('space')
        keyboard.press.assert_not_called()
        with self.assertRaises(Stopped):
            control.sleep(3600)


class CompletionTests(unittest.TestCase):
    def test_game_close_targets_only_game_and_handles_exit_race(self):
        import completion
        game = Mock(pid=123, info={'name': 'EliteDangerous64.exe'})
        launcher = Mock(pid=124, info={'name': 'EDLaunch.exe'})
        game.is_running.return_value = True
        game.terminate.side_effect = completion.psutil.NoSuchProcess(123)
        with patch.object(completion.psutil, 'process_iter', return_value=[game, launcher]), \
                patch.object(completion.ctypes.windll, 'user32', Mock()), \
                patch.object(completion.time, 'monotonic', side_effect=[0, 16]):
            completion.close_game(RuntimeControl())
        game.terminate.assert_called_once()
        launcher.terminate.assert_not_called()

    def test_game_close_failure_keeps_completion_unsuccessful(self):
        import completion
        game = Mock(pid=123, info={'name': 'EliteDangerous64.exe'})
        game.is_running.return_value = True
        game.wait.side_effect = completion.psutil.TimeoutExpired(5)
        with patch.object(completion.psutil, 'process_iter', return_value=[game]), \
                patch.object(completion.ctypes.windll, 'user32', Mock()), \
                patch.object(completion.time, 'monotonic', side_effect=[0, 16]):
            with self.assertRaisesRegex(RuntimeError, 'keeping CATS open'):
                completion.close_game(RuntimeControl())

    def test_real_main_function_routes_all_completion_actions(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        code = compile(ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef)],
                                  type_ignores=[]), '<main-function-test>', 'exec')
        for power, action in [(False, 'keep-open'), (False, 'shutdown'), (True, 'close-apps')]:
            with self.subTest(power=power, action=action), tempfile.TemporaryDirectory() as temp:
                route = Path(temp) / 'route.txt'
                route.write_text('Target\n', encoding='utf-8')
                watcher = Mock(last_system=None)
                watcher.get_jumped.side_effect = [False, True]
                threads = Mock()
                threads.Thread.return_value.is_alive.return_value = False
                system = Mock(return_value=0)
                close_game = Mock()
                scope = dict(datetime=dt, time=SimpleNamespace(sleep=Mock(), mktime=__import__('time').mktime,
                             localtime=__import__('time').localtime), os=SimpleNamespace(path=os.path, system=system),
                             threading=threads, tzlocal=SimpleNamespace(get_localzone=lambda: UTC),
                             journal_watcher=watcher, discord_messenger=Mock(), power_saving=power,
                             completion_action=action, route_file=str(route), disable_refuel=True,
                             webhook_url='', journal_directory=temp, control=RuntimeControl(), print=Mock())
                exec(code, scope)
                scope.update(load_settings=Mock(), wait_for_scheduled_start=Mock(), wait_for_carrier_ready=Mock(),
                             latest_journal=Mock(return_value='fake'), jump_to_system=Mock(return_value=(6, dt.datetime.now())),
                             follow_button_sequence=Mock())
                with patch.dict(sys.modules, completion=SimpleNamespace(close_game=close_game)):
                    self.assertTrue(scope['main_loop']())
                self.assertEqual(watcher.get_jumped.call_count, 2)
                scope['follow_button_sequence'].assert_not_called()
                threads.Timer.assert_not_called()
                if action == 'shutdown':
                    system.assert_called_once_with('shutdown /s /t 30')
                else:
                    system.assert_not_called()
                if action == 'close-apps':
                    close_game.assert_called_once()
                    scope['print'].assert_any_call('CATS_COMPLETION_CLOSE', flush=True)
                else:
                    close_game.assert_not_called()


if __name__ == '__main__':
    unittest.main()
