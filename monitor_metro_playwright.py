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
        data={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        },
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
            writer.writerow([
                "Data",
                "Hora",
                "Linha",
                "Status Novo",
                "Status Antigo",
            ])


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
# NORMALIZAÇÃO DE NOME
# ===============================

def normalizar_nome(numero, nome):
    """
    Exemplos de saída:
    - Linha 1 – Azul
    - Linha 7 – Rubi
    - Linha 10 – Turquesa
    """
    numero = numero.strip()
    nome = nome.strip().title()
    return f"Linha {numero} – {nome}"


# ===============================
# SCRAPING
# ===============================

def capturar_status():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, timeout=60000)

        # aceitar cookies
        try:
            page.click("button:has-text('Aceitar')", timeout=5000)
        except:
            pass

        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    dados = {}

    """
    Estrutura confirmada:
    <li class="linha">
        <div class="linha-numero">1</div>
        <div class="linha-nome">Azul</div>
        <div class="linha-situacao">Operação Normal</div>
    </li>
    """

    for item in soup.select("li.linha"):
        numero = item.select_one(".linha-numero")
        nome = item.select_one(".linha-nome")
        status = item.select_one(".linha-situacao")

        if not numero or not nome or not status:
            continue

        nome_normalizado = normalizar_nome(
            numero.get_text(strip=True),
            nome.get_text(strip=True)
        )

        dados[nome_normalizado] = status.get_text(strip=True)

    return dados


# ===============================
# MAIN
# ===============================

def main():
    print("🚇 Monitoramento Metrô + CPTM iniciado")

    garantir_csv_existe()

    estado_anterior = carregar_estado()
    estado_atual = {}

    dados = capturar_status()

    if not dados:
        print("⚠️ Nenhum dado capturado.")
        return

    for linha, status in dados.items():
        antigo = estado_anterior.get(linha)

        # 🔔 alerta somente se houver mudança real
        if antigo is not None and antigo != status:
            emoji = "✅" if "Normal" in status else "⚠️"
            mensagem = (
                f"{emoji} **{linha}**\n"
                f"🔄 De: {antigo}\n"
                f"➡️ Para: **{status}**"
            )
            enviar_telegram(mensagem)
            salvar_historico(linha, status, antigo)

        estado_atual[linha] = status

    salvar_estado(estado_atual)

    print("✅ Execução finalizada com sucesso")


if __name__ == "__main__":
    main()
