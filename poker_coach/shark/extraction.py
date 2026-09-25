"""
sharkscope_extracao.py

Extrai dados do SharkScope chamando os mesmos endpoints que o site usa.
Cada chamada real consome busca do seu saldo, por isso o script:
  - guarda TUDO em cache (nunca repete uma consulta já feita);
  - tem um limite de chamadas por execução (MAX_CHAMADAS);
  - tem modo --dry-run (só mostra as URLs, não chama nada).

Instalação:
    pip install requests pandas

Comandos (use nesta ordem na primeira vez):
    python sharkscope_extracao.py --dry-run auto --n 3   # só mostra as URLs
    python sharkscope_extracao.py jogador                # 1 chamada: dados do jogador
    python sharkscope_extracao.py torneios --n 10        # 1 chamada: últimos 10 torneios
    python sharkscope_extracao.py detalhe 123456789      # 1 chamada: um torneio
    python sharkscope_extracao.py auto --n 5             # lista + detalhes (respeita o limite)
    python sharkscope_extracao.py estrutura arquivo.json # offline: inspeciona um JSON salvo

Opcional: se estiver logado no navegador, copie o header Cookie de uma requisição
no DevTools e defina a variável de ambiente SHARKSCOPE_COOKIE com ele.
"""
import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE = "https://pt.sharkscope.com/poker-statistics"
NETWORK = "PartyPoker"
PLAYER = "PowderyMaple763"
CURRENCY = "BRL"

MAX_CHAMADAS = 3   # teto de chamadas reais por execução
PAUSA = 3          # segundos entre chamadas

CACHE = Path("./cache_sharkscope")
RAW = CACHE / "raw"
DEBUG = CACHE / "debug"
for d in (RAW, DEBUG):
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"),
    "Accept": "application/json",   # sem isso a API do SharkScope pode responder XML
    "Referer": "https://pt.sharkscope.com/",
}


# ---------------------------------------------------------------------------
# Utilitários de JSON
# ---------------------------------------------------------------------------
def limpar(obj):
    """Remove '@' dos atributos e troca '$' (texto de nó XML) por 'texto'."""
    if isinstance(obj, dict):
        return {("texto" if k == "$" else k.lstrip("@")): limpar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpar(v) for v in obj]
    return obj


def achar_valor(obj, trecho):
    """Primeiro valor simples cujo nome de campo contém `trecho`."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if trecho.lower() in k.lower() and not isinstance(v, (dict, list)):
                return v
        for v in obj.values():
            achado = achar_valor(v, trecho)
            if achado is not None:
                return achado
    elif isinstance(obj, list):
        for v in obj:
            achado = achar_valor(v, trecho)
            if achado is not None:
                return achado
    return None


def listas_de_objetos(obj, caminho=""):
    """Gera (caminho, lista_de_dicts). Trata elemento único vindo de XML como lista."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            novo = f"{caminho}/{k}"
            if isinstance(v, dict) and any(t in k.lower() for t in ("tournament", "entry")):
                yield novo, [v]   # XML->JSON: um único item vira dict, não lista
            yield from listas_de_objetos(v, novo)
    elif isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            yield caminho, obj
        for v in obj:
            yield from listas_de_objetos(v, caminho)


def numerico(df):
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


def tabela(data, campo_obrigatorio, caminho_contem=None):
    """Maior lista de objetos que tenha `campo_obrigatorio` (e caminho opcional)."""
    candidatas = []
    for caminho, lista in listas_de_objetos(data):
        if caminho_contem and caminho_contem.lower() not in caminho.lower():
            continue
        if any(campo_obrigatorio.lower() == k.lower() or campo_obrigatorio.lower() in k.lower()
               for k in lista[0]):
            candidatas.append((caminho, lista))
    if not candidatas:
        return None, None
    caminho, lista = max(candidatas, key=lambda c: len(c[1]))
    return caminho, numerico(pd.json_normalize(lista))


def resumo_estrutura(obj, nivel=0, max_nivel=5, nome="raiz"):
    """Imprime a árvore de chaves do JSON, para entender o formato real."""
    pre = "  " * nivel
    if isinstance(obj, dict):
        simples = [k for k, v in obj.items() if not isinstance(v, (dict, list))]
        print(f"{pre}{nome} {{campos: {', '.join(simples[:12])}{'...' if len(simples) > 12 else ''}}}")
        if nivel < max_nivel:
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    resumo_estrutura(v, nivel + 1, max_nivel, k)
    elif isinstance(obj, list):
        print(f"{pre}{nome} [lista com {len(obj)} itens]")
        if obj and nivel < max_nivel:
            resumo_estrutura(obj[0], nivel + 1, max_nivel, f"{nome}[0]")


# ---------------------------------------------------------------------------
# Cliente HTTP com cache e orçamento
# ---------------------------------------------------------------------------
class SemOrcamento(Exception):
    pass


