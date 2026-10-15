# Discrimination proofs — dashboard (`sazed painel`)

Date: 2026-10-15. Branch `feat/dashboard`. Each proof applies one realistic mutation, runs the
named tests, and restores the file. A proof that stays green is reported as a finding, not
bent until it fails. Output below is pytest's, trimmed to the failure lines.

## Findings

- **The `is_file` guard in `CoppermindReader.connect` is not load-bearing.** Removing it alone
  leaves every test green: SQLite's `mode=ro` already refuses to create a missing file. The
  first version of the "never creates the database" test pointed at a missing *folder*, which
  SQLite cannot create either, so it could not fail; a second test now uses an existing folder,
  and the combined mutation (guard removed and `mode=rwc`) turns it red. The guarantee lives in
  `mode=ro`; the guard only supplies the friendly "nada foi gravado" message. Both are kept,
  with a comment saying which one is the rule.
- **The startup line was invisible with a piped stdout** (found in the end-to-end run, not by a
  test). Fixed with a flushing `say()`; the last proof below shows the new test failing without
  the flush.

## Read-only coppermind, ledger, redaction, failure rule

### read-only: mode=ro becomes mode=rwc
mutation in src/sazed/adapters/sqlite/reader.py: '?mode=ro"' -> '?mode=rwc"'
```
E       Failed: DID NOT RAISE OperationalError
FAILED tests/adapters/test_sqlite_reader.py::test_connection_is_read_only - F...
1 failed, 11 passed in 0.30s
```

### never creates: the is_file guard removed (not load-bearing)
mutation in src/sazed/adapters/sqlite/reader.py: 'if not self._path.is_file():' -> 'if False:'
```
12 passed in 0.22s
```

### never creates: guard removed and mode=rwc
mutation in src/sazed/adapters/sqlite/reader.py: 'if not self._path.is_file():' -> 'if False:'
mutation in src/sazed/adapters/sqlite/reader.py: '?mode=ro"' -> '?mode=rwc"'
```
E       AssertionError: assert not True
E        +  where True = exists()
E        +    where exists = WindowsPath('C:/Users/Usuario/AppData/Local/Temp/pytest-of-Usuario/pytest-100/test_missing_database_is_not_c0/coppermind.db').exists
E       Failed: DID NOT RAISE OperationalError
FAILED tests/adapters/test_sqlite_reader.py::test_missing_database_is_not_created
FAILED tests/adapters/test_sqlite_reader.py::test_connection_is_read_only - F...
2 failed, 10 passed in 0.30s
```

### ledger: unknown lines filtered out
mutation in src/sazed/interfaces/dashboard/ledger.py: 'for line in lines if line.strip())' -> 'for line in lines if line.strip() and _entry(line).kind != "raw")'
```
E       AssertionError: assert ['Task 1: sta...ss port', ...] == ['Task 1: sta...learned', ...]
E         
E         At index 4 diff: 'Final: Ruling: power intents are never learned' != 'algo que ninguém previu'
E         Right contains one more item: 'Final: fixed the Desinstalação filter'
E         Use -v to get more diff
E       ValueError: not enough values to unpack (expected 1, got 0)
E       ValueError: not enough values to unpack (expected 1, got 0)
E       ValueError: not enough values to unpack (expected 1, got 0)
FAILED tests/interfaces/dashboard/test_ledger.py::test_every_non_blank_line_is_kept_in_order
FAILED tests/interfaces/dashboard/test_ledger.py::test_line_kinds[algo que ningu\xe9m previu-raw-None-algo que ningu\xe9m previu]
FAILED tests/interfaces/dashboard/test_ledger.py::test_line_kinds[Task x: started-raw-None-Task x: started]
FAILED tests/interfaces/dashboard/test_ledger.py::test_line_kinds[## Notes-raw-None-## Notes]
4 failed, 26 passed in 0.11s
```

