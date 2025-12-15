import requests
from bs4 import BeautifulSoup
import json
import os
import csv
from datetime import datetime, timedelta, timezone

# =====================================================
# PATH BASE (GARANTE DIRETÓRIO CORRETO)
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

def log(msg):
    print(f"[LOG] {msg}")

def agora_sp():
    return datetime.now(timezone(timedelta(hours=-3)))

def enviar_telegram(msg):
    if not TOKEN or not CHAT_ID:
        log("Telegram não configurado")
        return
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )

# =====================================================
# PERSISTÊNCIA
# =====================================================

def garantir_csv_existe():
    if not os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Data", "Hora", "Linha", "Status Novo", "Status Antigo"])
        log("CSV criado")

def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        log("JSON não existe — primeira execução")
        return {}
    with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    log("JSON salvo")

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

    log(f"Metrô capturado: {len(dados)} linhas")
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

    log("ViaMobilidade capturada")
    return dados

# =====================================================
# MAIN
# =====================================================

def main():
    log("Iniciando monitoramento")

    # 🔒 GARANTE CRIAÇÃO DOS ARQUIVOS
    garantir_csv_existe()
    estado_anterior = carregar_estado()

    estado_atual = {}
    estado_atual.update(capturar_metro())
    estado_atual.update(capturar_viamobilidade())

    for linha, status in estado_atual.items():
        antigo = estado_anterior.get(linha)

        if antigo is not None and antigo != status:
            enviar_telegram(
                f"🚇 **{linha}**\n"
                f"🔄 {antigo} ➜ **{status}**"
            )

            with open(ARQUIVO_HISTORICO, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                t = agora_sp()
                writer.writerow([
                    t.strftime("%Y-%m-%d"),
                    t.strftime("%H:%M:%S"),
                    linha,
                    status,
                    antigo,
                ])

    salvar_estado(estado_atual)
    log("Finalizado com sucesso")

# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