class Cliente:
    def __init__(self, max_chamadas, dry_run=False):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        cookie = os.environ.get("SHARKSCOPE_COOKIE")
        if cookie:
            self.s.headers["Cookie"] = cookie
        self.orcamento = max_chamadas
        self.dry_run = dry_run

    def get(self, caminho, params, nome_cache):
        arq = RAW / f"{nome_cache}.json"
        if arq.exists():
            print(f"[cache] {nome_cache}")
            return limpar(json.loads(arq.read_text(encoding="utf-8")))

        url = f"{BASE}/{caminho}"
        if self.dry_run:
            print(f"[dry-run] GET {url}  params={params}")
            return None
        if self.orcamento <= 0:
            raise SemOrcamento("Limite de chamadas desta execução atingido.")
        self.orcamento -= 1

        print(f"[GET] {url}  params={params}")
        r = self.s.get(url, params=params, timeout=30)
        time.sleep(PAUSA)

        try:
            bruto = r.json()
        except ValueError:
            dbg = DEBUG / f"{nome_cache}_status{r.status_code}.txt"
            dbg.write_text(r.text, encoding="utf-8")
            raise RuntimeError(f"Resposta não é JSON (HTTP {r.status_code}). Conteúdo salvo em {dbg}")

        data = limpar(bruto)
        resp = data.get("Response", data)

        restantes = achar_valor(resp, "RemainingSearches")
        if restantes is not None:
            print(f"    buscas restantes: {restantes}")

        if str(resp.get("success", "true")).lower() == "false" or r.status_code >= 400:
            dbg = DEBUG / f"{nome_cache}_erro.json"
            dbg.write_text(json.dumps(bruto, ensure_ascii=False, indent=2), encoding="utf-8")
            erro = achar_valor(resp, "texto") or achar_valor(resp, "error") or "sem mensagem"
            raise RuntimeError(f"API retornou erro: {erro}  (JSON salvo em {dbg})")

        # Só vai para o cache o que deu certo
        arq.write_text(json.dumps(bruto, ensure_ascii=False, indent=2), encoding="utf-8")
        return data


# ---------------------------------------------------------------------------
# Recursos
# ---------------------------------------------------------------------------
def buscar_jogador(cli):
    data = cli.get(f"networks/{NETWORK}/players/{PLAYER}",
                   {"Currency": CURRENCY}, f"jogador_{PLAYER}_{date.today()}")
    if data:
        resumo_estrutura(data)
    return data


def buscar_torneios(cli, n):
    # PALPITE baseado na documentação: recurso completedTournaments do jogador
    data = cli.get(f"networks/{NETWORK}/players/{PLAYER}/completedTournaments",
                   {"order": f"Last,1~{n}", "Currency": CURRENCY},
                   f"torneios_{PLAYER}_{n}_{date.today()}")
    if not data:
        return None
    caminho, df = tabela(data, "id", caminho_contem="tournament")
    if df is None:
        print("Não achei a lista de torneios. Estrutura recebida:")
        resumo_estrutura(data)
        return None
    print(f"Lista encontrada em {caminho}: {len(df)} torneios")
    df.to_csv(CACHE / "torneios.csv", index=False)
    return df


def buscar_detalhe(cli, tid):
    # PALPITE baseado na documentação: torneio por ID na rede
    data = cli.get(f"networks/{NETWORK}/tournaments/{tid}",
                   {"Currency": CURRENCY}, f"detalhe_{tid}")
    if not data:
        return None, None
    caminho, jogadores = tabela(data, "position")
    if jogadores is None:
        print("Não achei a lista de jogadores. Estrutura recebida:")
        resumo_estrutura(data)
        return None, None

    col_pos = next(c for c in jogadores.columns if "position" in c.lower())
    col_pre = next((c for c in jogadores.columns if "prize" in c.lower()), None)
    col_bty = [c for c in jogadores.columns if "bounty" in c.lower()]

    premios = None
    if col_pre:
        itm = jogadores[jogadores[col_pre].fillna(0) > 0]
        premios = (itm[[col_pos, col_pre, *col_bty]]
                   .rename(columns={col_pos: "posicao", col_pre: "premio"})
                   .sort_values("posicao").reset_index(drop=True))
        premios.to_csv(CACHE / f"premios_{tid}.csv", index=False)
    jogadores.to_csv(CACHE / f"jogadores_{tid}.csv", index=False)

    print(f"Torneio {tid}: {len(jogadores)} jogadores, "
          f"{0 if premios is None else len(premios)} premiados")
    if col_bty:
        print("    Atenção: há colunas de bounty; o 'premio' pode incluir bounties ganhos.")
    return jogadores, premios


def col_id(df):
    return next(c for c in df.columns if c.lower() == "id" or c.lower().endswith(".id"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=MAX_CHAMADAS, help="teto de chamadas reais")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("jogador")
    t = sub.add_parser("torneios"); t.add_argument("--n", type=int, default=10)
    d = sub.add_parser("detalhe"); d.add_argument("tid")
    a = sub.add_parser("auto"); a.add_argument("--n", type=int, default=5)
    e = sub.add_parser("estrutura"); e.add_argument("arquivo")
    args = ap.parse_args()

    if args.cmd == "estrutura":
        data = limpar(json.loads(Path(args.arquivo).read_text(encoding="utf-8")))
        resumo_estrutura(data)
        for campo in ("id", "position"):
            caminho, df = tabela(data, campo)
            if df is not None:
                print(f"\nTabela com '{campo}' em {caminho}:\n{df.head(10).to_string()}")
        return

    cli = Cliente(args.max, dry_run=args.dry_run)
    try:
        if args.cmd == "jogador":
            buscar_jogador(cli)
        elif args.cmd == "torneios":
            df = buscar_torneios(cli, args.n)
            if df is not None:
                print(df.head(20).to_string())
        elif args.cmd == "detalhe":
            _, premios = buscar_detalhe(cli, args.tid)
            if premios is not None:
                print(premios.to_string())
        elif args.cmd == "auto":
            df = buscar_torneios(cli, args.n)
            if args.dry_run:
                buscar_detalhe(cli, "<ID_DO_TORNEIO>")
            elif df is not None:
                for tid in df[col_id(df)].astype(str):
                    buscar_detalhe(cli, tid)
    except SemOrcamento as ex:
        print(f"\n{ex} O restante fica para a próxima execução (o cache evita repetir).")
    except RuntimeError as ex:
        print(f"\nERRO: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    main()