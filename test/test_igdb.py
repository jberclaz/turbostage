import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import requests

from turbostage import igdb_client
from turbostage.igdb_client import IgdbClient


def _response(json_data=None, content=b"[]"):
    response = MagicMock()
    response.json.return_value = json_data
    response.content = content
    return response


class _FakeCredentials(unittest.TestCase):
    def setUp(self):
        creds = patch("turbostage.igdb_client.load_credentials", return_value=("cid", "secret"))
        creds.start()
        self.addCleanup(creds.stop)


class TestIgdbSearch(_FakeCredentials):
    """Tests for the search functionality of the IGDB client."""

    def setUp(self):
        super().setUp()
        self.auth_patch = patch.object(IgdbClient, "_get_auth", return_value="mock_token")
        self.auth_patch.start()
        self.post_patch = patch("turbostage.igdb_client.requests.post")
        self.mock_post = self.post_patch.start()
        self.client = IgdbClient()

    def tearDown(self):
        self.post_patch.stop()
        self.auth_patch.stop()

    def test_simple_search(self):
        """Test searching for games by name."""
        self.mock_post.return_value = _response(content=b'[{"id": 123, "name": "Test Drive"}]')

        result = self.client.search_games("Drive")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 123)
        self.assertEqual(result[0]["name"], "Test Drive")

        # Verify API call parameters
        self.mock_post.assert_called_once()
        args, kwargs = self.mock_post.call_args
        self.assertEqual(args[0], igdb_client.IGDB_API_URL + "games")
        self.assertIn('search "Drive"', kwargs["data"])
        self.assertIn("platforms = (13)", kwargs["data"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer mock_token")
        self.assertEqual(kwargs["headers"]["Client-ID"], "cid")
        self.assertEqual(kwargs["timeout"], igdb_client.REQUEST_TIMEOUT_S)


class TestIgdbAuthentication(_FakeCredentials):
    """The client must be constructible offline; it authenticates on first use."""

    def test_construction_does_not_touch_network(self):
        with patch("turbostage.igdb_client.requests.post") as mock_post:
            IgdbClient()
        mock_post.assert_not_called()

    def test_authenticates_once_with_timeout(self):
        with patch("turbostage.igdb_client.requests.post") as mock_post:
            mock_post.return_value = _response(json_data={"access_token": "tok"})
            client = IgdbClient()
            client.search_games("Doom")
            client.search_games("Quake")
        auth_calls = [c for c in mock_post.call_args_list if "id.twitch.tv" in c.args[0]]
        self.assertEqual(len(auth_calls), 1)
        self.assertEqual(auth_calls[0].kwargs["timeout"], igdb_client.AUTH_TIMEOUT_S)
        self.assertEqual(auth_calls[0].kwargs["params"]["client_id"], "cid")
        self.assertEqual(auth_calls[0].kwargs["params"]["client_secret"], "secret")
        self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_offline_request_raises_and_retries_later(self):
        with patch("turbostage.igdb_client.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("offline")
            client = IgdbClient()
            with self.assertRaises(requests.exceptions.RequestException):
                client.search_games("Doom")

            mock_post.side_effect = None
            mock_post.return_value = _response(json_data={"access_token": "tok"})
            self.assertEqual(client.search_games("Doom"), [])


class TestIgdbRateLimit(_FakeCredentials):
    def _http_error(self, status):
        response = MagicMock()
        response.status_code = status
        return requests.exceptions.HTTPError(response=response)

    def setUp(self):
        super().setUp()
        patches = [
            patch.object(IgdbClient, "_get_auth", return_value="tok"),
            patch("turbostage.igdb_client.time.sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = IgdbClient()

    def test_retries_rate_limit_then_succeeds(self):
        with patch.object(IgdbClient, "_api_request", side_effect=[self._http_error(429), b"[]"]) as api:
            self.assertIsNone(self.client.get_game_info(1))
        self.assertEqual(api.call_count, 2)

    def test_gives_up_after_bounded_retries(self):
        with patch.object(IgdbClient, "_api_request", side_effect=self._http_error(429)) as api:
            with self.assertRaises(requests.exceptions.HTTPError):
                self.client.get_game_info(1)
        self.assertEqual(api.call_count, igdb_client.RATE_LIMIT_RETRIES + 1)

    def test_other_http_errors_are_not_retried(self):
        with patch.object(IgdbClient, "_api_request", side_effect=self._http_error(500)) as api:
            with self.assertRaises(requests.exceptions.HTTPError):
                self.client.get_game_info(1)
        self.assertEqual(api.call_count, 1)


class TestIgdbCredentials(unittest.TestCase):
    def test_environment_takes_precedence(self):
        with patch.dict(os.environ, {"IGDB_CLIENT_ID": "env_id", "IGDB_CLIENT_SECRET": "env_secret"}):
            self.assertEqual(igdb_client.load_credentials(), ("env_id", "env_secret"))

    def test_falls_back_to_generated_module(self):
        module = types.SimpleNamespace(CLIENT_ID="build_id", CLIENT_SECRET="build_secret")
        with (
            patch.dict(os.environ, {"IGDB_CLIENT_ID": "", "IGDB_CLIENT_SECRET": ""}),
            patch.dict(sys.modules, {"turbostage._igdb_credentials": module}),
        ):
            self.assertEqual(igdb_client.load_credentials(), ("build_id", "build_secret"))

    def test_missing_credentials_behave_like_unreachable_igdb(self):
        with (
            patch("turbostage.igdb_client.load_credentials", return_value=None),
            patch("turbostage.igdb_client.requests.post") as mock_post,
        ):
            with self.assertRaises(requests.exceptions.RequestException):
                IgdbClient().search_games("Doom")
        mock_post.assert_not_called()

    def test_no_credentials_in_source(self):
        from turbostage import constants

        self.assertFalse(hasattr(constants, "IGDB_CLIENT_SECRET"))

    def test_generator_script_writes_importable_module(self):
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "write_igdb_credentials.py")
        spec = importlib.util.spec_from_file_location("write_igdb_credentials", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "_creds.py")
            with (
                patch.object(module, "TARGET", target),
                patch.dict(os.environ, {"IGDB_CLIENT_ID": "id'1", "IGDB_CLIENT_SECRET": "s\\2"}),
            ):
                self.assertEqual(module.main(), 0)
            values = {}
            with open(target) as f:
                exec(f.read(), values)
            self.assertEqual((values["CLIENT_ID"], values["CLIENT_SECRET"]), ("id'1", "s\\2"))

            with patch.dict(os.environ, {"IGDB_CLIENT_ID": "", "IGDB_CLIENT_SECRET": ""}):
                self.assertEqual(module.main(), 1)


if __name__ == "__main__":
    unittest.main()
