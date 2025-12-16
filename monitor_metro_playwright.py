import requests
from bs4 import BeautifulSoup
import json
import os
import csv
import hashlib
from datetime import datetime, timedelta, timezone

# =====================================================
# PATH BASE
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_transporte.json")
ARQUIVO_HISTORICO = os.path.join(BASE_DIR, "historico_transporte.csv")
ARQUIVO_HASH = os.path.join(BASE_DIR, "hash_sites.json")

# =====================================================
# URLS
# =====================================================

URL_METRO = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"
URL_VIAMOBILIDADE = "https://trilhos.motiva.com.br/viamobilidade8e9/situacao-das-linhas/"
URL_CPTM = "https://www.cptm.sp.gov.br/cptm"

# =====================================================
# TELEGRAM
# =====================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")               # grupo
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID")   # privado

# =====================================================
# PADRÕES DE STATUS
# =====================================================

PADROES_ENCERRADA = [
    "operação encerrada",
    "circulação encerrada",
    "serviço encerrado",
]

PADROES_PROBLEMA = [
    "velocidade reduzida",
    "operação parcial",
    "operação interrompida",
    "operação prejudicada",
    "circulação com restrições",
    "circulação alterada",
    "intervalos maiores",
    "falha",
    "problema",
]

PADROES_NORMAL = [
    "operação normal",
    "circulação normal",
    "operação normalizada",
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
        data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10,
    )


def enviar_telegram_admin(msg):
    if not TOKEN or not ADMIN_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": ADMIN_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10,
    )


def identificar_operador(linha):
    if linha.startswith("Linha"):
        return "metro"
    if linha.startswith("ViaMobilidade"):
        return "viamobilidade"
    if linha.startswith("CPTM"):
        return "cptm"
    return "desconhecido"


def emoji_status(status, operador):
    s = status.lower()
    if "encerrada" in s:
        return {"metro": "🚇⛔", "viamobilidade": "🚆⛔", "cptm": "🚈⛔"}.get(operador, "⛔")
    return {
        "metro": "🚇✅" if "normal" in s else "🚇⚠️",
        "viamobilidade": "🚆✅" if "normal" in s else "🚆⚠️",
        "cptm": "🚈✅" if "normal" in s else "🚈⚠️",
    }.get(operador, "❓")


def classificar_status(texto):
    t = texto.lower()

    for p in PADROES_ENCERRADA:
        if p in t:
            return "Operação Encerrada", "Operação Encerrada"

    for p in PADROES_PROBLEMA:
        if p in t:
            return p.title(), p.title()

    for p in PADROES_NORMAL:
        if p in t:
            return "Operação normal", None

    return "Operação normal", None


def obter_status_antigo(valor):
    if isinstance(valor, dict):
        return valor.get("status")
    if isinstance(valor, str):
        return valor
    return None


def hash_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()

# =====================================================
# ESTRUTURA / HASH
# =====================================================

