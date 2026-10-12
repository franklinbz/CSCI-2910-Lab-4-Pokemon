"""Lab 4: Pokémon profiles and ability descriptions from PokéAPI."""
import json
import re
from pathlib import Path

import requests

BASE_URL = 'https://pokeapi.co/api/v2/'
CACHE_FILE = Path(__file__).with_name('cache.json')
STAT_NAMES = ('hp', 'attack', 'defense', 'special-attack', 'special-defense', 'speed')


class APIError(Exception):
    """An expected request or response problem that the menus can report."""


def resource_kind(url):
    match = re.fullmatch(re.escape(BASE_URL) + r'(pokemon|ability)/([a-z0-9]+(?:-[a-z0-9]+)*)/', url)
    if not match:
        raise APIError('The response contains an unsupported resource URL.')
    return match.group(1)


def validate_resource(url, data):
    """Check fields needed by the interface before saving or displaying data."""
    kind = resource_kind(url)
    def require(condition):
        if not condition:
            raise ValueError("Invalid field")
    try:
        require(isinstance(data, dict))
        require(type(data['id']) is int and data['id'] > 0)
        require(isinstance(data['name'], str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', data['name']))
        if kind == 'pokemon':
            for field in ('height', 'weight'):
                require(type(data[field]) is int and data[field] >= 0)
            require(isinstance(data['types'], list) and data['types'])
            for entry in data['types']:
                require(isinstance(entry['type']['name'], str))
            require(isinstance(data['stats'], list))
            stats = {entry['stat']['name']: entry['base_stat'] for entry in data['stats']}
            require(all(type(stats[name]) is int and stats[name] >= 0 for name in STAT_NAMES))
            require(isinstance(data['abilities'], list))
            for entry in data['abilities']:
                require(isinstance(entry['ability']['name'], str))
                require(type(entry['is_hidden']) is bool)
                require(resource_kind(entry['ability']['url']) == 'ability')
    except (AssertionError, KeyError, TypeError, ValueError):
        raise APIError('The API response is missing or has invalid required fields.') from None
    return data


class APIClient:
    """All HTTP access and persistent cache handling live here."""
    def __init__(self, cache_file=CACHE_FILE):
        self.cache_file = Path(cache_file)
        self.cache = {}
        try:
            data = json.loads(self.cache_file.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('Cache must contain an object.')
            self.cache = data
        except FileNotFoundError:
            pass  # Normal first launch.
        except (OSError, ValueError):
            print('Warning: cache could not be read. Starting with an empty cache.')

    def save_cache(self):
        temporary = self.cache_file.with_name(self.cache_file.name + '.tmp')
        try:
            temporary.write_text(json.dumps(self.cache, indent=2), encoding='utf-8')
            temporary.replace(self.cache_file)
        except OSError:
            print('Warning: could not save cache. Data remains available this session.')

    def get_json(self, url):
        """The only HTTP call site; successful resources also get ID/name aliases."""
        kind = resource_kind(url)
        if url in self.cache:
            try:
                return validate_resource(url, self.cache[url])
            except APIError:
                del self.cache[url]
                print('Warning: invalid cached resource. Fetching a fresh copy.')
        try:
            response = requests.get(url, timeout=10, headers={'Accept': 'application/json'})
        except requests.Timeout:
            raise APIError('The request timed out. Please try again later.') from None
        except requests.RequestException:
            raise APIError('Could not connect to PokéAPI. Check your connection and try later.') from None
        if response.status_code == 404:
            raise APIError('Resource not found. Check the Pokémon name or ID.')
        if response.status_code == 429:
            raise APIError('PokéAPI is limiting requests. Please try again later.')
        if response.status_code != 200:
            raise APIError(f'PokéAPI returned HTTP {response.status_code}. Please try again later.')
        try:
            data = response.json()
        except ValueError:
            raise APIError('PokéAPI returned invalid JSON. Please try again later.') from None
        validate_resource(url, data)
        for alias in (url, f"{BASE_URL}{kind}/{data['id']}/", f"{BASE_URL}{kind}/{data['name']}/"):
            self.cache[alias] = data
        self.save_cache()
        return data


def normalize_query(query):
    query = query.strip().lower()
    if query.isascii() and query.isdecimal():
        # Avoid Python's huge-integer conversion limit on malicious or accidental input.
        query = query.lstrip('0')
        if query and len(query) <= 10:
            return query
    elif re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', query):
        return query
    raise ValueError('Enter a positive ID or API name such as pikachu or mr-mime.')


def search_pokemon(client, query):
    # CALL A: Pokémon profile, with no JSON request body.
    return client.get_json(f'{BASE_URL}pokemon/{normalize_query(query)}/')


def display_name(name):
    return name.replace('-', ' ').title()


def show_profile(data):
    print(f"\n{display_name(data['name'])} (ID {data['id']})")
    print('Types: ' + ', '.join(display_name(item['type']['name']) for item in data['types']))
    print(f"Height: {data['height'] / 10:g} m | Weight: {data['weight'] / 10:g} kg")
    print('Base stats:')
    stats = {item['stat']['name']: item['base_stat'] for item in data['stats']}
    for name in STAT_NAMES:
        print(f'  {display_name(name):16} {stats[name]}')
    print('Abilities:')
    for number, entry in enumerate(data['abilities'], 1):
        hidden = ' [Hidden]' if entry['is_hidden'] else ''
        print(f"  {number}. {display_name(entry['ability']['name'])}{hidden}")
    if not data['abilities']:
        print('  None listed.')


def english_description(data):
    effects = data.get('effect_entries')
    for entry in effects if isinstance(effects, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get('language'), dict):
            text = entry.get('short_effect')
            if entry['language'].get('name') == 'en' and isinstance(text, str) and text.strip():
                return ' '.join(text.split())
    flavors = data.get('flavor_text_entries')
    for entry in flavors if isinstance(flavors, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get('language'), dict):
            text = entry.get('flavor_text')
            if entry['language'].get('name') == 'en' and isinstance(text, str) and text.strip():
                version = entry.get('version_group') or {}
                version_name = version.get('name', 'unspecified') if isinstance(version, dict) else 'unspecified'
                return f"{' '.join(text.split())} (Version group: {version_name})"
    return 'No English description is available.'


def show_ability(client, data, selection):
    entry = data['abilities'][selection]
    # CALL B: Follow only the selected ability URL; no other resource links.
    ability = client.get_json(entry['ability']['url'])
    hidden = ' [Hidden]' if entry['is_hidden'] else ''
    print(f"\n{display_name(ability['name'])}{hidden}")
    print(english_description(ability))


def main():
    client = APIClient()
    try:
        while True:
            print('\nPokémon Lookup\n1. Search Pokémon\n0. Exit')
            choice = input('Choose: ').strip()
            if choice == '0':
                return
            if choice != '1':
                print('Choose 1 or 0.')
                continue
            try:
                data = search_pokemon(client, input('Pokémon name or ID: '))
            except (ValueError, APIError) as error:
                print(error)
                continue
            show_profile(data)
            while True:
                choice = input('\nAbility number, 0 for another search, or q to exit: ').strip().lower()
                if choice == 'q':
                    return
                if choice == '0':
                    break
                options = {str(i + 1): i for i in range(len(data['abilities']))}
                if choice not in options:
                    print('Choose a listed ability number, 0, or q.')
                    continue
                try:
                    show_ability(client, data, options[choice])
                except APIError as error:
                    print(error)
    except (EOFError, KeyboardInterrupt):
        print('\nExiting Pokémon Lookup.')


if __name__ == '__main__':
    main()
