from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import os
import csv
import requests
from datetime import datetime, timedelta, timezone

# =====================================================
# URLS
# =====================================================

URL_METRO = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"
URL_CPTM_API = "https://www.cptm.sp.gov.br/_layouts/15/Cptm.WebServices/SituacaoService.asmx/ObterSituacao"

# =====================================================
# CONFIG
# =====================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_metro.csv"

# =====================================================
# UTIL
# =====================================================

def agora_sp():
    return datetime.now(timezone(timedelta(hours=-3)))


def enviar_telegram(msg):
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
    except Exception as e:
        print("Erro ao enviar Telegram:", e)


# =====================================================
# PERSISTÊNCIA
# =====================================================

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

# =====================================================
# NORMALIZAÇÃO / EMOJIS
# =====================================================

def normalizar_nome(numero, nome):
    return f"Linha {numero.strip()} – {nome.strip().title()}"


def tipo_linha(nome):
    try:
        return "CPTM" if int(nome.split()[1]) >= 7 else "METRO"
    except Exception:
        return "METRO"


def emoji_linha(linha, status):
    ok = "Normal" in status
    if tipo_linha(linha) == "CPTM":
        return "🚆✅" if ok else "🚆⚠️"
    return "🚇✅" if ok else "🚇⚠️"

# =====================================================
# SCRAPER METRÔ (HTML)
# =====================================================

def capturar_metro():
    dados = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL_METRO, timeout=60000)

        try:
            page.click("button:has-text('Aceitar')", timeout=5000)
        except:
            pass

        page.wait_for_selector("li.linha", timeout=15000)
        soup = BeautifulSoup(page.content(), "lxml")
        browser.close()

    for item in soup.select("li.linha"):
        numero = item.select_one(".linha-numero")
        nome = item.select_one(".linha-nome")
        status = item.select_one(".linha-situacao")

        if numero and nome and status:
            linha = normalizar_nome(
                numero.get_text(strip=True),
                nome.get_text(strip=True),
            )
            dados[linha] = status.get_text(strip=True)

    print(f"🚇 Metrô capturado: {len(dados)} linhas")
    return dados

# =====================================================
# SCRAPER CPTM (API JSON)
# =====================================================

def capturar_cptm():
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
    }

    try:
        resp = requests.post(URL_CPTM_API, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print("❌ Erro ao acessar API CPTM:", e)
        return {}

    dados = {}

    for item in data.get("d", []):
        numero = item.get("Linha")
        nome = item.get("Cor")
        status = item.get("Situacao")

        if numero and nome and status:
            linha = normalizar_nome(numero, nome)
            dados[linha] = status

    print(f"🚆 CPTM capturada via API: {len(dados)} linhas")
    return dados

# =====================================================
# MAIN
# =====================================================

def main():
    print("🚇🚆 Monitoramento Metrô + CPTM iniciado")

    garantir_csv_existe()
    estado_anterior = carregar_estado()
    estado_atual = {}

    dados_metro = capturar_metro()
    dados_cptm = capturar_cptm()

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
    print("✅ JSON atualizado e persistido com sucesso")


if __name__ == "__main__":
    main()
