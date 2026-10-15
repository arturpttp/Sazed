"""JSON endpoints: validate the query, read the sources, shape the answer. No HTTP here.

`handle(path, query)` returns (status, payload). A source that cannot be read answers 200
with `available: false` and a pt-BR message for its panel; anything unexpected is logged
and answered with a generic pt-BR 500, never with its internal text.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from sazed.interfaces.dashboard.redact import config_rows
from sazed.interfaces.dashboard.sources import DevSources, ResourceSampler
from sazed.interfaces.dashboard.stats import (
    Turn,
    daily_activity,
    daily_learned,
    is_failure,
    totals,
)
from sazed.runtime.admin import DECISION_LABELS, REACTION_LABELS
from sazed.runtime.insight import (
    FAILURE_OUTCOMES,
    ConfigView,
    CoppermindReader,
    CoppermindUnavailable,
    Thresholds,
    capabilities,
    explain,
    learned_for,
    path_rows,
    ports,
    skills_for_listing,
)

log = logging.getLogger(__name__)

GENERIC_ERROR = "Peço desculpas, Mestre Artur: algo falhou ao montar este painel. Veja o log."
REACTIONS = {reaction.value: label for reaction, label in REACTION_LABELS.items()}


class CatalogEntry(Protocol):
    """What the dashboard reads of an app catalog entry (`skills.pc.apps.AppEntry`)."""

    @property
    def name(self) -> str: ...
    @property
    def target(self) -> str: ...
    @property
    def shortcut(self) -> str: ...


class BadRequest(Exception):
    """`str(error)` is a pt-BR message meant for the user."""


@dataclass(frozen=True)
class IntParam:
    default: int
    low: int
    high: int


@dataclass(frozen=True)
class TextParam:
    max_length: int = 200


Param = IntParam | TextParam


def parse_query(spec: Mapping[str, Param], query: Mapping[str, str]) -> dict[str, Any]:
    """Every endpoint's query goes through its spec; unknown keys are ignored."""
    values: dict[str, Any] = {}
    for name, param in spec.items():
        raw = query.get(name)
        if isinstance(param, TextParam):
            text = (raw or "").strip()
            if len(text) > param.max_length:
                raise BadRequest(
                    f"Parâmetro inválido: '{name}' deve ter no máximo {param.max_length} letras."
                )
            values[name] = text or None
            continue
        if raw is None or raw == "":
            values[name] = param.default
            continue
        try:
            number = int(raw)
        except ValueError:
            raise BadRequest(f"Parâmetro inválido: '{name}' deve ser um número inteiro.") from None
        if not param.low <= number <= param.high:
            raise BadRequest(
                f"Parâmetro inválido: '{name}' deve ficar entre {param.low} e {param.high}."
            )
        values[name] = number
    return values


def unavailable(message: str) -> dict[str, Any]:
    return {"available": False, "message": message}