def carregar_hashes():
    if not os.path.exists(ARQUIVO_HASH):
        return {}
    with open(ARQUIVO_HASH, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_hashes(hashes):
    with open(ARQUIVO_HASH, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)


def verificar_mudanca_estrutura(nome_site, html):
    hashes = carregar_hashes()
    novo_hash = hash_texto(html)

    if nome_site in hashes and hashes[nome_site] != novo_hash:
        enviar_telegram_admin(
            f"🛠️ *Alerta técnico*\n"
            f"O site **{nome_site}** mudou a estrutura.\n"
            f"O scraping pode precisar de ajuste."
        )

    hashes[nome_site] = novo_hash
    salvar_hashes(hashes)

# =====================================================
# PERSISTÊNCIA
# =====================================================

def garantir_csv_existe():
    if not os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["Data", "Hora", "Linha", "Status Novo", "Status Antigo", "Descricao"]
            )


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
        csv.writer(f).writerow(
            [t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S"), linha, novo, antigo, descricao or ""]
        )

# =====================================================
# SCRAPING METRÔ
# =====================================================

def capturar_metro():
    dados = {}
    try:
        r = requests.get(URL_METRO, timeout=15)
        r.raise_for_status()
        verificar_mudanca_estrutura("MetroSP", r.text)
    except Exception as e:
        print(f"⚠️ Metrô fora: {e}")
        return dados

    soup = BeautifulSoup(r.text, "lxml")
    for item in soup.select("li.linha"):
        n = item.select_one(".linha-numero")
        nome = item.select_one(".linha-nome")
        s = item.select_one(".linha-situacao")
        if n and nome and s:
            dados[f"Linha {n.text.strip()} – {nome.text.strip()}"] = {
                "status": s.text.strip(),
                "descricao": None,
            }
    return dados

# =====================================================
# SCRAPING VIAMOBILIDADE
# =====================================================

def capturar_viamobilidade():
    linhas = {
        "ViaMobilidade – Linha 8 Diamante": "linha 8",
        "ViaMobilidade – Linha 9 Esmeralda": "linha 9",
    }
    dados = {l: {"status": "Operação normal", "descricao": None} for l in linhas}

    try:
        r = requests.get(URL_VIAMOBILIDADE, timeout=30)
        r.raise_for_status()
        verificar_mudanca_estrutura("ViaMobilidade", r.text)
    except Exception as e:
        print(f"⚠️ ViaMobilidade fora: {e}")
        return dados

    texto = r.text.lower()
    for linha, chave in linhas.items():
        trecho = texto.split(chave, 1)[1][:600] if chave in texto else texto
        status, desc = classificar_status(trecho)
        dados[linha] = {"status": status, "descricao": desc}

    return dados

# =====================================================
# SCRAPING CPTM (PLAYWRIGHT)
# =====================================================

def capturar_cptm():
    from playwright.sync_api import sync_playwright

    linhas_site = {
        "Linha 7 – Rubi": "CPTM – Linha 7 – Rubi",
        "Linha 8 – Diamante": "CPTM – Linha 8 – Diamante",
        "Linha 9 – Esmeralda": "CPTM – Linha 9 – Esmeralda",
        "Linha 10 – Turquesa": "CPTM – Linha 10 – Turquesa",
        "Linha 11 – Coral": "CPTM – Linha 11 – Coral",
        "Linha 12 – Safira": "CPTM – Linha 12 – Safira",
        "Linha 13 – Jade": "CPTM – Linha 13 – Jade",
    }

    dados = {
        nome: {"status": "Operação normal", "descricao": None}
        for nome in linhas_site.values()
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(URL_CPTM, timeout=30000)
            page.wait_for_timeout(5000)

            texto = page.inner_text("body").lower()
            html = page.content()
            browser.close()

        verificar_mudanca_estrutura("CPTM", html)

    except Exception as e:
        print(f"⚠️ CPTM Playwright falhou: {e}")
        return dados

    for chave_site, nome_padrao in linhas_site.items():
        chave = chave_site.lower()
        if chave in texto:
            trecho = texto.split(chave, 1)[1][:600]
            status, desc = classificar_status(trecho)
            dados[nome_padrao] = {"status": status, "descricao": desc}

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
    estado_atual.update(capturar_cptm())

    for linha, info in estado_atual.items():
        novo = info["status"]
        desc = info.get("descricao")
        antigo = obter_status_antigo(estado_anterior.get(linha))

        if antigo is not None and antigo != novo:
            operador = identificar_operador(linha)
            emoji = emoji_status(novo, operador)

            msg = f"{emoji} **{linha}**\n🔄 De: {antigo}\n➡️ Para: **{novo}**"
            if desc:
                msg += f"\n📝 Motivo: {desc}"

            enviar_telegram(msg)
            salvar_historico(linha, novo, antigo, desc)

    salvar_estado(estado_atual)

# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
