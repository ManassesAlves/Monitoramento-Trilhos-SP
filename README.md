# 🚇 Monitoramento de Trilhos – SP (Metrô, CPTM e ViaMobilidade)

Este projeto realiza o **monitoramento automático da situação operacional** das linhas de transporte sobre trilhos da Região Metropolitana de São Paulo, abrangendo:

- 🚇 **Metrô de São Paulo**
- 🚈 **CPTM**
- 🚆 **ViaMobilidade (Linhas 8 e 9)**

O sistema verifica periodicamente o status das linhas, **detecta mudanças**, **registra histórico** e **envia notificações via Telegram somente quando ocorre alteração no status**, evitando alertas repetitivos ou falsos positivos.

---

## 🎯 Objetivo

Fornecer um monitoramento confiável, automatizado e resiliente do transporte ferroviário de SP, com foco em:

- Detecção de problemas operacionais  
- Notificações em tempo quase real  
- Persistência de histórico  
- Baixa dependência de scraping frágil  
- Execução contínua via **GitHub Actions**

---

## ⚙️ Como funciona

### 🔄 Execução automática
O script é executado periodicamente através do **GitHub Actions**, em intervalos configuráveis via cron.

### 🔍 Coleta de dados
- **Metrô SP**  
  Scraping direto de HTML, com timeout e fallback para evitar falhas do pipeline.

- **ViaMobilidade (Linhas 8 e 9)**  
  Leitura de informações públicas do site oficial.

- **CPTM**  
  Monitoramento em **modo global**, assumindo *Operação Normal* como padrão e alterando o status **somente quando o site menciona explicitamente problemas**, evitando interpretações incorretas (como confundir nome/cor da linha com status).

### 📊 Padronização de status
- ✅ **Operação normal**
- ⚠️ **Qualquer outro status** (velocidade reduzida, operação parcial, falha, etc.)

### 🔔 Notificações
- As notificações são enviadas via **Telegram**
- Um alerta **só é disparado quando há mudança real no status**
- Sempre que possível, a **descrição do problema** é incluída na mensagem

---

## 📲 Exemplo de notificação

```
🚇⚠️ Linha 3 – Vermelha
🔄 De: Operação normal
➡️ Para: Velocidade reduzida
📝 Motivo: Falha em equipamento de sinalização
```

---

## 💾 Persistência de dados

- `estado_transporte.json` – Último estado conhecido  
- `historico_transporte.csv` – Histórico de mudanças

Ambos são versionados no repositório para garantir continuidade entre execuções.

---

## 🛡️ Resiliência e boas práticas

- Timeouts configurados
- Tratamento de exceções por operador
- Fallback seguro quando sites estão fora do ar
- Baixa frequência de acesso (baixo risco de bloqueio)

---

## 🔐 Variáveis de ambiente

Configure como **Secrets** no GitHub:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

---

## 🚀 Tecnologias utilizadas

- Python 3.11+
- requests
- BeautifulSoup (bs4)
- GitHub Actions
- Telegram Bot API

---

## ✅ Status do projeto

🟢 **Estável – Pronto para uso em produção**
