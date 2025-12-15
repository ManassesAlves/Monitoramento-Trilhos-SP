from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import os
import sys
from datetime import datetime, timedelta, timezone
import csv
import requests

URL = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_metro.csv"


def get_horario_sp():
    fuso_sp = timezone(timedelta(hours=-3))
    return datetime.now(fuso_sp)


def enviar_telegram(mensagem):
    if not TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print("Erro Telegram:", e)


def carregar_estado_anterior():
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_estado_atual(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=4, ensure_ascii=False)


def salvar_historico(linha, status_novo, status_antigo):
    arquivo_existe = os.path.exists(ARQUIVO_HISTORICO)
    agora = get_horario_sp()
    with open(ARQUIVO_HISTORICO, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not arquivo_existe:
            writer.writerow(["Data", "Hora", "Linha", "Status_Novo", "Status_Anterior"])
        writer.writerow([
            agora.strftime("%Y-%m-%d"),
            agora.strftime("%H:%M:%S"),
            linha, status_novo, status_antigo
        ])


def capturar_status_html():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL, timeout=60000)

        # Aceitar cookies
        try:
            page.click("button:has-text('Aceitar')", timeout=5000)
        except:
            pass

        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")

    dados = {}

    # 🔎 Cada linha fica em um card/div — seletor robusto
    for card in soup.select(".linha"):
        nome = card.select_one(".nome")
        status = card.select_one(".status")

        if nome and status:
            dados[nome.get_text(strip=True)] = status.get_text(strip=True)

    return dados


def main():
    print("Iniciando monitoramento via Playwright + HTML")

    estado_anterior = carregar_estado_anterior()
    novo_estado = estado_anterior.copy()

    linhas = capturar_status_html()

    if not linhas:
        print("Não foi possível extrair dados do HTML.")
        sys.exit(1)

    for nome, status_atual in linhas.items():
        status_antigo = estado_anterior.get(nome)

        if status_antigo and status_antigo != status_atual:
            emoji = "✅" if "Normal" in status_atual else "⚠️"
            msg = (
                f"{emoji} **{nome}**\n"
                f"🔄 De: {status_antigo}\n"
                f"➡️ Para: **{status_atual}**"
            )
            enviar_telegram(msg)
            salvar_historico(nome, status_atual, status_antigo)

        novo_estado[nome] = status_atual

    salvar_estado_atual(novo_estado)
    print("Monitoramento concluído com sucesso.")


if __name__ == "__main__":
    main()
