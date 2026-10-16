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

## Round 2 — editable learnings (forget/undo, examples, aliases, labels, notes)

### Findings

- **Native crash: onnxruntime imported after WinRT.** Found in the end-to-end run, not by a
  unit test: an alias write scanned the Store catalog (WinRT), and the next "teach a phrase"
  imported onnxruntime and killed the dashboard with an access violation. Sazed itself is safe
  only because `build_default_app` happens to import the embedder first. Fixed in
  `runtime/editing.real_catalog`; `tests/runtime/test_editing_windows.py` (`-m windows`)
  reproduces it in a subprocess. Without the fix:

```
E       AssertionError:
E        +  where 3221225477 = CompletedProcess(args=[...], returncode=3221225477, stdout='', stderr='').returncode
tests\runtime\test_editing_windows.py:30: AssertionError
1 failed in 1.21s
```

  With the fix: `1 passed in 1.32s`. (3221225477 = 0xC0000005, access violation.)
- `sazed aprendizado` with a redirected stdout crashes on "→" (cp1252); pre-existing CLI
  behaviour, reported, not changed here.

### Mutations

### token: a missing token is let through
mutation in src/sazed/interfaces/dashboard/server.py: '        if not hmac.compare_digest(' -> '        if token and not hmac.compare_digest('
```
E       assert 200 == 403
E       assert 200 == 403
FAILED tests/interfaces/dashboard/test_server_writes.py::test_the_token_is_required[None]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_the_token_is_required[]
2 failed, 3 passed, 33 deselected in 0.71s
```

### Origin: checked by prefix instead of exact origin
mutation in src/sazed/interfaces/dashboard/server.py: '            if origin not in self._origins():' -> '            if not origin.startswith(f"http://{HOST}"):'
```
E       assert 200 == 403
FAILED tests/interfaces/dashboard/test_server_writes.py::test_the_origin_must_be_the_dashboard[headers1]
1 failed, 6 passed, 31 deselected in 0.74s
```

### Origin: a request without Origin skips the Referer check
mutation in src/sazed/interfaces/dashboard/server.py: '            if not any(referer.startswith(f"{o}/") for o in self._origins()):' -> '            if False:'
```
E       assert 200 == 403
E       assert 200 == 403
E       assert 200 == 403
FAILED tests/interfaces/dashboard/test_server_writes.py::test_the_origin_must_be_the_dashboard[headers3]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_the_origin_must_be_the_dashboard[headers4]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_the_origin_must_be_the_dashboard[headers5]
3 failed, 4 passed, 31 deselected in 0.80s
```

### POST only: PUT served like POST
mutation in src/sazed/interfaces/dashboard/server.py: '    # output ----' -> '    do_PUT = do_POST\n\n    # output ----'
```
E       AssertionError: assert {'do_GET', 'd...ST', 'do_PUT'} == {'do_GET', 'do_POST'}
E         
E         Extra items in the left set:
E         'do_PUT'
E         Use -v to get more diff
FAILED tests/interfaces/dashboard/test_server.py::test_every_handler_method_other_than_get_and_post_refuses
1 failed, 8 passed, 30 deselected in 0.81s
```

### POST only: GET on a write path is no longer refused
mutation in src/sazed/interfaces/dashboard/server.py: '        if url.path in WRITE_ROUTES:\n            self._refuse_method(allow="POST")\n            return\n' -> ''
```
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
E       assert 404 == 405
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/alias/add]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/alias/edit]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/episode/label]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/example/add]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/example/edit]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/forget]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/note/add]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/note/edit]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/note/remove]
FAILED tests/interfaces/dashboard/test_server_writes.py::test_writes_are_post_only[/api/write/undo]
10 failed, 28 deselected in 0.79s
```

### power intent: the learnable check forgotten
mutation in src/sazed/runtime/admin.py: '    if not specs[intent_id].learnable:' -> '    if False:'
```
E       AssertionError: assert <LabelResult.LEARNED: 'learned'> is <LabelResult.NOT_LEARNABLE: 'not_learnable'>
E        +  where <LabelResult.LEARNED: 'learned'> = learn_example(SazedApp(assistant=<sazed.runtime.assistant.Assistant object at 0x00000254612FC7D0>, store=<sazed.adapters.sqlite.copp...s={})), rng=<random.Random objec
E        +  and   <LabelResult.NOT_LEARNABLE: 'not_learnable'> = LabelResult.NOT_LEARNABLE
E       AssertionError: assert <LabelResult.LEARNED: 'learned'> is <LabelResult.NOT_LEARNABLE: 'not_learnable'>
E        +  where <LabelResult.LEARNED: 'learned'> = edit_example(SazedApp(assistant=<sazed.runtime.assistant.Assistant object at 0x000002546136B4D0>, store=<sazed.adapters.sqlite.copp...s={})), rng=<random.Random object
E        +  and   <LabelResult.NOT_LEARNABLE: 'not_learnable'> = LabelResult.NOT_LEARNABLE
E       AssertionError: assert 'learned' == 'not_learnable'
E         
E         - not_learnable
E         + learned
E       assert (True is False)
FAILED tests/runtime/test_admin_editing.py::test_learn_example_refuses_a_power_intent
FAILED tests/runtime/test_admin_editing.py::test_a_refused_edit_leaves_index_and_store_untouched
FAILED tests/runtime/test_editing.py::test_label_and_edit_go_through_the_safeguards
FAILED tests/interfaces/dashboard/test_writes.py::test_power_intent_is_refused_with_an_explanation
4 failed, 48 passed in 0.64s
```

