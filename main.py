import os
import json
import time
import requests
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configurações ---
ARQUIVO_ESTADO = "estado_metro.json"
URL_METRO = "https://www.metro.sp.gov.br/pt_BR/sua-viagem/direto-metro/"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
        print("Mensagem enviada para o Telegram.")
    except Exception as e:
        print(f"Erro ao enviar telegram: {e}")

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # --- CAMUFLAGEM (STEALTH) ---
    # Simula um User-Agent de Windows 10 real
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Remove flags que indicam automação
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # Hack extra para enganar verificações de JS
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
        """
    })
    return driver

def extrair_dados(driver):
    driver.get(URL_METRO)
    # Espera aleatória pequena para parecer humano
    time.sleep(3) 
    
    dados_atuais = {}
    
    try:
        wait = WebDriverWait(driver, 20)
        # Espera carregar qualquer elemento que contenha 'Linha'
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Linha')]")))
        
        # Busca genérica para encontrar as linhas
        linhas_elementos = driver.find_elements(By.XPATH, "//li[contains(., 'Linha')] | //div[contains(., 'Linha')]")
        
        for elemento in linhas_elementos:
            texto = elemento.text.strip()
            # Validação simples para garantir que pegamos a info certa
            if "Linha" in texto and any(status in texto for status in ["Normal", "Reduzida", "Paralisada", "Encerrada"]):
                partes = texto.split('\n')
                nome_linha = partes[0].strip()
                status_linha = partes[1].strip() if len(partes) > 1 else "Status desconhecido"
                
                # Armazena no dicionário: Chave (Nome) -> Valor (Status)
                dados_atuais[nome_linha] = status_linha
                
    except Exception as e:
        print(f"Erro na extração: {e}")
    
    return dados_atuais

def main():
    print("Iniciando scraper camuflado...")
    driver = configurar_driver()
    
    try:
        dados_novos = extrair_dados(driver)
    finally:
        driver.quit()

    if not dados_novos:
        print("Nenhum dado encontrado. Abortando.")
        return

    # Carrega estado anterior
    dados_antigos = {}
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            try:
                dados_antigos = json.load(f)
            except:
                pass

    # Compara e notifica
    mudancas = []
    
    for linha, status in dados_novos.items():
        status_anterior = dados_antigos.get(linha)
        
        # Se o status mudou OU é uma linha nova que não existia
        if status != status_anterior:
            # Ícones para facilitar leitura
            icone = "🟢" if "Normal" in status else "🔴" if "Paralisada" in status else "🟡"
            mudancas.append(f"{icone} *{linha}*\nDe: {status_anterior}\nPara: *{status}*")

    if mudancas:
        msg_final = f"🚨 *ATUALIZAÇÃO METRÔ SP* 🚨\n\n" + "\n\n".join(mudancas)
        msg_final += f"\n\n_Verificado em: {datetime.now().strftime('%H:%M')}_"
        
        print("Mudanças detectadas. Enviando Telegram...")
        enviar_telegram(msg_final)
        
        # Salva o novo estado
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(dados_novos, f, ensure_ascii=False, indent=4)
        print("Estado atualizado salvo.")
    else:
        print("Nenhuma mudança nos status.")

if __name__ == "__main__":
    main()
