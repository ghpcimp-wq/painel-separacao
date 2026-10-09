#!/usr/bin/env python3
"""Converte os XLSX de dados/xlsx em JSON para o painel.

Lê TODOS os arquivos de dados/xlsx (o historico completo) e regenera:
  dados/json/AAAA-MM-DD.json  -> itens de cada dia
  dados/resumo.json           -> indicadores por dia (historico do painel)

As colunas sao lidas pela POSICAO (o exportador corta os titulos), na ordem:
  0 data/hora impressao | 1 data | 2 CODTIPOPER | 3 NUNOTA | 4 fatura parcial
  5 CODPROD | 6 REFERENCIA | 7 valor liquido | 8 PENDENTE | 9 TIPO
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


def ler_xlsx(caminho):
    """Devolve a lista de itens de um XLSX (linhas invalidas e o cabecalho sao ignorados)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planilha = openpyxl.load_workbook(caminho, data_only=True).active
        linhas = list(planilha.iter_rows(values_only=True))
    itens = []
    for lin in linhas:
        if lin is None or len(lin) < 10:
            continue
        quando, nota, cod = _data_hora(lin[0]), _inteiro(lin[3]), _inteiro(lin[5])
        if quando is None or nota is None:
            continue  # cabecalho ou linha vazia
        try:
            valor = round(float(lin[7] or 0), 2)
        except (TypeError, ValueError):
            valor = 0.0
        itens.append({
            "data": quando.strftime("%Y-%m-%d"),
            "h": quando.strftime("%H:%M:%S"),
            "top": _inteiro(lin[2]),
            "nota": nota,
            "parc": 1 if str(lin[4] or "").strip().upper() == "SIM" else 0,
            "cod": cod,
            "ref": str(lin[6] or "").strip(),
            "v": valor,
            "pend": 1 if str(lin[8] or "").strip().upper() == "S" else 0,
            "tipo": str(lin[9] or "").strip().upper(),
        })
    return itens


def main():
    DIR_JSON.mkdir(parents=True, exist_ok=True)
    por_dia = {}
    arquivos = sorted(DIR_XLSX.glob("*.xlsx"))
    for arq in arquivos:  # ordem alfabetica: o arquivo mais novo de um dia prevalece
        try:
            itens = ler_xlsx(arq)
        except Exception as erro:  # arquivo corrompido nao pode derrubar o painel
            print(f"AVISO: nao foi possivel ler {arq.name}: {erro}", file=sys.stderr)
            continue
        dias_arquivo = {}
        for it in itens:
            dias_arquivo.setdefault(it.pop("data"), []).append(it)
        for dia, lista in dias_arquivo.items():
            por_dia[dia] = {"arquivo": arq.name, "itens": lista}

    dias = sorted(por_dia)
    pend_por_dia = {d: {i["ref"] for i in por_dia[d]["itens"] if i["pend"]} for d in dias}
    resumo = []
    for dia in dias:
        itens = por_dia[dia]["itens"]
        limite = (dt.date.fromisoformat(dia) - dt.timedelta(days=JANELA_REINCIDENCIA - 1)).isoformat()
        janela = [d for d in dias if limite <= d <= dia]
        reinc = {}
        for ref in pend_por_dia[dia]:
            n = sum(1 for d in janela if ref in pend_por_dia[d])
            if n > 1:
                reinc[ref] = n
        saida = {"data": dia, "arquivo": por_dia[dia]["arquivo"], "itens": itens, "reinc": reinc}
        (DIR_JSON / f"{dia}.json").write_text(
            json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        pend = [i for i in itens if i["pend"]]
        notas = {i["nota"] for i in itens}
        resumo.append({
            "data": dia,
            "itens": len(itens),
            "pedidos": len(notas),
            "valor": round(sum(i["v"] for i in itens), 2),
            "itens_pend": len(pend),
            "pedidos_pend": len({i["nota"] for i in pend}),
            "valor_pend": round(sum(i["v"] for i in pend), 2),
        })

    for antigo in DIR_JSON.glob("*.json"):  # remove dias que nao existem mais nos XLSX
        if antigo.stem not in por_dia:
            antigo.unlink()
    RESUMO.write_text(json.dumps({"dias": resumo}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(arquivos)} arquivo(s) XLSX -> {len(dias)} dia(s) no painel.")


if __name__ == "__main__":
    main()
