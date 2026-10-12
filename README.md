# Pokémon Lookup

Benjamin Franklin  
CSCI-2910 Lab 4

Search Pokémon by name or ID, view base stats and measurements, and select an ability to read its English description.

## Requirements and setup

Python 3.12 or later and an internet connection for uncached lookups.
PokéAPI requires no API key, so `.env` and `python-dotenv` are not needed.
`.gitignore` excludes environment files, virtual environments, Python bytecode,
and the generated cache.

From this project folder in Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pokemon_lookup.py
```

On macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python pokemon_lookup.py
```

## Using the application

1. Choose `1` to search and enter a name such as `pikachu` or an ID such as `25`.
2. Read the profile, including types, metric measurements, all six base stats,
   and the numbered abilities. Hidden abilities are labeled.
3. Enter an ability number to view its English description. Enter another number
   to view another ability, `0` to return to search, or `q` to exit.
4. Choose `0` at the main menu to exit. Ctrl+C or end of input also exits cleanly.

Names are trimmed and converted to lowercase. Enter API identifiers for special
names, such as `mr-mime`. This is a reference tool, not a battle simulator.

`cache.json` is saved beside the script. Successful resources are stored under
both name and ID URLs. Cached resources work without a network connection and
remain available after restarting. Delete `cache.json` while the program is
closed to refresh all data. Cache writes replace a temporary file so an interrupted
write is less likely to damage the existing cache. A failed disk write leaves
responses available in memory for the current session.

## Lab 3 implementation mapping

| Planned feature | Implementation |
| --- | --- |
| Search by name or positive ID | `normalize_query()` and `search_pokemon()` |
| CALL A Pokémon profile | `GET https://pokeapi.co/api/v2/pokemon/{name or id}/` |
| Types, six base stats, height and weight | `show_profile()`; height and weight each divided by 10 |
| CALL B selected ability | `show_ability()` follows `abilities[i].ability.url` |
| English description and fallback | English `short_effect`, then English flavor text with version group, then a missing-description message |
| Repeat searches and ability selection | `main()` menu loops |
| Persistent cache and canonical aliases | `APIClient.get_json()` and `save_cache()` |
| Timeout, HTTP errors, bad JSON, cache errors | `APIError` messages and menu recovery |

Only `APIClient.get_json()` calls `requests.get()`, with a 10-second timeout.
There is no request body and no automatic retry loop. Only a successful,
validated response is cached. No type, stat, language, version, image, or listing
URLs are requested. A cached lookup makes zero requests. An uncached profile plus
one uncached selected ability makes two requests.

## Verification

Run the offline tests from the project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Or on macOS/Linux: `.venv/bin/python -m unittest -v`.

**Result from development:** 16 tests passed. The tests use synthetic responses
and temporary caches. They exercise menus end to end, normalization, invalid input,
name/ID aliases across restart, units and shuffled stats, English text fallbacks,
HTTP 404/429/500/403, timeout/connection failure, invalid JSON and schema, damaged
cache files, failed writes, retrying an ability after failure, and graceful exit.

**Live verification still required:** Direct API traffic was blocked with HTTP 403
in the development environment. On your computer, with no existing cache:

1. Search for `pikachu`; check ID 25, Electric type, 0.4 m, 6 kg, and six base stats.
2. Select Static, then the hidden ability; confirm descriptions load and the latter
   is labeled hidden.
3. Return to search and enter `25`; then restart the program and repeat the search.
   After the first lookup, the saved resource should be reused.
4. Search for `not-a-real-pokemon-name`; confirm the not found message.
5. Try empty search input and an invalid ability number; confirm the menu remains usable.

A local connection problem or API outage can prevent fresh requests. Cached
profiles still work. A 403 is reported as an HTTP error rather than cached.

## Issues

- **Duplicate requests for names and IDs — resolved:** A name and numeric ID can identify the same Pokémon. The cache stores both canonical URLs so either search reuses the same response, including after restarting.
- **Missing English descriptions — resolved:** The formatter first uses English effect text, then English flavor text with its version group. When neither exists, it displays a missing-description message.
- **Invalid input and failed requests — resolved:** Invalid menu choices and searches are handled locally. HTTP errors, timeouts, and connection failures produce messages and return control to the menus. A failed ability request leaves the profile available.
- **Response validation — resolved:** Required-field validation uses explicit checks rather than assertions, so it remains active when Python optimization is enabled. Malformed optional description collections use the fallback message.
- **Damaged cache or failed writes — resolved:** An unreadable cache starts empty with a warning. Invalid cached resources are fetched again. Failed writes preserve data in memory for the current session.
- **Live API verification — pending:** Direct requests received HTTP 403 in the test environment. The 16 passing automated tests use simulated responses. Live success still needs to be checked on an unrestricted connection using the checklist above.

## Files

- `pokemon_lookup.py`: application source.
- `requirements.txt`: dependency specification.
- `test_pokemon_lookup.py`: offline automated tests.
- `.gitignore`: environment and generated-file exclusions.
- `README.md`: setup, usage, API calls, verification, and issue log.

## Sources

- [PokéAPI v2 documentation](https://pokeapi.co/docs/v2/)
- [Requests documentation](https://requests.readthedocs.io/en/latest/)
