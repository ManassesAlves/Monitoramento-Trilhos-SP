import os
import json
import time
import requests
import pandas as pd
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURAÇÕES ---
URL_METRO = "https://www.metro.sp.gov.br/pt_BR/sua-viagem/direto-metro/"
ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_ocorrencias.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, data=data)
        print(f"Telegram status: {response.status_code}")
    except Exception as e:
        print(f"Erro Telegram: {e}")

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def tentar_fechar_cookies(driver):
    try:
        xpath = "//button[contains(text(), 'Aceitar') or contains(text(), 'Concordar')]"
        wait = WebDriverWait(driver, 5)
        botao = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        botao.click()
        print("Cookies fechados.")
        time.sleep(2)
    except:
        print("Sem banner de cookies.")

def extrair_dados_selenium(driver):
    print(f"Acessando: {URL_METRO}")
    driver.get(URL_METRO)
    
    # TESTE DE CONEXÃO TELEGRAM
    enviar_telegram("🤖 *Debug Iniciado:* O robô acessou o site.")

    tentar_fechar_cookies(driver)
    time.sleep(10) # Espera carregar

    # --- O PULO DO GATO: TIRAR FOTO ---
    driver.save_screenshot("debug_tela.png")
    print("📸 Screenshot salvo como debug_tela.png")

    dados = {}
    try:
        body_element = driver.find_element(By.TAG_NAME, "body")
        texto_completo = body_element.get_attribute('innerText')
        
        # Salva o HTML para você ler depois
        with open("debug_html.txt", "w", encoding="utf-8") as f:
            f.write(texto_completo)

        # Regex ajustado
        padrao = r"(Linha\s+\d+[\w\s-]+?)(Operação Normal|Velocidade Reduzida|Paralisada|Encerrada|Operação Parcial)"
        matches = re.findall(padrao, texto_completo, re.IGNORECASE | re.MULTILINE)
        
        if matches:
            for nome, status in matches:
                nome_limpo = re.sub(r'[^\w\s-]', '', nome.strip().replace("\n", " ")).strip()
                dados[nome_limpo] = status.strip()
        else:
            print("⚠️ Regex não encontrou nada.")

    except Exception as e:
        print(f"Erro extração: {e}")

    return dados

def main():
    driver = configurar_driver()
    try:
        dados_novos = extrair_dados_selenium(driver)
    finally:
        driver.quit()

    # Cria arquivo JSON vazio se não existir (para não dar erro no Git)
    if not os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump({}, f)

    if dados_novos:
        print(f"✅ Sucesso: {len(dados_novos)} linhas.")
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(dados_novos, f, ensure_ascii=False, indent=4)
        
        # Salva CSV
        historico = [{"data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "linha": k, "status": v} for k,v in dados_novos.items()]
        df = pd.DataFrame(historico)
        header = not os.path.exists(ARQUIVO_HISTORICO)
        df.to_csv(ARQUIVO_HISTORICO, mode='a', index=False, header=header, sep=';', encoding='utf-8-sig')
    else:
        print("❌ Nenhuma linha identificada.")

if __name__ == "__main__":
    main()
