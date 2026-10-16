import pytest

from fakes.index import ScriptedIndex
from sazed.core.policy import Thresholds
from sazed.runtime.evaluation import NO_INTENT, NluCase, evaluate

TH = Thresholds(t_exec=0.90, t_confirm=0.70, g_min=0.05)
APPS = ["Google Chrome", "Spotify"]
INDEX = ScriptedIndex(
    {
        "abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.6},  # right, executes
        "fecha o spotify": {"abrir_app": 0.95, "fechar_app": 0.6},  # wrong intent, executes
        "abre ai o spotify": {"abrir_app": 0.80, "fechar_app": 0.3},  # right, confirms
        "que horas sao": {"volume_mudo": 0.95},  # out of domain, executes
        "conta uma piada": {"volume_mudo": 0.20},  # out of domain, not understood
    }
)
CASES = [
    NluCase("abre o chrome", "abrir_app", app="Google Chrome"),
    NluCase("fecha o spotify", "fechar_app", app="Spotify"),
    NluCase("abre ai o spotify", "abrir_app", app="Spotify"),
    NluCase("que horas sao", NO_INTENT),
    NluCase("conta uma piada", NO_INTENT),
]


def test_report_arithmetic() -> None:
    report = evaluate(CASES, index=INDEX, app_names=APPS, thresholds=TH)
    assert report.accuracy == pytest.approx(2 / 3)
    assert report.false_execute_rate == pytest.approx(2 / 5)
    assert report.confirm_rate == pytest.approx(1 / 5)
    assert [r.case.text for r in report.false_executes()] == ["fecha o spotify", "que horas sao"]
    assert [r.case.text for r in report.misranked()] == ["fecha o spotify"]


def test_executing_the_right_intent_with_the_wrong_app_is_a_false_execute() -> None:
    case = NluCase("abre o chrome", "abrir_app", app="Spotify")
    report = evaluate([case], index=INDEX, app_names=APPS, thresholds=TH)
    assert report.false_execute_rate == 1.0


def test_executing_with_an_unknown_app_is_not_a_false_execute() -> None:
    # The skill only answers "não encontrei": no OS action happens, so it is not the costly error.
    index = ScriptedIndex({"abre o photoshop": {"abrir_app": 0.95, "fechar_app": 0.6}})
    case = NluCase("abre o photoshop", "abrir_app", app="Photoshop")
    report = evaluate([case], index=index, app_names=APPS, thresholds=TH)
    assert report.false_execute_rate == 0.0


def test_out_of_domain_with_an_unknown_app_is_not_a_false_execute() -> None:
    index = ScriptedIndex({"abre a porta": {"abrir_app": 0.95, "fechar_app": 0.6}})
    report = evaluate(
        [NluCase("abre a porta", NO_INTENT)], index=index, app_names=APPS, thresholds=TH
    )
    assert report.false_execute_rate == 0.0


def test_served_rates_count_only_in_domain_cases() -> None:
    report = evaluate(CASES, index=INDEX, app_names=APPS, thresholds=TH)
    # in-domain: chrome executed correctly, spotify executed wrongly, "abre ai" confirmed
    assert report.executed_rate == pytest.approx(1 / 3)
    assert report.asked_rate == pytest.approx(1 / 3)
    assert report.not_understood_rate == pytest.approx(0.0)


def test_executing_with_the_wrong_level_is_a_false_execute() -> None:
    index = ScriptedIndex({"abaixa pra 20": {"volume_diminuir": 0.95}})
    right = NluCase("abaixa pra 20", "volume_diminuir", alvo=20)
    wrong = NluCase("abaixa pra 20", "volume_diminuir", alvo=30)
    assert evaluate([right], index=index, app_names=APPS, thresholds=TH).false_execute_rate == 0
    assert evaluate([wrong], index=index, app_names=APPS, thresholds=TH).false_execute_rate == 1


def test_executing_with_the_wrong_query_is_a_false_execute() -> None:
    index = ScriptedIndex({"pesquisa gatos": {"pesquisar": 0.95}})
    right = NluCase("pesquisa gatos", "pesquisar", consulta="gatos")
    wrong = NluCase("pesquisa gatos", "pesquisar", consulta="cachorros")
    assert evaluate([right], index=index, app_names=APPS, thresholds=TH).false_execute_rate == 0
    assert evaluate([wrong], index=index, app_names=APPS, thresholds=TH).false_execute_rate == 1


def test_executing_with_the_wrong_folder_file_or_side_is_a_false_execute() -> None:
    index = ScriptedIndex(
        {
            "abre a pasta downloads": {"abrir_pasta": 0.95},
            "abre o arquivo gastos": {"abrir_arquivo": 0.95},
            "joga a janela pra esquerda": {"janela_encaixar": 0.95},
        }
    )
    cases = {
        True: [
            NluCase("abre a pasta downloads", "abrir_pasta", pasta="Documentos"),
            NluCase("abre o arquivo gastos", "abrir_arquivo", arquivo="contas"),
            NluCase("joga a janela pra esquerda", "janela_encaixar", lado="direita"),
        ],
        False: [
            NluCase("abre a pasta downloads", "abrir_pasta", pasta="Downloads"),
            NluCase("abre o arquivo gastos", "abrir_arquivo", arquivo="gastos"),
            NluCase("joga a janela pra esquerda", "janela_encaixar", lado="esquerda"),
        ],
    }
    for wrong, group in cases.items():
        for case in group:
            report = evaluate([case], index=index, app_names=APPS, thresholds=TH)
            assert report.false_execute_rate == (1.0 if wrong else 0.0), case


def test_a_file_change_proposal_counts_as_asked_never_as_a_false_execute() -> None:
    # The plan is the confirmation: nothing happens on disk before "sim".
    index = ScriptedIndex({"apaga o relatório": {"arquivo_apagar": 0.97}})
    wrong = NluCase("apaga o relatório", "abrir_arquivo")
    report = evaluate([wrong], index=index, app_names=APPS, thresholds=TH)
    assert report.false_execute_rate == 0.0
    assert report.executed_rate == 0.0 and report.asked_rate == 1.0
