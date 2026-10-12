"""Offline tests use synthetic responses; they make no real API requests."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import pokemon_lookup as app

POKEMON = {
    'id': 25, 'name': 'pikachu', 'height': 4, 'weight': 60,
    'types': [{'type': {'name': 'electric'}}],
    'stats': [{'stat': {'name': name}, 'base_stat': value} for name, value in
              zip(app.STAT_NAMES, [35, 55, 40, 50, 50, 90])],
    'abilities': [{'is_hidden': False, 'ability': {'name': 'static', 'url': app.BASE_URL + 'ability/9/'}},
                  {'is_hidden': True, 'ability': {'name': 'lightning-rod', 'url': app.BASE_URL + 'ability/31/'}}]
}
ABILITY = {'id': 9, 'name': 'static', 'effect_entries': [
    {'language': {'name': 'en'}, 'short_effect': 'Synthetic English effect for testing.'}]}


def response(data=POKEMON, status=200):
    result = Mock(status_code=status)
    result.json.return_value = copy.deepcopy(data)
    return result


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'cache.json'
        self.client = app.APIClient(self.path)

    def test_normalization(self):
        for text, expected in [(' PIKACHU ', 'pikachu'), ('025', '25'), ('mr-mime', 'mr-mime')]:
            self.assertEqual(app.normalize_query(text), expected)

    def test_invalid_input_has_no_http(self):
        with patch('pokemon_lookup.requests.get') as get:
            for value in ['', '0', '-1', '1.5', '../pikachu', 'a b', '１', '9' * 5000]:
                with self.assertRaises(ValueError):
                    app.search_pokemon(self.client, value)
            get.assert_not_called()

    def test_request_and_aliases_survive_restart(self):
        with patch('pokemon_lookup.requests.get', return_value=response()) as get:
            app.search_pokemon(self.client, ' PIKACHU ')
            app.search_pokemon(self.client, '25')
            app.search_pokemon(app.APIClient(self.path), 'pikachu')
            get.assert_called_once_with(app.BASE_URL + 'pokemon/pikachu/', timeout=10,
                                        headers={'Accept': 'application/json'})

    def test_ability_follows_link_and_marks_hidden(self):
        with patch('pokemon_lookup.requests.get', return_value=response({'id':31,'name':'lightning-rod'})) as get:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                app.show_ability(self.client, POKEMON, 1)
            get.assert_called_once_with(POKEMON['abilities'][1]['ability']['url'], timeout=10,
                                        headers={'Accept':'application/json'})
            self.assertIn('[Hidden]', out.getvalue())
            self.assertIn('No English description', out.getvalue())

    def test_profile_units_and_shuffled_stats(self):
        data = copy.deepcopy(POKEMON); data['stats'].reverse()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            app.show_profile(data)
        text = out.getvalue()
        self.assertIn('Height: 0.4 m | Weight: 6 kg', text)
        self.assertIn('Electric', text)
        for name in app.STAT_NAMES:
            self.assertIn(app.display_name(name), text)
        self.assertIn('[Hidden]', text)

    def test_effect_and_flavor_fallback(self):
        self.assertEqual(app.english_description(ABILITY), 'Synthetic English effect for testing.')
        data = {'flavor_text_entries': [
            {'language': {'name':'de'}, 'flavor_text':'Skip this'},
            {'language': {'name':'en'}, 'flavor_text':'Fallback\ntext.', 'version_group':{'name':'red-blue'}}]}
        self.assertEqual(app.english_description(data), 'Fallback text. (Version group: red-blue)')
        for data in [{}, {'effect_entries': None}, {'effect_entries': 12, 'flavor_text_entries': 'bad'}]:
            self.assertEqual(app.english_description(data), 'No English description is available.')

    def test_http_errors_not_cached(self):
        for status in [404, 429, 500, 403]:
            with patch('pokemon_lookup.requests.get', return_value=response(status=status)) as get:
                with self.assertRaises(app.APIError):
                    app.search_pokemon(self.client, 'pikachu')
                get.assert_called_once()
                self.assertEqual(self.client.cache, {})

    def test_network_errors_not_cached(self):
        for error in [requests.Timeout(), requests.ConnectionError()]:
            with patch('pokemon_lookup.requests.get', side_effect=error):
                with self.assertRaises(app.APIError):
                    app.search_pokemon(self.client, 'pikachu')
                self.assertEqual(self.client.cache, {})

    def test_bad_json_and_schema_not_cached(self):
        bad_json = response(); bad_json.json.side_effect = ValueError('bad JSON')
        for result in [bad_json, response({}), response([])]:
            with patch('pokemon_lookup.requests.get', return_value=result):
                with self.assertRaises(app.APIError):
                    app.search_pokemon(self.client, 'pikachu')
                self.assertEqual(self.client.cache, {})

    def test_corrupt_cache_recovers(self):
        for contents in ['{broken', '[]']:
            self.path.write_text(contents)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                client = app.APIClient(self.path)
            self.assertEqual(client.cache, {})
            self.assertIn('Warning', out.getvalue())

    def test_invalid_cached_resource_is_refetched(self):
        url = app.BASE_URL + 'pokemon/pikachu/'
        self.client.cache[url] = {}
        with patch('pokemon_lookup.requests.get', return_value=response()) as get:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.client.get_json(url)['id'], 25)
            get.assert_called_once()

    def test_failed_cache_write_keeps_memory(self):
        with patch('pokemon_lookup.requests.get', return_value=response()):
            with patch.object(Path, 'write_text', side_effect=OSError('denied')):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    app.search_pokemon(self.client, 'pikachu')
            self.assertIn('could not save', out.getvalue())
            with patch('pokemon_lookup.requests.get') as get:
                app.search_pokemon(self.client, '25')
                get.assert_not_called()

    def test_menus_search_select_repeat_and_exit(self):
        inputs = ['bad', '1', ' PIKACHU ', '99', '1', '1', '0', '1', '25', 'q']
        with patch('pokemon_lookup.APIClient', return_value=self.client):
            with patch('builtins.input', side_effect=inputs):
                with patch('pokemon_lookup.requests.get', side_effect=[response(), response(ABILITY)]) as get:
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        app.main()
                    self.assertEqual(get.call_count, 2)
                    self.assertEqual(out.getvalue().count('Synthetic English effect'), 2)

    def test_failed_ability_keeps_menu_available(self):
        with patch('pokemon_lookup.APIClient', return_value=self.client), patch('builtins.input', side_effect=['1','pikachu','1','1','q']):
            with patch('pokemon_lookup.requests.get', side_effect=[response(), response(status=500), response(ABILITY)]) as get:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    app.main()
                self.assertEqual(get.call_count, 3)
                self.assertIn('HTTP 500', out.getvalue())
                self.assertIn('Synthetic English effect', out.getvalue())

    def test_unknown_search_does_not_fetch_ability(self):
        with patch('pokemon_lookup.APIClient', return_value=self.client), patch('builtins.input', side_effect=['1','nonexistent','0']):
            with patch('pokemon_lookup.requests.get', return_value=response(status=404)) as get:
                with contextlib.redirect_stdout(io.StringIO()):
                    app.main()
                get.assert_called_once()

    def test_eof_exits_cleanly(self):
        with patch('pokemon_lookup.APIClient', return_value=self.client), patch('builtins.input', side_effect=EOFError):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                app.main()
            self.assertIn('Exiting', out.getvalue())


if __name__ == '__main__':
    unittest.main()
