from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import os
import csv
import requests
from datetime import datetime, timedelta, timezone

URL_METRO = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"
URL_CPTM = "https://www.cptm.sp.gov.br/Pages/Situacao-Linhas.aspx"

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_metro.csv"


# ===============================
# UTIL
# ===============================

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


# ===============================
# PERSISTÊNCIA
# ===============================

def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def garantir_csv_existe():
    if not os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Data", "Hora", "Linha", "Status Novo", "Status Antigo"])


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


# ===============================
# NORMALIZAÇÃO / EMOJIS
# ===============================

def normalizar_nome(numero, nome):
    return f"Linha {numero} – {nome.strip().title()}"


def tipo_linha(nome):
    try:
        return "CPTM" if int(nome.split()[1]) >= 7 else "METRO"
    except:
        return "METRO"


def emoji_linha(linha, status):
    ok = "Normal" in status
    if tipo_linha(linha) == "CPTM":
        return "🚆✅" if ok else "🚆⚠️"
    return "🚇✅" if ok else "🚇⚠️"


# ===============================
# SCRAPER METRÔ
# ===============================

def capturar_metro(page):
    page.goto(URL_METRO, timeout=60000)

    try:
        page.click("button:has-text('Aceitar')", timeout=5000)
    except:
        pass

    page.wait_for_selector("li.linha", timeout=10000)
    soup = BeautifulSoup(page.content(), "lxml")

    dados = {}
    for item in soup.select("li.linha"):
        numero = item.select_one(".linha-numero")
        nome = item.select_one(".linha-nome")
        status = item.select_one(".linha-situacao")

        if numero and nome and status:
            dados[normalizar_nome(
                numero.get_text(strip=True),
                nome.get_text(strip=True)
            )] = status.get_text(strip=True)

    print(f"🚇 Metrô capturado: {len(dados)} linhas")
    return dados


# ===============================
# SCRAPER CPTM (CORRIGIDO)
# ===============================

def capturar_cptm(page):
    page.goto(URL_CPTM, timeout=60000)

    # ⏳ aguarda JS renderizar
    try:
        page.wait_for_selector(".linha", timeout=15000)
    except:
        print("⚠️ CPTM não carregou elementos")
        return {}

    soup = BeautifulSoup(page.content(), "lxml")
    dados = {}

    for item in soup.select(".linha"):
        numero = item.select_one(".numero")
        nome = item.select_one(".nome")
        status = item.select_one(".status")

        if numero and nome and status:
            dados[normalizar_nome(
                numero.get_text(strip=True),
                nome.get_text(strip=True)
            )] = status.get_text(strip=True)

    print(f"🚆 CPTM capturada: {len(dados)} linhas")
    return dados


# ===============================
# MAIN
# ===============================

def main():
    print("🚇🚆 Monitoramento iniciado")

    garantir_csv_existe()
    estado_anterior = carregar_estado()
    estado_atual = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        dados_metro = capturar_metro(page)
        dados_cptm = capturar_cptm(page)

        browser.close()

    dados = {**dados_metro, **dados_cptm}

    if not dados:
        print("❌ Nenhum dado capturado")
        return

    for linha, status in dados.items():
        antigo = estado_anterior.get(linha)

        if antigo is not None and antigo != status:
            enviar_telegram(
                f"{emoji_linha(linha, status)} **{linha}**\n"
                f"🔄 De: {antigo}\n"
                f"➡️ Para: **{status}**"
            )
            salvar_historico(linha, status, antigo)

        estado_atual[linha] = status

    salvar_estado(estado_atual)
    print("✅ JSON atualizado com sucesso")


if __name__ == "__main__":
    main()
