from pathlib import Path

from fakes.ports import fake_pc_ports
from sazed.core.types import SlotValue
from sazed.runtime.config import BUILTIN_ENGINES, Config
from sazed.runtime.skills import build_skills
from sazed.skills.pc.files import KNOWN_FOLDERS
from sazed.skills.pc.settings import PAGE_NAMES


def test_every_skill_is_built_once() -> None:
    ids = [s.id for s in build_skills(fake_pc_ports([]), Config()).skills]
    assert sorted(ids) == sorted(
        [
            "apps",
            "volume",
            "media",
            "power",
            "screen",
            "settings",
            "brightness",
            "web",
            "status",
            "windows",
            "files",
            "fileops",
        ]
    )


def test_sites_join_the_app_names_and_installed_apps_win() -> None:
    skill_set = build_skills(fake_pc_ports(["WhatsApp", "Spotify"]), Config())
    assert {"WhatsApp", "Spotify", "YouTube", "WhatsApp Web"} <= set(skill_set.app_names)
    assert skill_set.app_names.count("WhatsApp") == 1


def test_store_aliases_are_added_only_for_apps_that_exist() -> None:
    aliases = build_skills(fake_pc_ports(["Calculator"]), Config()).app_aliases
    assert aliases == {"calculadora": "Calculator"}


def test_configured_aliases_override_the_defaults() -> None:
    config = Config(aliases={"calculadora": "Spotify"})
    aliases = build_skills(fake_pc_ports(["Calculator", "Spotify"]), config).app_aliases
    assert aliases["calculadora"] == "Spotify"


def test_engines_and_pages_feed_the_extractors() -> None:
    skill_set = build_skills(fake_pc_ports([]), Config())
    assert skill_set.engine_names == list(BUILTIN_ENGINES)
    assert skill_set.page_names == PAGE_NAMES
    declared = {slot.name for s in skill_set.skills for spec in s.intents for slot in spec.slots}
    assert declared <= set(skill_set.extractors())


def test_known_and_configured_folders_feed_the_folder_extractor(tmp_path: Path) -> None:
    skill_set = build_skills(fake_pc_ports([]), Config(folders={"Projetos": tmp_path}))
    assert skill_set.folder_names == [*KNOWN_FOLDERS, "Projetos"]
    extract = skill_set.extractors()["pasta"]
    assert extract("abre a pasta projetos", {}) == SlotValue("pasta", "Projetos", "projetos", 1.0)
    assert extract("abre os baixados", {}) == SlotValue("pasta", "Downloads", "baixados", 1.0)


def test_the_file_area_protects_sazed_and_appdata_and_fixes_the_known_folders() -> None:
    from sazed.runtime.skills import file_area

    area = file_area(
        profile=r"C:\Users\a",
        configured=[r"D:\Projetos"],
        known=[r"C:\Users\a\Downloads", r"D:\Docs"],
        data_dir=r"C:\Users\a\AppData\Local\Sazed",
        project=r"C:\Programacao\JARVIS\Sazed",
    )
    assert area.roots == (r"C:\Users\a", r"D:\Projetos")
    assert area.fixed == (r"C:\Users\a", r"D:\Projetos", r"C:\Users\a\Downloads", r"D:\Docs")
    assert area.trees == (
        r"C:\Users\a\AppData",
        r"C:\Users\a\AppData\Local\Sazed",
        r"C:\Programacao\JARVIS\Sazed",
    )
