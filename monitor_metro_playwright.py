from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import os
import csv
import requests
from datetime import datetime, timedelta, timezone

URL = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_metro.csv"


def agora_sp():
    return datetime.now(timezone(timedelta(hours=-3)))


def enviar_telegram(msg):
    if not TOKEN or not CHAT_ID:
        print("Telegram não configurado.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }, timeout=10)


def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def salvar_historico(linha, novo, antigo):
    existe = os.path.exists(ARQUIVO_HISTORICO)
    t = agora_sp()

    with open(ARQUIVO_HISTORICO, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["Data", "Hora", "Linha", "Status Novo", "Status Antigo"])
        writer.writerow([
            t.strftime("%Y-%m-%d"),
            t.strftime("%H:%M:%S"),
            linha,
            novo,
            antigo or "INICIAL"
        ])


def capturar_status():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, timeout=60000)

        try:
            page.click("button:has-text('Aceitar')", timeout=5000)
        except:
            pass

        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    dados = {}

    for item in soup.select("li.linha"):
        nome = item.select_one(".linha-nome")
        status = item.select_one(".linha-situacao")

        if nome and status:
            dados[nome.get_text(strip=True)] = status.get_text(strip=True)

    return dados


def main():
    print("🚇 Monitoramento Direto do Metrô iniciado")

    estado_anterior = carregar_estado()
    primeira_execucao = estado_anterior is None
    estado_atual = {}

    dados = capturar_status()

    if not dados:
        print("Nenhum dado capturado.")
        return

    if primeira_execucao:
        msg = "📡 **Monitoramento do Metrô iniciado**\n\n"
        for linha, status in dados.items():
            msg += f"🚇 Linha {linha}: **{status}**\n"
        enviar_telegram(msg)

    for linha, status in dados.items():
        antigo = estado_anterior.get(linha) if estado_anterior else None

        if antigo and antigo != status:
            emoji = "✅" if "Normal" in status else "⚠️"
            msg = (
                f"{emoji} **Linha {linha}**\n"
                f"🔄 De: {antigo}\n"
                f"➡️ Para: **{status}**"
            )
            enviar_telegram(msg)
            salvar_historico(linha, status, antigo)

        estado_atual[linha] = status

    salvar_estado(estado_atual)

    print("✅ Monitoramento concluído com sucesso")


if __name__ == "__main__":
    main()
