import os
import json
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# --- CONFIGURAÇÕES ---
URL_ENDPOINT_PHP = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"
URL_PAGE_MAIN = "https://www.metro.sp.gov.br/pt_BR/sua-viagem/direto-metro/"
ARQUIVO_ESTADO = "estado_metro.json"
ARQUIVO_HISTORICO = "historico_ocorrencias.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Aviso: Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Erro Telegram: {e}")

def parse_html_generico(html_content, origem):
    """ Tenta extrair linhas de qualquer HTML usando busca por texto """
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator='\n')
    lines = text.split('\n')
    
    dados = {}
    # Linhas e termos para buscar
    nomes_linhas = ["Azul", "Verde", "Vermelha", "Amarela", "Lilás", "Prata"]
    status_possiveis = ["Operação Normal", "Velocidade Reduzida", "Paralisada", "Encerrada", "Operação Parcial"]

    for i, line in enumerate(lines):
        line_clean = line.strip()
        # Se a linha contém "Linha" e o nome de uma cor
        if "Linha" in line_clean and any(nome in line_clean for nome in nomes_linhas):
            
            # Tenta achar o status na mesma linha
            status_encontrado = next((s for s in status_possiveis if s in line_clean), None)
            
            # Se não achou, olha a próxima linha (comum em layouts mobile)
            if not status_encontrado and i + 1 < len(lines):
                prox_linha = lines[i+1].strip()
                status_encontrado = next((s for s in status_possiveis if s in prox_linha), None)
            
            if status_encontrado:
                # Limpeza do nome da linha (remove o status se estiver grudado)
                nome_final = line_clean.split("Operação")[0].split("Velocidade")[0].strip()
                if len(nome_final) < 50: # Evita pegar textos longos errados
                    dados[nome_final] = status_encontrado

    if dados:
        print(f"✅ Sucesso via {origem}: {len(dados)} linhas encontradas.")
    return dados

def obter_dados():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

    # 1. TENTATIVA VIA ENDPOINT PHP
    print(f"Tentando endpoint PHP: {URL_ENDPOINT_PHP}...")
    try:
        resp = requests.get(URL_ENDPOINT_PHP, headers=headers, timeout=10)
        resp.encoding = 'utf-8' # Força UTF-8
        if resp.status_code == 200:
            dados = parse_html_generico(resp.text, "PHP Endpoint")
            if dados: return dados
            print(f"⚠️ Endpoint PHP retornou 200 mas sem dados legíveis. Conteúdo inicial: {resp.text[:200]}")
    except Exception as e:
        print(f"Erro no PHP Endpoint: {e}")

    # 2. TENTATIVA VIA PÁGINA PRINCIPAL (FALLBACK)
    print(f"Tentando página principal: {URL_PAGE_MAIN}...")
    try:
        resp = requests.get(URL_PAGE_MAIN, headers=headers, timeout=15)
        resp.encoding = 'utf-8'
        if resp.status_code == 200:
            dados = parse_html_generico(resp.text, "Main Page")
            if dados: return dados
            # Se falhar aqui, imprime o HTML para debug no log do GitHub
            print("❌ FALHA CRÍTICA: HTML da página principal baixado, mas parser não achou linhas.")
            print("--- INÍCIO HTML DEBUG ---")
            print(resp.text[:1000]) # Mostra os primeiros 1000 caracteres
            print("--- FIM HTML DEBUG ---")
    except Exception as e:
        print(f"Erro na Main Page: {e}")

    return {}

def main():
    print(" Iniciando verificação...")
    dados_novos = obter_dados()

    # SE NÃO TIVER DADOS, FORÇA ERRO PARA GITHUB FICAR VERMELHO
    if not dados_novos:
        print("❌ ERRO: Não foi possível extrair dados de nenhuma fonte.")
        exit(1) # Isso faz o GitHub Actions marcar como FALHA ❌

    # Carrega estado anterior
    dados_antigos = {}
    arquivo_existe = os.path.exists(ARQUIVO_ESTADO)
    if arquivo_existe:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            try:
                dados_antigos = json.load(f)
            except:
                pass

    mudancas = []
    historico = []
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for linha, status in dados_novos.items():
        status_antigo = dados_antigos.get(linha)
        
        # Detecta mudança OU nova linha detectada
        if status != status_antigo:
            icone = "🟢" if "Normal" in status else "🔴" if "Paralisada" in status else "🟡"
            status_txt_antigo = status_antigo if status_antigo else "Início"
            
            mudancas.append(f"{icone} *{linha}*\nDe: {status_txt_antigo}\nPara: *{status}*")
            
            historico.append({
                "data": agora,
                "linha": linha,
                "status_anterior": status_txt_antigo,
                "status_novo": status
            })

    # SALVAR CSV
    if historico:
        df = pd.DataFrame(historico)
        header = not os.path.exists(ARQUIVO_HISTORICO)
        df.to_csv(ARQUIVO_HISTORICO, mode='a', index=False, header=header, sep=';', encoding='utf-8-sig')
        print("CSV atualizado.")

    # SALVAR JSON (Sempre salva se tiver dados novos, garantindo a criação do arquivo)
    if mudancas or not arquivo_existe:
        if mudancas:
            msg = f"🚨 *METRÔ SP* 🚨\n\n" + "\n\n".join(mudancas)
            msg += f"\n\n_Horário: {datetime.now().strftime('%H:%M')}_"
            enviar_telegram(msg)
        
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(dados_novos, f, ensure_ascii=False, indent=4)
        print("JSON de estado salvo com sucesso.")
    else:
        print("Sem mudanças no status.")

if __name__ == "__main__":
    main()
