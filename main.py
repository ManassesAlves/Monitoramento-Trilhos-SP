import os
import json
import time
import requests
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# --- CONFIGURAÇÕES ---
ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_ocorrencias.csv"
URL_METRO = "https://www.metro.sp.gov.br/pt_BR/sua-viagem/direto-metro/"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Aviso: Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Erro Telegram: {e}")

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # User-Agent atualizado para evitar bloqueios
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def extrair_dados_robusto(driver):
    print(f"Acessando {URL_METRO}...")
    driver.get(URL_METRO)
    
    # Espera fixa de 10s para garantir que scripts do site carreguem
    time.sleep(10)
    
    dados_atuais = {}
    
    try:
        # Debug: Mostra o título da página para sabermos se carregou
        print(f"Título da página acessada: {driver.title}")

        # ESTRATÉGIA NOVA: Pegar todo o texto do corpo e processar linha a linha
        # Isso evita erros se o site mudar de <li> para <div> ou <span>
        body_text = driver.find_element(By.TAG_NAME, "body").text
        linhas_texto = body_text.split('\n')
        
        # Palavras-chave de status
        status_conhecidos = ["Operação Normal", "Velocidade Reduzida", "Paralisada", "Encerrada", "Operação Parcial"]

        for i, linha in enumerate(linhas_texto):
            linha = linha.strip()
            
            # Procura por linhas que tenham nome de linha (ex: "Linha 1-Azul")
            if "Linha" in linha and ("Azul" in linha or "Verde" in linha or "Vermelha" in linha or "Amarela" in linha or "Lilás" in linha or "Prata" in linha):
                
                # O status costuma estar na mesma linha ou na próxima
                status_encontrado = None
                
                # Verifica se o status está na mesma linha (Ex: "Linha 1-Azul Operação Normal")
                for s in status_conhecidos:
                    if s in linha:
                        status_encontrado = s
                        break
                
                # Se não achou na mesma linha, olha a próxima linha do texto
                if not status_encontrado and i + 1 < len(linhas_texto):
                    prox_linha = linhas_texto[i+1].strip()
                    for s in status_conhecidos:
                        if s in prox_linha:
                            status_encontrado = s
                            break
                
                # Se achou algo, salva
                if status_encontrado:
                    # Remove o status do nome da linha para limpar (caso esteja junto)
                    nome_limpo = linha.replace(status_encontrado, "").strip()
                    dados_atuais[nome_limpo] = status_encontrado

        print(f"Linhas encontradas: {len(dados_atuais)}")
        print(dados_atuais)

    except Exception as e:
        print(f"Erro crítico na extração: {e}")
        # Se der erro, salva o HTML para debug (opcional, ajuda a entender o erro)
        with open("erro_pagina.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

    return dados_atuais

def main():
    driver = configurar_driver()
    try:
        dados_novos = extrair_dados_robusto(driver)
    finally:
        driver.quit()

    # --- CORREÇÃO PRINCIPAL ---
    # Se não encontrar dados, forçamos um erro visível ou salvamos vazio para debug
    if not dados_novos:
        print("❌ ALERTA: O robô acessou o site mas não conseguiu ler as linhas.")
        print("Possíveis causas: O site mudou o texto, está bloqueando o acesso ou demorou para carregar.")
        # Não damos 'return' aqui se quisermos forçar a criação do arquivo, 
        # mas sem dados o arquivo ficaria vazio. Melhor avisar no log.
        return

    # Lógica de Arquivos (JSON e CSV)
    dados_antigos = {}
    arquivo_existe = os.path.exists(ARQUIVO_ESTADO)
    
    if arquivo_existe:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            try:
                dados_antigos = json.load(f)
            except:
                pass

    mudancas_notificacao = []
    registros_historico = []
    timestamp_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for linha, status_novo in dados_novos.items():
        status_anterior = dados_antigos.get(linha)
        
        if status_novo != status_anterior:
            icone = "🟢" if "Normal" in status_novo else "🔴" if "Paralisada" in status_novo else "🟡"
            status_exibicao_antigo = status_anterior if status_anterior else "Sem registro"
            
            mudancas_notificacao.append(f"{icone} *{linha}*\nDe: {status_exibicao_antigo}\nPara: *{status_novo}*")
            
            registros_historico.append({
                "data_hora": timestamp_agora,
                "linha": linha,
                "status_anterior": status_exibicao_antigo,
                "status_novo": status_novo
            })

    # Salva CSV se houver histórico novo
    if registros_historico:
        df_hist = pd.DataFrame(registros_historico)
        csv_existe = os.path.isfile(ARQUIVO_HISTORICO)
        df_hist.to_csv(ARQUIVO_HISTORICO, mode='a', index=False, header=not csv_existe, encoding='utf-8-sig', sep=';')

    # Salva JSON e Notifica
    # Salva sempre que tiver dados válidos, para garantir que o arquivo exista
    if mudancas_notificacao or not arquivo_existe:
        if mudancas_notificacao:
            msg = f"🚨 *ATUALIZAÇÃO METRÔ SP* 🚨\n\n" + "\n\n".join(mudancas_notificacao)
            msg += f"\n\n_Verificado em: {datetime.now().strftime('%H:%M')}_"
            enviar_telegram(msg)
        
        # O PULO DO GATO: O arquivo é criado aqui.
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(dados_novos, f, ensure_ascii=False, indent=4)
        print(f"Sucesso: Arquivo {ARQUIVO_ESTADO} atualizado/criado.")
    else:
        print("Sem mudanças, mantendo arquivo atual.")

if __name__ == "__main__":
    main()