### redaction: exact key name instead of contains
mutation in src/sazed/interfaces/dashboard/redact.py: 'return any(part in lowered for part in SENSITIVE_PARTS)' -> 'return lowered in SENSITIVE_PARTS'
```
E       AssertionError: assert False is True
E        +  where False = is_sensitive('api_key')
E       AssertionError: assert False is True
E        +  where False = is_sensitive('github_token')
E       AssertionError: assert False is True
E        +  where False = is_sensitive('client_secret')
E       AssertionError: assert {'user': {'na..._exec': 0.94}} == {'user': {'na..._exec': 0.94}}
E         
E         Omitting 3 identical items, use -vv to show
E         Differing items:
E         {'service': {'api_key': 'abc', 'nested': [{'token': '••• (oculto)'}, {'ok': 1}]}} != {'service': {'api_key': '••• (oculto)', 'nested': [{'token': '••• (oculto)'}, {'ok': 1}]}}
E         Use -v to get more diff
E       AssertionError: assert [('secrets.plain', 'x')] == [('secrets', '••• (oculto)')]
E         
E         At index 0 diff: ('secrets.plain', 'x') != ('secrets', '••• (oculto)')
E         Use -v to get more diff
FAILED tests/interfaces/dashboard/test_redact.py::test_is_sensitive[api_key-True]
FAILED tests/interfaces/dashboard/test_redact.py::test_is_sensitive[github_token-True]
FAILED tests/interfaces/dashboard/test_redact.py::test_is_sensitive[client_secret-True]
FAILED tests/interfaces/dashboard/test_redact.py::test_redact_is_recursive_and_keeps_other_values
FAILED tests/interfaces/dashboard/test_redact.py::test_config_rows_redact_by_any_path_segment
5 failed, 7 passed in 0.10s
```

### redaction: config_rows forgets to check the leaf key
mutation in src/sazed/interfaces/dashboard/redact.py: 'if is_sensitive(str(key)):\n                rows' -> 'if False:\n                rows'
```
E       AssertionError: assert [('user.name'...', 'arquivo')] == [('user.name'...', 'arquivo')]
E         
E         At index 4 diff: ('service.token', 'xyz', 'arquivo') != ('service.token', '••• (oculto)', 'arquivo')
E         Use -v to get more diff
E       AssertionError: assert [('secrets.plain', 'x')] == [('secrets', '••• (oculto)')]
E         
E         At index 0 diff: ('secrets.plain', 'x') != ('secrets', '••• (oculto)')
E         Use -v to get more diff
FAILED tests/interfaces/dashboard/test_redact.py::test_config_rows_flatten_and_mark_the_origin
FAILED tests/interfaces/dashboard/test_redact.py::test_config_rows_redact_by_any_path_segment
2 failed, 10 passed in 0.09s
```

### failure rule: 'corrected' forgotten
mutation in src/sazed/interfaces/dashboard/stats.py: 'frozenset({"denied", "corrected"})' -> 'frozenset({"denied"})'
```
E       AssertionError: assert {3, 7, 9, 10, 11, 12, ...} == {3, 4, 7, 8, 9, 10, ...}
E         
E         Extra items in the right set:
E         32
E         4
E         100
E         8
E         104...
E         
E         ...Full output truncated (4 lines hidden), use '-vv' to show
FAILED tests/interfaces/dashboard/test_pure_modules.py::test_is_failure_agrees_with_the_store
1 failed, 5 passed in 0.53s
```

## Server, launcher and listing

### loopback: HOST becomes 0.0.0.0 (all interfaces)
mutation in src/sazed/interfaces/dashboard/server.py: 'HOST = "127.0.0.1"' -> 'HOST = "0.0.0.0"'
```
E           AssertionError: assert '0.0.0.0' == '127.0.0.1'
E             
E             - 127.0.0.1
E             + 0.0.0.0
FAILED tests/interfaces/dashboard/test_server.py::test_binds_to_loopback_only
1 failed, 38 deselected in 1.75s
```

