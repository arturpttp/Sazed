# Sub-project 2b — discrimination proofs

Each section: the mutation a person could plausibly write, and the failing output.

## Task 1: "vai pro X" offers to open only on focus
Mutation: drop the `WindowNotFound.offer_open` branch from `template_key`.
```
E       AssertionError: assert 'Spotify não ...Mestre Artur.' == 'Spotify não .... Devo abrir?'
E         - Spotify não está aberto, Mestre Artur. Devo abrir?
```

## Task 2: moving between monitors uses the source monitor's offset
Mutation: `round(v * dst.width / src.width)` (forgets `- src.left`).
```
FAILED tests/skills/test_window_geometry.py::test_moving_back_returns_to_the_same_place
```

## Task 3: folder and file names are masked before learning
Mutation: `_NAMED_SLOTS = {}` in `runtime/assistant.py`.
```
FAILED tests/runtime/test_assistant_learning.py::test_a_learned_folder_phrase_keeps_the_wording_not_the_folder
FAILED tests/runtime/test_assistant_learning.py::test_a_learned_file_phrase_keeps_the_wording_not_the_file
```
Mutation: always insert the placeholder (no collapse after the same literal word).
```
FAILED tests/nlu/test_slot_mask.py::test_a_placeholder_after_the_same_literal_word_collapses
```

## Task 4: Sazed's console is never a window target
Mutation: exclude only windows whose own pid is Sazed's (drop the hosted-child check — Windows
Terminal draws the console inside its own process's window).
```
FAILED tests/adapters/test_window_choice.py::test_a_frame_hosting_sazeds_console_is_excluded
```

## Task 5: a maximised window stays maximised after moving to another monitor
Mutation: drop the final `maximize` after `place`.
```
FAILED tests/skills/test_windows_skill.py::test_moving_a_maximised_window_keeps_it_maximised
```

## Task 6: the search SQL cannot be broken out of; program files are recognised in any case
Mutation: `escape_sql_like` forgets to double quotes.
```
FAILED tests/skills/test_files_pure.py::test_like_escaping[d'água-d''água]
FAILED tests/skills/test_files_pure.py::test_an_injection_attempt_stays_inside_the_string[x' OR 1=1 --]
FAILED tests/skills/test_files_pure.py::test_an_injection_attempt_stays_inside_the_string[a'; DROP TABLE x; --]
```
Mutation: `is_program` compares without `.lower()` → 23 failures (every upper-case extension).

## Task 7: a program found by search is revealed, never opened (skill guard)
Mutation: skip the `is_program` check in `FilesSkill._open_hit`.
```
FAILED tests/skills/test_files_skill.py::test_a_program_chosen_from_a_list_is_revealed_not_run
FAILED tests/skills/test_files_skill.py::test_a_single_program_hit_is_revealed_too
```

## Task 8: the opener itself refuses programs (the load-bearing guard)
Mutation: drop the `is_program` check in `WindowsFileOpener.open` → 23 failures (one per
`PROGRAM_EXTENSIONS` entry), e.g.
`FAILED tests/adapters/test_files_adapter.py::test_the_opener_refuses_a_program_even_if_the_skill_did_not[.bat]`.

## Task 8: the index's display path is not a real path (found on this machine)
With the plan's `System.ItemPathDisplay`, the real-index test failed:
```
E  AssertionError: assert WindowsPath('C:/Usuários/Usuario/Documentos/sazed2b430dd08dfd.txt')
   == WindowsPath('C:/Users/Usuario/Documents/sazed2b430dd08dfd.txt')
```
Fixed by reading `System.ItemUrl`; the test now also asserts the path exists, with a file name
holding a space and an accent. Dates arrive as UTC (`TimeZoneInfo('GMT Standard Time', True)`)
and are converted to local time (checked against the clock: created 00:35 local, read 00:35).

## Task 9: snapping lands the *visible* window on the half (invisible borders compensated)
Real desktop, a throwaway Tk window. Mutation: `SetWindowPos` with the target rect itself
(no `outer_rect`). With the first tolerance (8 px) the test could not see it — a finding: the
borders are 7 px. Tolerance cut to 2 px, then:
```
E  AssertionError: (Rect(left=7, top=0, right=673, bottom=761), Rect(left=0, top=0, right=680, bottom=768))
```

