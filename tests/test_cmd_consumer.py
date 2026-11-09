import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import cmd_consumer
from tests.test_dashboard_auth import api, asgi_request


class CommandQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bot = SimpleNamespace(handle_command=Mock(), log=Mock())
        for module, name, value in (
            (api, "CMD_DIR", self.tmp.name),
            (api, "_rate_limit_state", {}),
            (cmd_consumer, "CMD_FILE", str(self.directory / "command.json")),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def dispatch(self, action, endpoint="/api/v1/command", body=None):
        status, cookies, payload = asgi_request(
            api.app,
            "POST",
            endpoint,
            headers={"X-Control-API-Key": api.CONTROL_API_KEY},
            body=body or {"action": action},
        )
        self.assertEqual(status, 200)
        self.assertEqual(cookies, [])
        return json.loads(payload)

    def write_command(self, name, data, mode=0o600):
        path = self.directory / name
        path.write_text(json.dumps(data))
        path.chmod(mode)
        return path

    def test_two_commands_queued_in_order_and_consumed_once(self):
        responses = [self.dispatch("/panic"), self.dispatch("/close BTCUSDT")]
        files = sorted(self.directory.glob("*.json"))
        self.assertEqual(len(files), 2)
        for response, path, action in zip(
            responses, files, ("/panic", "/close BTCUSDT")
        ):
            self.assertEqual(
                response,
                {"ok": True, "status": "queued", "action": action, "id": path.stem},
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        cmd_consumer.consume_command_file(self.bot)
        self.assertEqual(
            [c.args[0] for c in self.bot.handle_command.call_args_list],
            ["/panic", "/close BTCUSDT"],
        )
        self.assertEqual(list(self.directory.iterdir()), [])
        cmd_consumer.consume_command_file(self.bot)
        self.assertEqual(self.bot.handle_command.call_count, 2)

    def test_file_published_during_consumption_survives_for_next_run(self):
        self.write_command("command.json", {"commands": [{"action": "/panic"}]})
        real_load = json.load

        def publish_after_read(handle):
            data = real_load(handle)
            self.dispatch("/close BTCUSDT")
            return data

        with patch.object(cmd_consumer.json, "load", side_effect=publish_after_read):
            cmd_consumer.consume_command_file(self.bot)
        self.assertEqual(
            [c.args[0] for c in self.bot.handle_command.call_args_list], ["/panic"]
        )
        self.assertEqual(len(list(self.directory.glob("*.json"))), 1)
        cmd_consumer.consume_command_file(self.bot)
        self.assertEqual(
            [c.args[0] for c in self.bot.handle_command.call_args_list],
            ["/panic", "/close BTCUSDT"],
        )

    def test_bad_files_removed_without_blocking_next_valid_command(self):
        self.write_command("cmd-0001.json", {"commands": [{"action": "/panic"}]}, 0o666)
        (self.directory / "cmd-0002.json").write_text("{broken")
        (self.directory / "cmd-0002.json").chmod(0o600)
        self.write_command("cmd-0003.json", {"commands": "invalid"})
        self.write_command(
            "cmd-0004.json",
            {"commands": [{"action": "/dump_db"}, {"action": "/pause"}]},
        )
        tmp = self.write_command("cmd-0000.tmp", {"commands": [{"action": "/panic"}]})
        cmd_consumer.consume_command_file(self.bot)
        self.assertEqual(
            [c.args[0] for c in self.bot.handle_command.call_args_list], ["/pause"]
        )
        self.assertEqual(list(self.directory.iterdir()), [tmp])
        self.assertGreaterEqual(self.bot.log.call_count, 4)

    def test_symlink_is_removed_without_reading_target(self):
        target = self.write_command("ignored.tmp", {"commands": [{"action": "/panic"}]})
        link = self.directory / "cmd-0001.json"
        link.symlink_to(target)
        cmd_consumer.consume_command_file(self.bot)
        self.bot.handle_command.assert_not_called()
        self.assertFalse(link.is_symlink())
        self.assertTrue(target.exists())
        self.bot.log.assert_called()

    def test_legacy_command_consumed_once(self):
        self.write_command("command.json", {"commands": [{"action": "/resume"}]})
        cmd_consumer.consume_command_file(self.bot)
        cmd_consumer.consume_command_file(self.bot)
        self.bot.handle_command.assert_called_once_with("/resume")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_other_consumer_claim_does_not_block_later_files(self):
        self.write_command("cmd-0001.json", {"commands": [{"action": "/panic"}]})
        self.write_command("cmd-0002.json", {"commands": [{"action": "/pause"}]})
        real_rename = os.rename

        def competing_claim(source, destination):
            if str(source).endswith("cmd-0001.json"):
                real_rename(source, destination)
                raise FileNotFoundError("claimed by another consumer")
            return real_rename(source, destination)

        with patch.object(cmd_consumer.os, "rename", side_effect=competing_claim):
            cmd_consumer.consume_command_file(self.bot)
        self.bot.handle_command.assert_called_once_with("/pause")

    def test_symlinked_directory_cannot_consume_or_delete_target(self):
        command = self.write_command(
            "cmd-0001.json", {"commands": [{"action": "/panic"}]}
        )
        original = command.read_bytes()
        link = self.directory / "queue-link"
        link.symlink_to(self.directory, target_is_directory=True)
        with patch.object(cmd_consumer, "CMD_FILE", str(link / "command.json")):
            cmd_consumer.consume_command_file(self.bot)
        self.bot.handle_command.assert_not_called()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual(set(self.directory.iterdir()), {link, command})
        self.bot.log.assert_called()

    def test_world_writable_directory_cannot_consume(self):
        command = self.write_command(
            "cmd-0001.json", {"commands": [{"action": "/panic"}]}
        )
        original = command.read_bytes()
        self.directory.chmod(0o777)
        self.addCleanup(self.directory.chmod, 0o700)
        cmd_consumer.consume_command_file(self.bot)
        self.bot.handle_command.assert_not_called()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual(list(self.directory.iterdir()), [command])
        self.bot.log.assert_called()

    def test_private_directory_still_consumes(self):
        self.directory.chmod(0o700)
        self.write_command("cmd-0001.json", {"commands": [{"action": "/pause"}]})
        cmd_consumer.consume_command_file(self.bot)
        self.bot.handle_command.assert_called_once_with("/pause")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_sibling_control_endpoints_preserve_actions(self):
        for endpoint, body, action in (
            ("/api/v1/trade/close", {"symbol": "btcusdt"}, "/close BTCUSDT"),
            ("/api/v1/trade/breakeven", {"symbol": "ethusdt"}, "/breakeven ETHUSDT"),
            ("/api/v1/scan", None, "/scan"),
            ("/api/v1/sync", None, "/sync_wallet"),
        ):
            response = self.dispatch(action, endpoint, body)
            self.assertEqual(response["action"], action)
            self.assertEqual(response["status"], "queued")
