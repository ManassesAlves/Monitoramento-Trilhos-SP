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


def identificar_operador(linha):
    if linha.startswith("Linha"):
        return "metro"
    if linha.startswith("ViaMobilidade"):
        return "viamobilidade"
    return "desconhecido"


def emoji_status(status, operador):
    status = status.lower()

    if operador == "metro":
        return "🚇✅" if "normal" in status else "🚇⚠️"

    if operador == "viamobilidade":
        return "🚆✅" if "normal" in status else "🚆⚠️"

    return "❓"


def extrair_descricao(status_texto):
    if "normal" in status_texto.lower():
        return None
    return status_texto.strip()


def obter_status_antigo(valor):
    if isinstance(valor, dict):
        return valor.get("status")
    if isinstance(valor, str):
        return valor
    return None

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
                "Descricao",
            ])


def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def salvar_historico(linha, novo, antigo, descricao):
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
            descricao or "",
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
            status_txt = status.text.strip()

            dados[linha] = {
                "status": status_txt,
                "descricao": extrair_descricao(status_txt),
            }

    return dados


def capturar_viamobilidade():
    dados = {
        "ViaMobilidade – Linha 8 Diamante": {
            "status": "Status indefinido",
            "descricao": "Status não identificado no site",
        },
        "ViaMobilidade – Linha 9 Esmeralda": {
            "status": "Status indefinido",
            "descricao": "Status não identificado no site",
        },
    }

    r = requests.get(URL_VIAMOBILIDADE, timeout=30)
    texto = r.text.lower()

    if "operação normal" in texto:
        for linha in dados:
            dados[linha] = {"status": "Operação normal", "descricao": None}

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

    for linha, info in estado_atual.items():
        novo_status = info["status"]
        descricao = info.get("descricao")

        antigo_status = obter_status_antigo(estado_anterior.get(linha))

        if antigo_status is not None and antigo_status != novo_status:
            operador = identificar_operador(linha)
            emoji = emoji_status(novo_status, operador)

            mensagem = (
                f"{emoji} **{linha}**\n"
                f"🔄 De: {antigo_status}\n"
                f"➡️ Para: **{novo_status}**"
            )

            if descricao:
                mensagem += f"\n📝 Motivo: {descricao}"

            enviar_telegram(mensagem)
            salvar_historico(linha, novo_status, antigo_status, descricao)

    salvar_estado(estado_atual)

# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