### GET only: the catch-all for other verbs removed
mutation in src/sazed/interfaces/dashboard/server.py: '        if name.startswith("do_"):\n            return self._refuse_method' -> '        if False:\n            return self._refuse_method'
```
E       assert 501 == 405
E       assert 501 == 405
E       assert 501 == 405
E       assert 501 == 405
E       assert 501 == 405
E       assert 501 == 405
E       assert 501 == 405
E       assert 501 == 405
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[POST]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[PUT]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[DELETE]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[PATCH]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[OPTIONS]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[HEAD]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[TRACE]
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[PROPFIND]
8 failed, 31 deselected in 0.87s
```

### GET only: someone adds do_POST = do_GET
mutation in src/sazed/interfaces/dashboard/server.py: '    def _send_json(\n' -> '    def do_POST(self) -> None:\n        self.do_GET()\n\n    def _send_json(\n'
```
E       assert 200 == 405
E       AssertionError: assert {'do_GET', 'do_POST'} == {'do_GET'}
E         
E         Extra items in the left set:
E         'do_POST'
E         Use -v to get more diff
FAILED tests/interfaces/dashboard/test_server.py::test_only_get_is_served[POST]
FAILED tests/interfaces/dashboard/test_server.py::test_every_handler_method_other_than_get_refuses
2 failed, 7 passed, 30 deselected in 0.86s
```

### Host header check removed
mutation in src/sazed/interfaces/dashboard/server.py: 'if not self._host_allowed():' -> 'if False:'
```
E       assert 200 == 403
E       assert 200 == 403
FAILED tests/interfaces/dashboard/test_server.py::test_foreign_host_header_is_refused[evil.example:80]
FAILED tests/interfaces/dashboard/test_server.py::test_foreign_host_header_is_refused[192.168.0.10]
2 failed, 1 passed, 36 deselected in 0.62s
```

### an unexpected error's text sent to the page
mutation in src/sazed/interfaces/dashboard/api.py: '        except Exception:\n            log.exception("dashboard endpoint %s failed", path)\n            return 500, {"error": GENERIC_ERROR}' -> '        except Exception as exc:\n            log.exception("dashboard endpoint %s failed", path)\n            return 500, {"error": str(exc)}'
```
E           assert (b'SELECT' not in b'{"error": "SELECT secret FROM episodes -- internal detail"}')
ERROR    sazed.interfaces.dashboard.api:api.py:170 dashboard endpoint /api/episodes failed
FAILED tests/interfaces/dashboard/test_server.py::test_an_unexpected_failure_never_leaks
1 failed, 38 deselected in 0.65s
```

### startup message not flushed
mutation in src/sazed/interfaces/dashboard/launch.py: 'print(text, flush=True)' -> 'print(text)'
```
E       AssertionError: assert 'write:\n' == 'flush'
E         
E         - flush
E         + write:
FAILED tests/interfaces/dashboard/test_launch.py::test_messages_are_flushed_so_a_piped_console_sees_them
1 failed, 3 passed in 0.59s
```

### listing skills drift from the wired skills
mutation in src/sazed/runtime/insight.py: 'return [AppsSkill(inert, inert), VolumeSkill(inert)]' -> 'return [AppsSkill(inert, inert)]'
```
E       AssertionError: assert [('apps', ['a...fechar_app'])] == [('apps', ['a...olume_mudo'])]
E         
E         Right contains one more item: ('volume', ['volume_definir', 'volume_aumentar', 'volume_diminuir', 'volume_mudo'])
E         Use -v to get more diff
E       AssertionError: assert {'AppCatalog', 'AppLauncher'} == {'AppCatalog'...AudioControl'}
E         
E         Extra items in the right set:
E         'AudioControl'
E         Use -v to get more diff
FAILED tests/runtime/test_insight.py::test_listing_skills_match_the_wired_skills
FAILED tests/runtime/test_insight.py::test_every_port_has_a_pt_br_description
2 failed, 18 passed in 0.30s
```
