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
from cargo_snapshot import read_snapshot, classify_change


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

    def test_pending_jump_expires_30_minutes_after_departure(self):
        departure = self.now - dt.timedelta(minutes=10)
        self.write('CarrierJumpRequest', self.now - dt.timedelta(minutes=25), CarrierID=42,
                   SystemName='Target', DepartureTime=departure.isoformat())
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        self.assertIsNone(watcher.readiness(self.now)[1])
        self.assertIsNone(watcher.readiness(departure + dt.timedelta(minutes=30))[1])
        self.assertEqual(watcher.readiness(departure + dt.timedelta(minutes=30, seconds=1)), ('ready', 0))
        self.assertIsNone(watcher.pending)

    def test_pending_jump_with_invalid_departure_is_not_guessed_expired(self):
        watcher = JournalWatcher()
        watcher.pending = {'DepartureTime': 'invalid'}
        self.assertIsNone(watcher.readiness(self.now)[1])
        self.assertIsNotNone(watcher.pending)

    def test_pending_jump_countdown_and_departure_not_arrival(self):
        watcher = JournalWatcher()
        watcher.pending = {'SystemName': 'Target', 'DepartureTime': (self.now + dt.timedelta(seconds=90)).isoformat()}
        self.assertEqual(watcher.pending_jump_countdown(self.now), ('Target', 90))
        self.assertEqual(watcher.pending_jump_countdown(self.now + dt.timedelta(seconds=100)), ('Target', 0))
        self.assertIsNone(watcher.readiness(self.now + dt.timedelta(seconds=100))[1])
        watcher.pending = {'DepartureTime': 'invalid'}
        self.assertIsNone(watcher.pending_jump_countdown(self.now))

    def test_existing_jump_identity_requires_matching_confirmed_arrival(self):
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        self.write('CarrierJumpRequest', self.now, CarrierID=42, SystemName='Target',
                   DepartureTime=(self.now + dt.timedelta(minutes=1)).isoformat())
        watcher.process_journal(self.file)
        identity = watcher.pending_jump_identity()
        self.assertFalse(watcher.arrival_matches(identity))
        self.arrive(self.now + dt.timedelta(minutes=1), system='Other')
        watcher.process_journal(self.file)
        self.assertFalse(watcher.arrival_matches(identity))
        self.arrive(self.now + dt.timedelta(minutes=2), system='Target')
        watcher.process_journal(self.file)
        self.assertTrue(watcher.arrival_matches(identity))

    def test_existing_cancelled_jump_does_not_trigger_refuel_match(self):
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        self.write('CarrierJumpRequest', self.now, CarrierID=42, SystemName='Target',
                   DepartureTime=(self.now + dt.timedelta(minutes=1)).isoformat())
        watcher.process_journal(self.file)
        identity = watcher.pending_jump_identity()
        self.write('CarrierJumpCancelled', self.now + dt.timedelta(seconds=10), CarrierID=42)
        watcher.process_journal(self.file)
        self.assertFalse(watcher.arrival_matches(identity))

    def test_transfer_marker_ignores_history_and_tracks_new_events(self):
        self.write('CargoTransfer', Transfers=[{'Type': 'steel', 'Direction': 'toship', 'Count': 1}])
        watcher = JournalWatcher()
        watcher.initialize(self.directory)
        marker = watcher.cargo_transfer_marker()
        self.assertEqual(watcher.cargo_transfers_since(marker), [])
        self.write('CargoTransfer', Transfers=[{'Type': 'tritium', 'Direction': 'toship', 'Count': 20}])
        watcher.process_journal(self.file)
        self.assertEqual(watcher.cargo_transfers_since(marker)[0][1][0]['Type'], 'tritium')

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
    def test_existing_jump_refuels_once_only_after_confirmed_arrival(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'wait_for_carrier_ready')
        for enabled, confirmed, expected in [(True, True, 1), (False, True, 0), (True, False, 0)]:
            with self.subTest(enabled=enabled, confirmed=confirmed):
                watcher = Mock()
                watcher.readiness.side_effect = [('jump in progress', None), ('cooldown', 150), ('ready', 0)]
                watcher.pending_jump_identity.side_effect = [('Target', 'request'), None, None]
                watcher.pending_jump_countdown.return_value = ('Target', 5)
                watcher.arrival_matches.return_value = confirmed
                refuel = Mock()
                class InlineThread:
                    def __init__(self, target, daemon): self.target = target
                    def start(self): self.target()
                    def is_alive(self): return False
                scope = dict(control=Mock(), journal_watcher=watcher, latest_journal=Mock(),
                             auto_plot_jumps=True, disable_refuel=not enabled, restock_tritium=refuel,
                             threading=SimpleNamespace(Thread=InlineThread), datetime=dt,
                             time=SimpleNamespace(sleep=Mock()), print=Mock())
                exec(compile(ast.Module(body=[node], type_ignores=[]), '<wait>', 'exec'), scope)
                scope['wait_for_carrier_ready'](refuel_existing_jump=True)
                self.assertEqual(refuel.call_count, expected)

    def test_route_dimming_stays_active_through_navigation_and_refuel(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        main = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'main_loop')
        game = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'open_game')
        def calls(node, name):
            return [n for n in ast.walk(node) if isinstance(n, ast.Call) and
                    ((isinstance(n.func, ast.Name) and n.func.id == name) or
                     (isinstance(n.func, ast.Attribute) and n.func.attr == name))]
        dim = calls(main, 'dim')
        self.assertEqual(len(dim), 1)
        self.assertLess(dim[0].lineno, calls(main, 'wait_for_scheduled_start')[0].lineno)
        self.assertFalse(calls(game, 'restore_displays'))
        loop = next(n for n in main.body if isinstance(n, ast.For) and isinstance(n.target, ast.Name)
                    and n.target.id == 'i' and isinstance(n.iter, ast.Call))
        # Error handlers can restore immediately; ordinary route iterations cannot.
        restores = calls(loop, 'restore_displays')
        self.assertEqual(len(restores), 1)
        self.assertTrue(any(restores[0] in ast.walk(handler) for n in ast.walk(loop)
                            if isinstance(n, ast.Try) for handler in n.handlers))

    def test_cargo_snapshot_change_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Cargo.json'
            def write(items, timestamp='2026-11-16T14:31:40Z'):
                path.write_text(json.dumps(dict(timestamp=timestamp, event='Cargo', Vessel='Ship',
                    Count=sum(items.values()), Inventory=[dict(Name=k, Count=v) for k, v in items.items()])), encoding='utf-8')
                return read_snapshot(directory)
            baseline = write({'tritium': 5})
            tritium = write({'tritium': 30}, '2026-11-16T14:31:41Z')
            self.assertEqual(classify_change(baseline, tritium), 'tritium')
            mixed = write({'tritium': 30, 'steel': 4}, '2026-11-16T14:31:42Z')
            self.assertEqual(classify_change(baseline, mixed), 'wrong')
            self.assertEqual(classify_change(baseline, baseline), 'unknown')
            self.assertEqual(classify_change(None, mixed), 'unknown')
            path.write_text('{broken', encoding='utf-8')
            self.assertIsNone(read_snapshot(directory))

    def test_display_brightness_saves_and_restores_without_real_hardware(self):
        from display_control import WindowsBrightness
        import ctypes
        manager = WindowsBrightness()
        calls = []
        def powershell(script):
            calls.append(script)
            return '[{"InstanceName":"DISPLAY_TEST","CurrentBrightness":74,"Level":[0,10,100]}]' if 'WmiMonitorBrightness |' in script else ''
        dxva = Mock()
        def get_brightness(handle, low, current, high):
            low._obj.value, current._obj.value, high._obj.value = 3, 65, 100
            return True
        dxva.GetMonitorBrightness.side_effect = get_brightness
        dxva.SetMonitorBrightness.return_value = True
        manager._powershell = powershell
        manager._monitors = lambda operation: (operation(dxva, 123, 0, SimpleNamespace(handle=456, description='fake')) or [])
        manager.dim()
        self.assertEqual(dxva.SetMonitorBrightness.call_args.args, (456, 3))
        self.assertIn('Brightness=[byte]0', calls[-1])
        manager.restore()
        self.assertEqual(dxva.SetMonitorBrightness.call_args.args, (456, 65))
        self.assertIn('Brightness=[byte]74', calls[-1])
        self.assertFalse(manager.saved_ddc or manager.saved_wmi)

    def test_extracted_cargo_classification_and_mixed_transfer(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'check_extracted_cargo')
        for transfers, expected in [([{'Type': 'steel', 'Direction': 'toship'}], 'wrong'),
                                    ([{'Type': 'tritium', 'Direction': 'toship'}], 'tritium'),
                                    ([{'Type': 'steel', 'Direction': 'tocarrier'}], 'unknown'),
                                    ([{'Type': 'tritium', 'Direction': 'toship'}, {'Type': 'steel', 'Direction': 'toship'}], 'wrong'),
                                    ([{'Direction': 'toship'}], 'unknown')]:
            with self.subTest(transfers=transfers):
                watcher = Mock()
                watcher.cargo_transfers_since.return_value = [(1, transfers)]
                scope = dict(time=SimpleNamespace(monotonic=Mock(side_effect=[0, 10]), sleep=Mock()),
                             journal_watcher=watcher, latest_journal=Mock(), print=Mock(),
                             classify_change=Mock(return_value='unknown'), read_snapshot=Mock(), journal_directory='unused')
                exec(compile(ast.Module(body=[node], type_ignores=[]), '<cargo-check>', 'exec'), scope)
                self.assertEqual(scope['check_extracted_cargo'](0), expected)

    def test_snapshot_fallback_and_conflicting_evidence(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'check_extracted_cargo')
        for events, snapshot, expected in [([], 'tritium', 'tritium'), ([], 'unknown', 'unknown'),
                                          ([(1, [{'Type': 'tritium', 'Direction': 'toship'}])], 'wrong', 'wrong')]:
            with self.subTest(snapshot=snapshot):
                watcher = Mock()
                watcher.cargo_transfers_since.return_value = events
                scope = dict(time=SimpleNamespace(monotonic=Mock(side_effect=[0, 10]), sleep=Mock()),
                             journal_watcher=watcher, latest_journal=Mock(), print=Mock(),
                             classify_change=Mock(return_value=snapshot), read_snapshot=Mock(), journal_directory='unused')
                exec(compile(ast.Module(body=[node], type_ignores=[]), '<cargo-check>', 'exec'), scope)
                self.assertEqual(scope['check_extracted_cargo'](0, object()), expected)

    def test_refuel_test_bypasses_disabled_option_without_route_or_shutdown(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        funcs = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in ('restock_tritium', 'run_refuel_test')]
        sequence, settings, sleep, system = Mock(), Mock(), Mock(), Mock()
        scope = dict(load_settings=settings, follow_button_sequence=sequence,
                     auto_plot_jumps=False, disable_refuel=True, refuel_mode=2, tritium_slot=2,
                     warehouse_extraction_blocked=False, unknown_transfer_policy='stop',
                     journal_watcher=Mock(), journal_directory='unused', latest_journal=Mock(return_value='journal'),
                     read_snapshot=Mock(),
                     os=SimpleNamespace(path=SimpleNamespace(isfile=lambda path: True), system=system),
                     pydirectinput=Mock(), time=SimpleNamespace(sleep=sleep),
                     slight_random_time=lambda x: x, print=Mock())
        exec(compile(ast.Module(body=funcs, type_ignores=[]), '<refuel-test>', 'exec'), scope)
        scope['check_extracted_cargo'] = Mock(return_value='tritium')
        scope['restock_tritium']()
        sequence.assert_not_called()
        self.assertTrue(scope['run_refuel_test']())
        settings.assert_called_once_with(force_refuel=True)
        self.assertEqual([call.args[0] for call in sequence.call_args_list],
                         ['squadron/restock_fc.txt', 'squadron/open_cargo_transfer.txt', 'squadron/restock_cargo.txt'])
        self.assertEqual(scope['pydirectinput'].press.call_count, 2)
        system.assert_not_called()

    def test_wrong_or_unknown_transfer_policy_and_depot_only(self):
        source = ast.parse((ROOT / 'TraversalSystem/main.py').read_text(encoding='utf-8'))
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'restock_tritium')
        for result, policy, blocked in [('wrong', 'ignore', True), ('wrong', 'stop', True),
                                        ('unknown', 'stop', True), ('unknown', 'ignore', False),
                                        ('tritium', 'stop', False)]:
            with self.subTest(result=result, policy=policy):
                sequence = Mock()
                scope = dict(auto_plot_jumps=True, disable_refuel=False, refuel_mode=2, tritium_slot=0,
                             warehouse_extraction_blocked=False, unknown_transfer_policy=policy,
                             journal_watcher=Mock(), latest_journal=Mock(return_value='journal'),
                             read_snapshot=Mock(), journal_directory='unused',
                             check_extracted_cargo=Mock(return_value=result), follow_button_sequence=sequence,
                             os=SimpleNamespace(path=SimpleNamespace(isfile=lambda p: True)),
                             pydirectinput=Mock(), time=SimpleNamespace(sleep=Mock()), print=Mock())
                exec(compile(ast.Module(body=[node], type_ignores=[]), '<refuel>', 'exec'), scope)
                scope['restock_tritium']()
                self.assertEqual(scope['warehouse_extraction_blocked'], blocked)
                sequence.reset_mock()
                scope['restock_tritium']()
                if blocked:
                    self.assertEqual([c.args[0] for c in sequence.call_args_list], ['squadron/restock_fc.txt'])
                else:
                    self.assertEqual(len(sequence.call_args_list), 3)

    def test_stop_releases_held_keys_saves_and_blocks_further_input(self):
        control = RuntimeControl()
        keyboard = Mock()
        control.keyboard = keyboard
        control.save_progress = Mock()
        control.restore_displays = Mock()
        guarded = ControlledInput(keyboard, control)
        guarded.keyDown('ctrl')
        with patch('runtimecontrol.os._exit', side_effect=SystemExit(3)):
            with self.assertRaises(SystemExit):
                control.stop_and_exit()
        keyboard.keyUp.assert_called_once_with('ctrl', _pause=False)
        control.save_progress.assert_called_once()
        control.restore_displays.assert_called_once()
        with self.assertRaises(Stopped):
            guarded.press('space')
        keyboard.press.assert_not_called()
        with self.assertRaises(Stopped):
            control.sleep(3600)


