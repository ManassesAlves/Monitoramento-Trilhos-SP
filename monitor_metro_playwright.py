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
# URL
# =====================================================

URL_METRO = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"

# =====================================================
# TELEGRAM
# =====================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =====================================================
# PADRÕES DE STATUS
# =====================================================

PADROES_ENCERRADA = [
    "operação encerrada",
    "circulação encerrada",
    "operação paralisada",
    "circulação paralisada",
]

PADROES_PROBLEMA = [
    "operação interrompida",
    "circulação interrompida",
    "velocidade reduzida",
    "operação parcial",
    "circulação parcial",
    "intervalos maiores",
    "falha",
]

PADROES_NORMAL = [
    "operação normal",
    "circulação normal",
]

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
        data={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        },
        timeout=10,
    )


def emoji_status(status):
    s = status.lower()
    if "encerrada" in s or "paralisada" in s:
        return "🚇⛔"
    if "normal" in s:
        return "🚇✅"
    return "🚇⚠️"


def obter_status_antigo(valor):
    if isinstance(valor, dict):
        return valor.get("status")
    if isinstance(valor, str):
        return valor
    return None


def classificar_status(texto):
    t = texto.lower()

    for p in PADROES_ENCERRADA:
        if p in t:
            return "Operação Paralisada", texto.strip()

    for p in PADROES_PROBLEMA:
        if p in t:
            return p.title(), texto.strip()

    for p in PADROES_NORMAL:
        if p in t:
            return "Operação normal", None

    return "Operação normal", None

# =====================================================
# PERSISTÊNCIA
# =====================================================

def garantir_csv_existe():
    if not os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["Data", "Hora", "Linha", "Status Novo", "Status Antigo", "Motivo"]
            )


def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def salvar_historico(linha, novo, antigo, motivo):
    garantir_csv_existe()
    t = agora_sp()
    with open(ARQUIVO_HISTORICO, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [
                t.strftime("%Y-%m-%d"),
                t.strftime("%H:%M:%S"),
                linha,
                novo,
                antigo,
                motivo or "",
            ]
        )

# =====================================================
# SCRAPING METRÔ SP (CORRIGIDO)
# =====================================================

def capturar_metro():
    dados = {}

    try:
        r = requests.get(URL_METRO, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"⚠️ Falha ao acessar site do Metrô: {e}")
        return dados

    soup = BeautifulSoup(r.text, "lxml")

    for item in soup.select("li.linha"):
        numero = item.select_one(".linha-numero")
        nome = item.select_one(".linha-nome")

        if not numero or not nome:
            continue

        linha_nome = f"Linha {numero.text.strip()} – {nome.text.strip()}"

        # 🔍 TEXTO COMPLETO DA LINHA (status + motivo)
        texto_completo = item.get_text(" ", strip=True)

        status, motivo = classificar_status(texto_completo)

        dados[linha_nome] = {
            "status": status,
            "motivo": motivo,
        }

    return dados

# =====================================================
# MAIN
# =====================================================

def main():
    garantir_csv_existe()

    estado_anterior = carregar_estado()
    estado_atual = capturar_metro()

    for linha, info in estado_atual.items():
        novo = info["status"]
        motivo = info.get("motivo")
        antigo = obter_status_antigo(estado_anterior.get(linha))

        if antigo is not None and antigo != novo:
            emoji = emoji_status(novo)

            msg = (
                f"{emoji} **{linha}**\n"
                f"🔄 De: {antigo}\n"
                f"➡️ Para: **{novo}**"
            )

            if motivo:
                msg += f"\n📝 Motivo: {motivo}"

            enviar_telegram(msg)
            salvar_historico(linha, novo, antigo, motivo)

    salvar_estado(estado_atual)

# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
