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

# --- CONFIGURAÇÕES ---
URL_METRO = "https://www.metro.sp.gov.br/pt_BR/sua-viagem/direto-metro/"
ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_ocorrencias.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
    except:
        pass

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Roda sem interface gráfica
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # Simula um usuário real para não ser bloqueado
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def extrair_dados_selenium(driver):
    print(f"Acessando via Selenium: {URL_METRO}")
    driver.get(URL_METRO)
    
    # 1. Espera Inteligente: Aguarda até aparecer a palavra "Linha" na tela
    try:
        wait = WebDriverWait(driver, 25)
        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "Linha"))
    except:
        print("⚠️ Tempo de espera excedido. O site pode estar lento, mas vamos tentar ler mesmo assim.")

    # 2. Espera de Segurança (Garante que o JS terminou de montar a lista)
    time.sleep(5)

    dados = {}
    try:
        # Pega TODO o texto visível da página
        body_text = driver.find_element(By.TAG_NAME, "body").text
        linhas_texto = body_text.split('\n')
        
        # Termos para procurar
        nomes_linhas = ["Azul", "Verde", "Vermelha", "Amarela", "Lilás", "Prata"]
        status_possiveis = ["Operação Normal", "Velocidade Reduzida", "Paralisada", "Encerrada", "Operação Parcial"]

        for i, linha in enumerate(linhas_texto):
            linha_limpa = linha.strip()
            
            # Se a linha contém "Linha" e uma das cores conhecidas
            if "Linha" in linha_limpa and any(cor in linha_limpa for cor in nomes_linhas):
                
                # Tenta achar o status na mesma linha
                status_encontrado = next((s for s in status_possiveis if s in linha_limpa), None)
                
                # Se não achou, olha a linha de baixo (estrutura comum em mobile)
                if not status_encontrado and i + 1 < len(linhas_texto):
                    prox_linha = linhas_texto[i+1].strip()
                    status_encontrado = next((s for s in status_possiveis if s in prox_linha), None)

                if status_encontrado:
                    # Salva no dicionário. Ex: "Linha 1-Azul" -> "Operação Normal"
                    # Remove o status do nome da linha para limpar
                    nome_linha = linha_limpa.split("Operação")[0].split("Velocidade")[0].strip()
                    
                    # Filtro extra para evitar lixo
                    if len(nome_linha) < 60: 
                        dados[nome_linha] = status_encontrado

    except Exception as e:
        print(f"Erro ao ler página: {e}")

    return dados

def main():
    driver = configurar_driver()
    try:
        dados_novos = extrair_dados_selenium(driver)
    finally:
        driver.quit()

    if not dados_novos:
        print("❌ ERRO CRÍTICO: O Selenium abriu o site, mas não achou nenhuma linha.")
        # NÃO vamos dar exit(1) aqui. Vamos deixar criar um JSON vazio se for preciso,
        # para não quebrar o workflow do Git, mas avisamos no log.
    else:
        print(f"✅ Sucesso! {len(dados_novos)} linhas encontradas.")

    # --- LÓGICA DE ARQUIVOS ---
    dados_antigos = {}
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            try:
                dados_antigos = json.load(f)
            except:
                pass

    mudancas = []
    historico = []
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Se dados_novos estiver vazio (erro no site), usamos os dados antigos para não gerar falso alerta
    # ou simplesmente pulamos a verificação.
    if dados_novos:
        for linha, status in dados_novos.items():
            status_antigo = dados_antigos.get(linha)
            
            if status != status_antigo:
                icone = "🟢" if "Normal" in status else "🔴" if "Paralisada" in status else "🟡"
                status_txt_antigo = status_antigo if status_antigo else "Sem registro"
                
                mudancas.append(f"{icone} *{linha}*\nDe: {status_txt_antigo}\nPara: *{status}*")
                
                historico.append({
                    "data": agora,
                    "linha": linha,
                    "status_anterior": status_txt_antigo,
                    "status_novo": status
                })

    # 1. Salva CSV
    if historico:
        df = pd.DataFrame(historico)
        header = not os.path.exists(ARQUIVO_HISTORICO)
        df.to_csv(ARQUIVO_HISTORICO, mode='a', index=False, header=header, sep=';', encoding='utf-8-sig')
        print("Histórico CSV atualizado.")

    # 2. Salva JSON e Notifica
    # Importante: Salvamos o JSON mesmo se não houver mudança, para garantir que o arquivo exista
    # Se dados_novos for vazio (erro), NÃO sobrescrevemos para não perder o estado anterior.
    if dados_novos:
        if mudancas:
            msg = f"🚨 *METRÔ SP* 🚨\n\n" + "\n\n".join(mudancas)
            msg += f"\n\n_Horário: {datetime.now().strftime('%H:%M')}_"
            enviar_telegram(msg)
        
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(dados_novos, f, ensure_ascii=False, indent=4)
        print("Arquivo JSON salvo/atualizado.")
    else:
        print("Sem dados novos válidos. Mantendo estado anterior.")
        # Se o arquivo não existir (primeira execução com erro), cria um vazio para o Git não reclamar
        if not os.path.exists(ARQUIVO_ESTADO):
             with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
                json.dump({}, f)

if __name__ == "__main__":
    main()
