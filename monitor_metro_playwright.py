import requests
from bs4 import BeautifulSoup
import json
import os
import csv
from datetime import datetime, timedelta, timezone

# =====================================================
# PATH BASE
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_transporte.json")
ARQUIVO_HISTORICO = os.path.join(BASE_DIR, "historico_transporte.csv")

# =====================================================
# URLS
# =====================================================

URL_METRO = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"
URL_VIAMOBILIDADE = "https://trilhos.motiva.com.br/viamobilidade8e9/situacao-das-linhas/"

# =====================================================
# TELEGRAM
# =====================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =====================================================
# UTIL
# =====================================================

def agora_sp():
    return datetime.now(timezone(timedelta(hours=-3)))


def enviar_telegram(msg):
    if not TOKEN or not CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10,
    )


def emoji_status(status, operador):
    status = status.lower()

    if operador == "metro":
        return "🚇✅" if "normal" in status else "🚇⚠️"

    if operador == "viamobilidade":
        return "🚆✅" if "normal" in status else "🚆⚠️"

    return "❓"


def identificar_operador(linha):
    if linha.startswith("Linha"):
        return "metro"
    if linha.startswith("ViaMobilidade"):
        return "viamobilidade"
    return "desconhecido"

# =====================================================
# PERSISTÊNCIA
# =====================================================

def garantir_csv_existe():
    if not os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Data",
                "Hora",
                "Linha",
                "Status Novo",
                "Status Antigo",
            ])


def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def salvar_historico(linha, novo, antigo):
    garantir_csv_existe()
    t = agora_sp()
    with open(ARQUIVO_HISTORICO, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            t.strftime("%Y-%m-%d"),
            t.strftime("%H:%M:%S"),
            linha,
            novo,
            antigo,
        ])

# =====================================================
# SCRAPING
# =====================================================

def capturar_metro():
    dados = {}
    r = requests.get(URL_METRO, timeout=30)
    soup = BeautifulSoup(r.text, "lxml")

    for item in soup.select("li.linha"):
        numero = item.select_one(".linha-numero")
        nome = item.select_one(".linha-nome")
        status = item.select_one(".linha-situacao")

        if numero and nome and status:
            linha = f"Linha {numero.text.strip()} – {nome.text.strip()}"
            dados[linha] = status.text.strip()

    return dados


def capturar_viamobilidade():
    dados = {
        "ViaMobilidade – Linha 8 Diamante": "Status indefinido",
        "ViaMobilidade – Linha 9 Esmeralda": "Status indefinido",
    }

    r = requests.get(URL_VIAMOBILIDADE, timeout=30)
    texto = r.text.lower()

    if "operação normal" in texto:
        dados["ViaMobilidade – Linha 8 Diamante"] = "Operação normal"
        dados["ViaMobilidade – Linha 9 Esmeralda"] = "Operação normal"

    return dados

# =====================================================
# MAIN
# =====================================================

def main():
    garantir_csv_existe()
    estado_anterior = carregar_estado()

    estado_atual = {}
    estado_atual.update(capturar_metro())
    estado_atual.update(capturar_viamobilidade())

    for linha, status in estado_atual.items():
        antigo = estado_anterior.get(linha)

        if antigo is not None and antigo != status:
            operador = identificar_operador(linha)
            emoji = emoji_status(status, operador)

            enviar_telegram(
                f"{emoji} **{linha}**\n"
                f"🔄 De: {antigo}\n"
                f"➡️ Para: **{status}**"
            )

            salvar_historico(linha, status, antigo)

        estado_atual[linha] = status

    salvar_estado(estado_atual)

# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
