"""Terminal interface. Talks only to sazed.runtime; every string here is pt-BR."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, TextIO

from sazed.runtime.admin import (
    LabelResult,
    failure_rows,
    forget_learned,
    intent_rows,
    label_episode,
    learned_rows,
)
from sazed.runtime.wiring import SazedApp, StartupError, start

EXIT_WORDS = {"sair", "tchau", "até logo", "ate logo"}


EXAMPLES = """exemplos:
  sazed                                  conversa com Sazed (sair: "sair" ou Ctrl-C)
  sazed aprendizado                      lista o que aprendeu (e3 = exemplo, a5 = apelido)
  sazed aprendizado --esquecer e3        esquece um item aprendido
  sazed revisar                          lista falhas recentes, com o número de cada pedido
  sazed revisar --rotular 12 abrir_app   ensina o que o pedido 12 queria dizer
      (acrescente --forcar para guardar mesmo se parecer outro pedido)
  sazed painel                           abre o painel local em http://127.0.0.1:8765"""


class _Formatter(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):  # type: ignore[no-untyped-def]
        # argparse passes prefix="" when it builds a subcommand's name: keep that one empty.
        return super().add_usage(usage, actions, groups, "uso: " if prefix is None else prefix)


class _Parser(argparse.ArgumentParser):
    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(add_help=False, formatter_class=_Formatter, **kwargs)
        self._positionals.title = "comandos"
        self._optionals.title = "opções"
        self.add_argument("-h", "--ajuda", action="help", help="mostra esta ajuda e sai")

    def error(self, message: str) -> NoReturn:
        self.exit(2, "Comando não reconhecido. Use 'sazed --ajuda' para ver as opções.\n")


def _parser() -> _Parser:
    parser = _Parser(prog="sazed", description="Sazed, seu assistente local.", epilog=EXAMPLES)
    parser.add_argument("--config", type=Path, default=None, help="caminho do config.toml")
    commands = parser.add_subparsers(dest="command", parser_class=_Parser, metavar="comando")
    learned = commands.add_parser("aprendizado", help="lista o que Sazed aprendeu")
    learned.add_argument("--esquecer", metavar="REF", help="remove um item (ex.: e3, a5)")
    review = commands.add_parser("revisar", help="lista falhas recentes para rotular")
    review.add_argument("--rotular", nargs=2, metavar=("EPISODIO", "PEDIDO"))
    review.add_argument("--limite", type=int, default=20, help="quantas falhas listar")
    review.add_argument(
        "--forcar", action="store_true", help="guarda mesmo se parecer outro pedido"
    )
    panel = commands.add_parser("painel", help="abre o painel local no navegador")
    panel.add_argument("--porta", type=_port, default=8765, help="porta local (padrão: 8765)")
    panel.add_argument("--raiz", type=Path, default=None, help="pasta do repositório de Sazed")
    return parser


def _port(text: str) -> int:
    port = int(text)
    if not 0 <= port <= 65535:
        raise ValueError(text)
    return port


def _learned(app: SazedApp, args: argparse.Namespace) -> int:
    if args.esquecer:
        row = forget_learned(app, args.esquecer)
        if row is None:
            print(f"Não encontrei '{args.esquecer}' em minha mente de cobre.")
            return 1
        print(f"Esquecido: {row.kind} '{row.text}' → {row.meaning}.")
        return 0
    rows = learned_rows(app)
    if not rows:
        print("Ainda não aprendi nada, Mestre.")
    for row in rows:
        when = f"{row.created_at:%d/%m/%Y %H:%M}"
        print(f"{row.ref:>5}  {row.kind:<8} '{row.text}' → {row.meaning}  ({when})")
    return 0


def _review(app: SazedApp, args: argparse.Namespace) -> int:
    if args.rotular:
        episode, intent = args.rotular
        result = (
            label_episode(app, int(episode), intent, force=args.forcar)
            if episode.isdigit()
            else LabelResult.UNKNOWN
        )
        if result is LabelResult.LEARNED:
            print("Guardado em minha mente de cobre.")
            return 0
        if result is LabelResult.ALREADY_KNOWN:
            print("Isso eu já sabia, Mestre.")
            return 0
        if result is LabelResult.CONFLICT:
            print(
                "Essa frase se parece com outro pedido que conheço. "
                "Use --forcar para guardar mesmo assim."
            )
            return 1
        if result is LabelResult.NOT_LEARNABLE:
            print("Esse pedido nunca é aprendido: sempre pedirei confirmação antes.")
            return 1
        print("Não consegui rotular. Pedidos válidos:")
        for intent_id, description in intent_rows(app):
            print(f"  {intent_id:<16} {description}")
        return 1
    rows = failure_rows(app, args.limite)
    if not rows:
        print("Nenhuma falha recente, Mestre.")
    for row in rows:
        print(f"{row.id:>5}  {row.at:%d/%m %H:%M}  '{row.utterance}'  [{row.what}]")
    return 0


def _repl(app: SazedApp, stdin: TextIO) -> int:
    print(app.greeting())
    try:
        while True:
            sys.stdout.write("> ")
            sys.stdout.flush()
            line = stdin.readline()
            if not line:
                break
            text = line.strip()
            if not text:
                continue
            if text.lower() in EXIT_WORDS:
                break
            print(app.assistant.handle(text).text)
    except KeyboardInterrupt:
        print()
    print(app.farewell())
    return 0


def main(
    argv: list[str] | None = None,
    *,
    build: Callable[[Path | None], SazedApp] | None = None,
    stdin: TextIO | None = None,
    dashboard: Callable[..., int] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.command == "painel":  # reads only: no model, no writable coppermind
        if dashboard is None:
            from sazed.interfaces.dashboard.launch import run as dashboard
        return dashboard(args.config, port=args.porta, root=args.raiz)
    try:
        app = (build or start)(args.config)
    except StartupError as err:
        print(str(err))
        return 2
    try:
        if args.command == "aprendizado":
            return _learned(app, args)
        if args.command == "revisar":
            return _review(app, args)
        return _repl(app, stdin or sys.stdin)
    finally:
        app.close()