class CompletionTests(unittest.TestCase):
    def test_leigod_dry_run_never_spawns_process(self):
        import leigod_pause
        with patch.object(leigod_pause.subprocess, 'Popen') as spawn:
            self.assertTrue(leigod_pause.pause(RuntimeControl(), dry_run=True))
            spawn.assert_not_called()

    def test_simulated_completion_never_calls_real_actions(self):
        import completion
        for action in ('keep-open', 'close-apps', 'shutdown'):
            for enabled in (True, False):
                with self.subTest(action=action, enabled=enabled), \
                        patch.object(completion, 'close_game') as close, \
                        patch.object(completion.os, 'system') as system, \
                        patch.object(completion, 'pause_leigod', return_value=True) as pause:
                    self.assertTrue(completion.execute_completion(action, enabled, RuntimeControl(),
                                                                  dry_run=True, screen_off=True))
                    close.assert_not_called()
                    system.assert_not_called()
                    if enabled:
                        self.assertTrue(pause.call_args.kwargs['dry_run'])
                    else:
                        pause.assert_not_called()

    def test_pause_failure_does_not_block_shutdown(self):
        import completion
        control = RuntimeControl()
        control.sleep = Mock()
        with patch.object(completion, 'pause_leigod', return_value=False), \
                patch.object(completion.os, 'system', return_value=0) as shutdown:
            self.assertTrue(completion.execute_completion('shutdown', True, control))
            shutdown.assert_called_once_with('shutdown /s /t 30')

    def test_completion_test_attempts_pause_but_not_shutdown(self):
        import completion
        with patch.object(completion, 'pause_leigod', return_value=True) as pause, \
                patch.object(completion.os, 'system') as shutdown, \
                patch.object(completion, 'close_game') as close:
            self.assertTrue(completion.execute_completion('shutdown', True, RuntimeControl(),
                                                         dry_run=True, test_real_pause=True))
            self.assertFalse(pause.call_args.kwargs['dry_run'])
            shutdown.assert_not_called()
            close.assert_not_called()

    def test_stopped_flow_does_not_pause_or_shutdown(self):
        import completion
        control = RuntimeControl()
        control.stopped.set()
        with patch.object(completion, 'pause_leigod') as pause, \
                patch.object(completion.os, 'system') as shutdown:
            with self.assertRaises(Stopped):
                completion.execute_completion('shutdown', True, control)
            pause.assert_not_called()
            shutdown.assert_not_called()

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
                execute_completion = Mock(return_value=True)
                scope = dict(datetime=dt, time=SimpleNamespace(sleep=Mock(), mktime=__import__('time').mktime,
                             localtime=__import__('time').localtime), os=SimpleNamespace(path=os.path, system=system),
                             threading=threads, tzlocal=SimpleNamespace(get_localzone=lambda: UTC),
                             journal_watcher=watcher, discord_messenger=Mock(), power_saving=power,
                             completion_action=action, route_file=str(route), disable_refuel=True, auto_plot_jumps=True,
                             dim_during_jump=False, display_brightness=None,
                             pause_leigod_on_complete=False,
                             webhook_url='', journal_directory=temp, control=RuntimeControl(), print=Mock())
                exec(code, scope)
                scope.update(load_settings=Mock(), wait_for_scheduled_start=Mock(), wait_for_carrier_ready=Mock(),
                             latest_journal=Mock(return_value='fake'), jump_to_system=Mock(return_value=(6, dt.datetime.now())),
                             follow_button_sequence=Mock())
                with patch.dict(sys.modules, completion=SimpleNamespace(execute_completion=execute_completion)):
                    self.assertTrue(scope['main_loop']())
                self.assertEqual(watcher.get_jumped.call_count, 2)
                scope['follow_button_sequence'].assert_not_called()
                threads.Timer.assert_not_called()
                system.assert_not_called()
                execute_completion.assert_called_once_with(action, False, scope['control'])


if __name__ == '__main__':
    unittest.main()