class DashboardApi:
    ROUTES: dict[str, tuple[str, dict[str, Param]]] = {
        "/api/overview": ("overview", {}),
        "/api/episodes": (
            "episodes",
            {
                "limit": IntParam(50, 1, 200),
                "offset": IntParam(0, 0, 10_000_000),
                "q": TextParam(),
                "decision": TextParam(40),
                "intent": TextParam(80),
            },
        ),
        "/api/learning": ("learning", {"days": IntParam(30, 1, 365)}),
        "/api/dev": ("dev", {}),
        "/api/resources": ("resources", {}),
        "/api/examples": ("examples", {"q": TextParam(), "limit": IntParam(200, 1, 1000)}),
        "/api/aliases": ("aliases", {"q": TextParam()}),
        "/api/capabilities": ("capabilities", {}),
        "/api/catalog": ("catalog", {"q": TextParam()}),
    }

    def __init__(
        self,
        *,
        view: ConfigView,
        config_path: Path,
        reader: CoppermindReader,
        dev: DevSources,
        sampler: ResourceSampler,
        catalog: Callable[[], Sequence[CatalogEntry]],
        clock: Callable[[], datetime],
        wall: Callable[[], float],
    ) -> None:
        self._view = view
        self._config_path = config_path
        self._reader = reader
        self._dev = dev
        self._sampler = sampler
        self._catalog = catalog
        self._clock = clock
        self._wall = wall
        self._skills = skills_for_listing()
        nlu = view.config.nlu
        self._thresholds = Thresholds(nlu.t_exec, nlu.t_confirm, nlu.g_min)

    def handle(self, path: str, query: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
        route = self.ROUTES.get(path)
        if route is None:
            return 404, {"error": "Este endereço não existe no painel."}
        name, spec = route
        try:
            params = parse_query(spec, query)
        except BadRequest as err:
            return 400, {"error": str(err)}
        try:
            payload: dict[str, Any] = getattr(self, name)(**params)
        except CoppermindUnavailable as err:
            log.warning("coppermind unavailable for %s", path, exc_info=err.__cause__ is not None)
            return 200, unavailable(str(err))
        except Exception:
            log.exception("dashboard endpoint %s failed", path)
            return 500, {"error": GENERIC_ERROR}
        return 200, payload

    # coppermind -------------------------------------------------------------------

    def _episode(
        self,
        e: Any,
        examples: Sequence[tuple[str, str]],
        aliases: Sequence[tuple[str, str]],
    ) -> dict[str, Any]:
        return {
            "id": e.id,
            "at": e.at,
            "utterance": e.utterance,
            "ranking": [{"intent": i, "score": s} for i, s in e.ranking],
            "slots": e.slots,
            "decision": e.decision,
            "decision_label": DECISION_LABELS.get(e.decision, e.decision),
            "intent": e.intent_id,
            "outcome": e.outcome,
            "failed": is_failure(Turn(e.at, e.decision, e.outcome, e.reaction), FAILURE_OUTCOMES),
            "reaction": e.reaction,
            "reaction_label": REACTIONS.get(e.reaction, e.reaction),
            "reason": explain(
                e.ranking, e.decision, e.slots, e.intent_id, self._skills, self._thresholds
            ),
            "learned": learned_for(e.utterance, examples, aliases),
        }

    def episodes(
        self, limit: int, offset: int, q: str | None, decision: str | None, intent: str | None
    ) -> dict[str, Any]:
        rows = self._reader.episodes(limit, offset, search=q, decision=decision, intent=intent)
        total = self._reader.count_episodes(search=q, decision=decision, intent=intent)
        examples = [(x.text, x.intent_id) for x in self._reader.examples(limit=100_000)]
        aliases = [(a.alias, a.value) for a in self._reader.aliases()]
        return {
            "available": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "thresholds": asdict(self._thresholds),
            "decisions": DECISION_LABELS,
            "items": [self._episode(e, examples, aliases) for e in rows],
        }

    def examples(self, q: str | None, limit: int) -> dict[str, Any]:
        items = [asdict(x) for x in self._reader.examples(q, limit=limit)]
        return {"available": True, "items": items}

    def aliases(self, q: str | None) -> dict[str, Any]:
        return {"available": True, "items": [asdict(a) for a in self._reader.aliases(q)]}

    def _turns(self) -> list[Turn]:
        return [
            Turn(s.at, s.decision, s.outcome, s.reaction) for s in self._reader.episode_summaries()
        ]

    def learning(self, days: int) -> dict[str, Any]:
        today = self._clock().date()
        turns = self._turns()
        return {
            "available": True,
            "days": days,
            "activity": [
                asdict(d) for d in daily_activity(turns, FAILURE_OUTCOMES, today=today, days=days)
            ],
            "learned": [
                asdict(d)
                for d in daily_learned(self._reader.learned_dates(), today=today, days=days)
            ],
            "totals": asdict(totals(turns, FAILURE_OUTCOMES, today=today)),
        }

    # other panels --------------------------------------------------------------

    def dev(self) -> dict[str, Any]:
        return {"available": True, **self._dev.snapshot()}

    def resources(self) -> dict[str, Any]:
        return {"available": True, **self._sampler.sample(self._wall())}

    def _coppermind_summary(self) -> dict[str, Any]:
        try:
            turns = self._turns()
            dates = self._reader.learned_dates()
            recent = self._reader.episodes(8)
            version = self._reader.schema_version()
        except CoppermindUnavailable as err:
            return {**unavailable(str(err)), "recent": []}
        today = self._clock().date()
        return {
            "available": True,
            "schema_version": version,
            "totals": asdict(totals(turns, FAILURE_OUTCOMES, today=today)),
            "learned": {
                "examples": sum(kind == "example" for kind, _ in dates),
                "aliases": sum(kind == "alias" for kind, _ in dates),
            },
            "recent": [self._episode(e, [], []) for e in recent],
        }

    def overview(self) -> dict[str, Any]:
        coppermind = self._coppermind_summary()
        recent = coppermind.pop("recent")
        dev = self._dev.snapshot()
        commits = dev["commits"]["items"]
        return {
            "available": True,
            "now": self._clock().isoformat(timespec="seconds"),
            "user": self._view.config.user.name,
            "coppermind": coppermind,
            "resources": self._sampler.sample(self._wall()),
            "dev": {
                "plan": dev["plan"],
                "done": dev["done"],
                "total": dev["total"],
                "current_task": dev["current_task"],
                "last_commit": commits[0] if commits else None,
                "branch": dev["commits"].get("branch"),
                "message": dev["message"],
            },
            "recent": recent,
        }

    def capabilities(self) -> dict[str, Any]:
        config = self._view.config
        return {
            "available": True,
            "skills": [asdict(s) for s in capabilities(self._skills)],
            "ports": [asdict(p) for p in ports(self._skills)],
            "config": {
                "path": str(self._config_path),
                "exists": self._config_path.exists(),
                "rows": [asdict(r) for r in config_rows(self._view.effective, self._view.raw)],
            },
            "paths": [asdict(p) for p in path_rows(config, self._config_path)],
            "thresholds": asdict(self._thresholds),
        }

    def catalog(self, q: str | None) -> dict[str, Any]:
        try:
            entries = list(self._catalog())
        except Exception:
            log.exception("app catalog unavailable")
            return unavailable("Não consegui ler o catálogo de programas do Menu Iniciar.")
        needle = (q or "").casefold()
        items = [
            {"name": e.name, "target": e.target, "shortcut": e.shortcut}
            for e in entries
            if needle in e.name.casefold()
        ]
        return {"available": True, "total": len(entries), "items": items}
