import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import AsyncMock, patch

spec = importlib.util.spec_from_file_location('ctl', Path(__file__).resolve().parents[1] / 'ctl.py')
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)

class FakeServerList:
    user_tier = 1
    def __init__(self, servers): self.logicals = servers
    @staticmethod
    def get_servers_in_country_code(servers, country):
        return (s for s in servers if s.country.lower() == country.lower())
    @staticmethod
    def get_servers_in_city(servers, city):
        return (s for s in servers if s.city.lower() == city.lower())
    @staticmethod
    def get_available_servers(servers, tier):
        return (s for s in servers if s.enabled and s.tier <= tier)
    @staticmethod
    def get_servers_with_features(servers, exclude_features):
        return (s for s in servers if not s.features & exclude_features)
    @staticmethod
    def get_fastest_server(servers): return min(servers, key=lambda s: s.score, default=None)

class SelectionTests(unittest.TestCase):
    def test_city_is_constrained_to_country_and_available_standard_servers(self):
        def server(country='US', **kw):
            return SimpleNamespace(**dict(dict(country=country, city='Shared City', score=5, enabled=True, tier=1, features=0), **kw))
        correct = server(score=10)
        servers = FakeServerList([server('CA', score=1), server(enabled=False), server(tier=2), server(features=1), server(features=2), correct])
        self.assertIs(ctl.select_server(servers, 'city', 'shared city', 'us'), correct)
        self.assertIsNone(ctl.select_server(servers, 'city', 'shared city', 'DE'))

    def test_city_country_argument_parses_without_losing_spaces(self):
        args = ctl.parse_args(['connect', 'city', 'Shared City', '--country', 'US'])
        self.assertEqual((args.target, args.value, args.country), ('city', 'Shared City', 'US'))

class StateTests(unittest.IsolatedAsyncioTestCase):
    async def test_waiter_does_not_miss_transition_during_registration(self):
        target = SimpleNamespace(type=0)
        connector = SimpleNamespace(current_state=SimpleNamespace(type=1))
        connector.register = lambda waiter: setattr(connector, 'current_state', target)
        unregistered = []
        connector.unregister = unregistered.append
        result = await ctl._wait_for(connector, {0}, .05)
        self.assertIs(result, target)
        self.assertEqual(len(unregistered), 1)

    async def test_waiter_unregisters_on_timeout(self):
        unregistered = []
        connector = SimpleNamespace(current_state=SimpleNamespace(type=1), register=lambda w: None, unregister=unregistered.append)
        with self.assertRaises(TimeoutError):
            await ctl._wait_for(connector, {0}, .01)
        self.assertEqual(len(unregistered), 1)

    async def test_disconnect_error_is_reported_and_no_refresh_is_requested(self):
        enum = ModuleType('proton.vpn.connection.enum')
        enum.ConnectionStateEnum = SimpleNamespace(DISCONNECTED=0, ERROR=4)
        connector = SimpleNamespace(is_connection_active=True, disconnect=AsyncMock())
        api = AsyncMock(return_value=(None, connector, None, None, None))
        with patch.dict('sys.modules', {'proton.vpn.connection.enum': enum}), \
             patch.object(ctl, '_api_session', api), \
             patch.object(ctl, '_wait_for', AsyncMock(return_value=SimpleNamespace(type=4))):
            with self.assertRaisesRegex(RuntimeError, 'failed to disconnect'):
                await ctl._disconnect()
        api.assert_awaited_once_with(refresh=False)
        connector.disconnect.assert_awaited_once()

    async def test_confirmed_disconnection_returns_success(self):
        enum = ModuleType('proton.vpn.connection.enum')
        enum.ConnectionStateEnum = SimpleNamespace(DISCONNECTED=0, ERROR=4)
        connector = SimpleNamespace(is_connection_active=True, disconnect=AsyncMock())
        with patch.dict('sys.modules', {'proton.vpn.connection.enum': enum}), \
             patch.object(ctl, '_api_session', AsyncMock(return_value=(None, connector, None, None, None))), \
             patch.object(ctl, '_wait_for', AsyncMock(return_value=SimpleNamespace(type=0))):
            result = await ctl._disconnect()
        self.assertTrue(result['ok'])
        self.assertFalse(result['connected'])

if __name__ == '__main__': unittest.main()
