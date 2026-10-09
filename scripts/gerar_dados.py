#!/usr/bin/env python3
"""Converte os XLSX de dados/xlsx em JSON para o painel.

Lê TODOS os arquivos de dados/xlsx (o historico completo) e regenera:
  dados/json/AAAA-MM-DD.json  -> itens de cada dia
  dados/resumo.json           -> indicadores por dia (historico do painel)

As colunas sao lidas pela POSICAO, na ordem do relatorio do ERP:
  0 data/hora impressao | 1 data | 2 CODTIPOPER | 3 NUNOTA | 4 fatura parcial
  5 CODPROD | 6 REFERENCIA | 7 QTDNEG | 8 QTDESTOQUE | 9 valor de venda do item
  10 PENDENTE | 11 STATUS

Arquivos no layout antigo (10 colunas, sem estoque/status) sao ignorados com aviso.
"""
import datetime as dt
import json
import pathlib
import sys
import warnings

import openpyxl

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DIR_XLSX = RAIZ / "dados" / "xlsx"
DIR_JSON = RAIZ / "dados" / "json"
RESUMO = RAIZ / "dados" / "resumo.json"
JANELA_REINCIDENCIA = 30  # dias
N_COLUNAS = 12
SEM_ESTOQUE = {"FABRICADO", "SC"}
COM_ESTOQUE = {"FORA DO PRAZO", "AGUARDANDO OUTROS ITENS"}


def _data_hora(valor):
    """Aceita texto 'DD/MM/AAAA HH:MM:SS' ou celula de data. Devolve datetime ou None."""
    if isinstance(valor, dt.datetime):
        return valor
    if isinstance(valor, str):
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return dt.datetime.strptime(valor.strip(), fmt)
            except ValueError:
                pass
    return None


def _inteiro(valor):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def _numero(valor, casas):
    try:
        n = round(float(valor or 0), casas)
    except (TypeError, ValueError):
        n = 0.0
    return int(n) if n == int(n) else n


def grupo(item):
    """a = atendido | e = pendente com estoque | f = pendente sem estoque (falta)."""
    if not item["pend"]:
        return "a"
    if item["st"] in SEM_ESTOQUE:
        return "f"
    if item["st"] in COM_ESTOQUE:
        return "e"
    return "e" if item["e"] >= item["q"] else "f"


def ler_xlsx(caminho):
    """Devolve (itens, linhas_layout_antigo). Cabecalho e linhas invalidas sao ignorados."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        linhas = list(openpyxl.load_workbook(caminho, data_only=True).active.iter_rows(values_only=True))
    itens, antigas = [], 0
    for lin in linhas:
        if lin is None or len(lin) < 4:
            continue
        quando, nota = _data_hora(lin[0]), _inteiro(lin[3])
        if quando is None or nota is None:
            continue  # cabecalho ou linha vazia
        if len(lin) < N_COLUNAS:
            antigas += 1
            continue
        pend = 1 if str(lin[10] or "").strip().upper() == "S" else 0
        status = " ".join(str(lin[11] or "").upper().split())
        if not pend:
            status = "ATENDIDO"
        elif not status or status == "ATENDIDO":
            status = "SEM CLASSIFICAÇÃO"
        itens.append({
            "data": quando.strftime("%Y-%m-%d"),
            "h": quando.strftime("%H:%M:%S"),
            "top": _inteiro(lin[2]),
            "nota": nota,
            "parc": 1 if str(lin[4] or "").strip().upper() == "SIM" else 0,
            "cod": _inteiro(lin[5]),
            "ref": str(lin[6] or "").strip(),
            "q": _numero(lin[7], 3),
            "e": _numero(lin[8], 3),
            "v": _numero(lin[9], 2),
            "pend": pend,
            "st": status,
        })
    return itens, antigas


def main():
    DIR_JSON.mkdir(parents=True, exist_ok=True)
    por_dia = {}
    arquivos = sorted(DIR_XLSX.glob("*.xlsx"))
    for arq in arquivos:  # ordem alfabetica: o arquivo mais novo de um dia prevalece
        try:
            itens, antigas = ler_xlsx(arq)
        except Exception as erro:  # arquivo corrompido nao pode derrubar o painel
            print(f"AVISO: nao foi possivel ler {arq.name}: {erro}", file=sys.stderr)
            continue
        if antigas:
            print(f"AVISO: {arq.name} esta no layout antigo ({antigas} linhas ignoradas).", file=sys.stderr)
        dias_arquivo = {}
        for it in itens:
            dias_arquivo.setdefault(it.pop("data"), []).append(it)
        for dia, lista in dias_arquivo.items():
            por_dia[dia] = {"arquivo": arq.name, "itens": lista}

    dias = sorted(por_dia)
    falta_por_dia = {d: {i["ref"] for i in por_dia[d]["itens"] if grupo(i) == "f"} for d in dias}
    resumo = []
    for dia in dias:
        itens = por_dia[dia]["itens"]
        limite = (dt.date.fromisoformat(dia) - dt.timedelta(days=JANELA_REINCIDENCIA - 1)).isoformat()
        janela = [d for d in dias if limite <= d <= dia]
        reinc = {}
        for ref in falta_por_dia[dia]:
            n = sum(1 for d in janela if ref in falta_por_dia[d])
            if n > 1:
                reinc[ref] = n
        saida = {"data": dia, "arquivo": por_dia[dia]["arquivo"], "itens": itens, "reinc": reinc}
        (DIR_JSON / f"{dia}.json").write_text(
            json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        pend = [i for i in itens if i["pend"]]
        resumo.append({
            "data": dia,
            "itens": len(itens),
            "pedidos": len({i["nota"] for i in itens}),
            "valor": round(sum(i["v"] for i in itens), 2),
            "itens_pend": len(pend),
            "pedidos_pend": len({i["nota"] for i in pend}),
            "valor_pend": round(sum(i["v"] for i in pend), 2),
            "valor_estoque": round(sum(i["v"] for i in pend if grupo(i) == "e"), 2),
            "valor_falta": round(sum(i["v"] for i in pend if grupo(i) == "f"), 2),
        })

    for antigo in DIR_JSON.glob("*.json"):  # remove dias que nao existem mais nos XLSX
        if antigo.stem not in por_dia:
            antigo.unlink()
    RESUMO.write_text(json.dumps({"dias": resumo}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(arquivos)} arquivo(s) XLSX -> {len(dias)} dia(s) no painel.")


if __name__ == "__main__":
    main()