### conflict: saved without force
mutation in src/sazed/runtime/admin.py: '    if verdict is Verdict.CONFLICT and not force:' -> '    if False:'
```
E       AssertionError: assert <LabelResult.LEARNED: 'learned'> is <LabelResult.CONFLICT: 'conflict'>
E        +  where <LabelResult.LEARNED: 'learned'> = learn_example(SazedApp(assistant=<sazed.runtime.assistant.Assistant object at 0x0000022B2A273170>, store=<sazed.adapters.sqlite.copp...s={})), rng=<random.Random objec
E        +  and   <LabelResult.CONFLICT: 'conflict'> = LabelResult.CONFLICT
E       AssertionError: assert <LabelResult.LEARNED: 'learned'> is <LabelResult.CONFLICT: 'conflict'>
E        +  where <LabelResult.LEARNED: 'learned'> = edit_example(SazedApp(assistant=<sazed.runtime.assistant.Assistant object at 0x0000022B2A2CE630>, store=<sazed.adapters.sqlite.copp...s={})), rng=<random.Random object
E        +  and   <LabelResult.CONFLICT: 'conflict'> = LabelResult.CONFLICT
E       AssertionError: assert 'learned' == 'conflict'
E         
E         - conflict
E         + learned
E       AssertionError: assert (200, True, 'learned', False) == (200, False, 'conflict', True)
E         
E         At index 1 diff: True != False
E         Use -v to get more diff
FAILED tests/runtime/test_admin_editing.py::test_a_conflict_needs_force - Ass...
FAILED tests/runtime/test_admin_editing.py::test_a_refused_edit_leaves_index_and_store_untouched
FAILED tests/runtime/test_editing.py::test_label_and_edit_go_through_the_safeguards
FAILED tests/interfaces/dashboard/test_writes.py::test_conflict_offers_force
4 failed, 48 passed in 0.64s
```

### atomic edit: the delete is committed before the insert
mutation in src/sazed/adapters/sqlite/coppermind.py: '            self._conn.execute("DELETE FROM learned_examples WHERE id = ?", (item_id,))\n' -> '            self._conn.execute("DELETE FROM learned_examples WHERE id = ?", (item_id,))\n            self._conn.commit()\n'
```
E       AssertionError: assert [] == [(1, 'abre o zap')]
E         
E         Right contains one more item: (1, 'abre o zap')
E         Use -v to get more diff
FAILED tests/adapters/test_sqlite_notes_and_edits.py::test_a_replace_that_fails_midway_leaves_no_trace
1 failed, 15 passed in 0.39s
```

### notes: forgetting an item leaves its notes behind
mutation in src/sazed/adapters/sqlite/coppermind.py: '            self._conn.execute(\n                "DELETE FROM notes WHERE target_kind = ? AND target_id = ?",\n                (kind.value, item_id),\n            )\n' -> ''
```
E       AssertionError: assert [('example', ...do episódio')] == [('alias', 'd...do episódio')]
E         
E         At index 0 diff: ('example', 'do exemplo') != ('alias', 'do apelido')
E         Left contains one more item: ('episode', 'do episódio')
E         Use -v to get more diff
E               sqlite3.IntegrityError: UNIQUE constraint failed: notes.id
E       assert [(1,)] == [(0,)]
E         
E         At index 0 diff: (1,) != (0,)
E         Use -v to get more diff
FAILED tests/adapters/test_sqlite_notes_and_edits.py::test_forgetting_an_item_deletes_its_notes_only
FAILED tests/adapters/test_sqlite_notes_and_edits.py::test_snapshot_then_restore_brings_back_the_row_and_its_notes
FAILED tests/runtime/test_editing.py::test_forget_then_undo_restores_row_and_notes
3 failed, 25 passed in 0.55s
```

### reads: the editor status 'warms up' the model
mutation in src/sazed/interfaces/dashboard/writes.py: '        """Never loads anything: it only reports the editor\'s state."""\n' -> '        self._worker.submit(self._editor._full).result()  # warm up\n'
```
E       AssertionError: assert 1 == 0
E        +  where 1 = <support.editing.AppFactory object at 0x000001DBDF70AA50>.calls
E        +    where <support.editing.AppFactory object at 0x000001DBDF70AA50> = Served(port=58977, factory=<support.editing.AppFactory object at 0x000001DBDF70AA50>, data=WindowsPath('C:/Users/Usuario/AppData/Local/Temp/
E       AssertionError: assert {'state': 're...essage': None} == {'state': 'id...essage': None}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'state': 'ready'} != {'state': 'idle'}
E         Use -v to get more diff
FAILED tests/interfaces/dashboard/test_server_writes.py::test_reads_never_load_the_model
FAILED tests/interfaces/dashboard/test_writes.py::test_editor_status_never_loads
2 failed, 58 deselected in 0.62s
```

