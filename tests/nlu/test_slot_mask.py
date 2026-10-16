from sazed.nlu.slots.mask import mask_words


def test_the_whole_name_becomes_one_placeholder_with_its_inner_fillers() -> None:
    # The file is "gastos do mes": its inner "do" belongs to the name.
    assert mask_words("acha a planilha de gastos do mes", {"gastos", "mes"}, "arquivo") == (
        "acha a planilha de arquivo"
    )


def test_consecutive_words_collapse() -> None:
    assert mask_words("abre a proposta final agora", {"proposta", "final"}, "arquivo") == (
        "abre a arquivo agora"
    )


def test_a_placeholder_after_the_same_literal_word_collapses() -> None:
    assert mask_words("abre a pasta projetos agora", {"projetos"}, "pasta") == (
        "abre a pasta agora"
    )


def test_accents_do_not_matter_and_command_words_survive() -> None:
    assert mask_words("abre o relatório", {"relatorio", "abre"}, "arquivo") == "abre o arquivo"