## Task 10: window words never become an app name (found while wiring the evaluation)
Before `WINDOW_WORDS`, "minimiza essa janela" / "joga a janela pra esquerda" extracted the app
query "essa janela" / "janela esquerda" → `Unmatched` → Sazed would answer "não encontrei". The
seven `test_window_words_name_no_app` cases failed (`assert Unmatched(...) is None`); all pass
with the window verbs and words in `COMMAND_WORDS`. Real-catalog check: "com" collides with
"Ação com um clique" (left out, guarded by a test); "monitor" with "Resource Monitor" (kept;
`test_resource_monitor_is_still_found_by_its_other_word`).

## Task 10: the focus offer is never learned as "open"
Mutation: `learn_example=True` on the "abrir?" offer after `janela_focar`.
```
FAILED tests/runtime/test_assistant_dialogue.py::test_going_to_a_closed_app_offers_to_open_it_and_learns_nothing
```
Mutation: drop the `pasta` check from `_is_false_execute` →
`test_executing_with_the_wrong_folder_file_or_side_is_a_false_execute` fails on the Documentos case.

## Task 10: fixture with the real model (qint8), thresholds unchanged (0.94 / 0.88 / 0.01)
| | cases | accuracy | false-execute | executed | asked |
|---|---|---|---|---|---|
| main before 2b | 150 | 0.928 | 0.000 | 0.496 | 0.504 |
| 2b, first seeds | 150 | 0.896 | 0.007 ("desliga o discord" → `janela_restaurar`, seed "desminimiza o discord") | 0.496 | 0.496 |
| 2b + 48 new cases, first seeds | 198 | 0.887 | 0.020 | 0.518 | 0.458 |
| 2b final | 198 | 0.923 | 0.000 | 0.542 | 0.458 |

Seed changes, each measured: window seeds name Word/Excel/Notion/"janela" instead of the apps the
open/close seeds use (Spotify/Discord pulled "bota o spotify pra rodar" to restore, "desliga o
discord" to restore); file seeds say "arquivo" or a type word; folder seeds say "pasta"; added
`abrir_app` "pode iniciar o chrome", "abre o gerenciador de tarefas"; `fechar_app` "fecha a
janela do discord"; minimise "esconde a janela"; restore "sai da tela cheia no chrome", "volta a
janela ao tamanho normal"; focus "vai pro discord", "me leva pro spotify"; files "abre o arquivo
documentos", "abre a foto da viagem".
Remaining 2b misrankings all *ask* (none executes): "abre o bloco de notas" (0.914 file vs
open), "me leva pro discord", "abre o arquivo downloads" (0.954 vs 0.947: gap under g_min),
"fecha a janela do spotify".

## Task 10: window seeds must not use the learning placeholder "programa"
Found by `test_a_learned_wording_carries_over_to_other_apps` (real model) failing: with window
seeds "me mostra o programa", "manda o programa pra outra tela"…, the learned form "bota o
programa pra rodar" scored ≥ t_conflict against them, so the confirmation asked "posso guardar?"
and stored nothing. Guard `test_only_opening_and_closing_apps_use_the_learning_placeholder`;
mutation (re-add "minimiza o programa") → `AssertionError: assert {'abrir_app', 'fechar_app',
'janela_minimizar'} <= {'abrir_app', 'fechar_app'}`.

## Task 10: a folder named inside a longer phrase
"abre o último print que eu tirei" read the folder as "print que eu tirei" (Unmatched → "a pasta
não existe"); fixed by matching a known name or synonym as a run of words inside the phrase.
`test_a_folder_named_inside_a_longer_phrase` failed first (2 of 3 cases).

## Task 11: `learning.t_conflict` 0.92 → 0.95 (measured; it was an unmeasured placeholder)
By hand, every confirmed window command asked "'minimiza o programa' se parece com outro
pedido… Guardo mesmo assim?" and learned nothing. Nearest seeds (real model): "minimiza o
programa" → `area_trabalho_mostrar` "minimiza tudo" 0.939; "restaura o programa" →
`area_trabalho_voltar` "restaura tudo" 0.923; "vai pro programa" → `abrir_app` "abre o programa"
0.922 — related commands, not the same one. A real conflict sits at ~1.0 ("fecha o programa"
taught as `abrir_app`). With 0.92, `test_a_confirmed_window_command_is_learned_without_a_conflict_question`
fails for both cases (`assert [] == [('minimiza aí o programa', 'janela_minimizar')]`); with
0.95 they pass and `test_a_real_conflict_is_still_asked_before_learning` still passes.