### edit: a refused edit forgets to put the old example back in the index
mutation in src/sazed/runtime/admin.py: '        if removed and not saved:' -> '        if False:'
```
E       assert 0.35032451152801514 == 1.0 ± 1.0e-06
E         
E         comparison failed
E         Obtained: 0.35032451152801514
E         Expected: 1.0 ± 1.0e-06
FAILED tests/runtime/test_admin_editing.py::test_a_refused_edit_leaves_index_and_store_untouched
1 failed, 17 passed in 0.37s
```

### pt-BR: a pydantic error type without a translation
mutation in src/sazed/interfaces/dashboard/writes.py: '    "string_type": "deve ser um texto",\n' -> ''
```
E           AssertionError: ('/api/write/alias/add', 'alias', 7, 'Dados inválidos: apelido: valor inválido; destino: é obrigatório.')
E           assert 'valor inválido' not in 'Dados invál...obrigatório.'
E             
E             'valor inválido' is contained here:
E               Dados inválidos: apelido: valor inválido; destino: é obrigatório.
E             ?                           ++++++++++++++
E           AssertionError: ('/api/write/alias/edit', 'target', 7, 'Dados inválidos: item: é obrigatório; destino: valor inválido.')
E           assert 'valor inválido' not in 'Dados invál...or inválido.'
E             
E             'valor inválido' is contained here:
E                destino: valor inválido.
E           AssertionError: ('/api/write/episode/label', 'intent', 7, 'Dados inválidos: comando: é obrigatório; pedido: valor inválido.')
E           assert 'valor inválido' not in 'Dados invál...or inválido.'
E             
E             'valor inválido' is contained here:
E               ; pedido: valor inválido.
E           AssertionError: ('/api/write/example/add', 'text', 7, 'Dados inválidos: texto: valor inválido; pedido: é obrigatório.')
E           assert 'valor inválido' not in 'Dados invál...obrigatório.'
E             
E             'valor inválido' is contained here:
E               Dados inválidos: texto: valor inválido; pedido: é obrigatório.
E             ?                         ++++++++++++++
E           AssertionError: ('/api/write/example/edit', 'text', 7, 'Dados inválidos: item: é obrigatório; texto: valor inválido; pedido: é obrigatório.')
E           assert 'valor inválido' not in 'Dados invál...obrigatório.'
E             
E             'valor inválido' is contained here:
E               o; texto: valor inválido; pedido: é obrigatório.
E             ?           ++++++++++++++
E           AssertionError: ('/api/write/forget', 'ref', 7, 'Dados inválidos: item: valor inválido.')
E           assert 'valor inválido' not in 'Dados invál...or inválido.'
E             
E             'valor inválido' is contained here:
E               Dados inválidos: item: valor inválido.
E             ?                        ++++++++++++++
E           AssertionError: ('/api/write/note/add', 'text', 7, 'Dados inválidos: destino: é obrigatório; item: é obrigatório; texto: valor inválido.')
E           assert 'valor inválido' not in 'Dados invál...or inválido.'
E             
E             'valor inválido' is contained here:
E               o; texto: valor inválido.
E           AssertionError: ('/api/write/note/edit', 'text', 7, 'Dados inválidos: item: é obrigatório; texto: valor inválido.')
E           assert 'valor inválido' not in 'Dados invál...or inválido.'
E             
E             'valor inválido' is contained here:
E               o; texto: valor inválido.
E           AssertionError: ('/api/write/undo', 'undo', 7, 'Dados inválidos: desfazer: valor inválido.')
E           assert 'valor inválido' not in 'Dados invál...or inválido.'
E             
E             'valor inválido' is contained here:
E               Dados inválidos: desfazer: valor inválido.
E             ?                            ++++++++++++++
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/alias/add]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/alias/edit]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/episode/label]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/example/add]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/example/edit]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/forget]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/note/add]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/note/edit]
FAILED tests/interfaces/dashboard/test_writes.py::test_every_invalid_field_is_explained_in_pt_br[/api/write/undo]
9 failed, 13 passed in 0.53s
```

### undo: notes not restored
mutation in src/sazed/adapters/sqlite/coppermind.py: '            for note in snap.notes:' -> '            for note in ():'
```
E       AssertionError: assert [] == ['nota']
E         
E         Right contains one more item: 'nota'
E         Use -v to get more diff
E       AssertionError: assert [] == [('nota',)]
E         
E         Right contains one more item: ('nota',)
E         Use -v to get more diff
FAILED tests/adapters/test_sqlite_notes_and_edits.py::test_snapshot_then_restore_brings_back_the_row_and_its_notes
FAILED tests/runtime/test_editing.py::test_forget_then_undo_restores_row_and_notes
2 failed, 26 passed in 0.53s
```
