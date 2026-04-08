# Google Ads Monitor — Coupler.io + FastAPI

## Arquitetura

```
Google Ads → Coupler.io (a cada 15min) → Postgres / Sheets
                                              ↓
                                     Webhook POST /coupler-webhook
                                              ↓
                                    FastAPI (lê dados, compara, alerta)
```

---

## 1. Configuração do Coupler.io

### 1.1 Criar conta e conectar Google Ads

1. Acesse [app.coupler.io](https://app.coupler.io) e crie uma importação.
2. **Source** → selecione **Google Ads**.
3. Autorize sua conta Google com acesso ao Google Ads.
4. Selecione a conta/MCC desejada.

### 1.2 Selecionar métricas e dimensões

Na tela de configuração da source, escolha **Custom Report** e adicione:

| Tipo       | Campo             |
|------------|-------------------|
| Dimension  | `campaign.id`     |
| Dimension  | `campaign.name`   |
| Dimension  | `campaign.status` |
| Dimension  | `segments.date`   |
| Metric     | `metrics.impressions` |
| Metric     | `metrics.cost_micros` |

> **Dica:** `cost_micros` vem em micros (÷ 1.000.000 = valor real). Você pode criar coluna calculada no Coupler ou tratar no backend.

### 1.3 Período

- Configure o **Date Range** para `Yesterday` + `Today`.
- Isso garante que cada execução traga os dois dias para comparação.

### 1.4 Frequência

- **Schedule** → a cada **15 minutos**.
- Coupler roda automaticamente e sobrescreve os dados no destino.

### 1.5 Destino

#### Opção A: PostgreSQL

1. Em **Destination**, selecione **PostgreSQL**.
2. Informe host, porta, database, user e password.
3. Defina o nome da tabela: `google_ads_data`.
4. Modo: **Replace** (sobrescreve a cada execução).

#### Opção B: Google Sheets

1. Em **Destination**, selecione **Google Sheets**.
2. Escolha a planilha e aba de destino.
3. Modo: **Replace**.

### 1.6 Webhook de saída

1. Na importação criada, vá em **Settings → Notifications → Webhook**.
2. Ative e cole a URL do seu backend:
   ```
   https://seu-dominio.com/coupler-webhook
   ```
3. O Coupler fará um `POST` para essa URL ao concluir cada importação.

---

## 2. Configuração do Backend

### 2.1 Pré-requisitos

- Python 3.11+
- PostgreSQL (se usar Opção A)
- Credenciais de Service Account Google (se usar Opção B / Sheets)

### 2.2 Instalar

```bash
cd project
cp .env.example .env
# edite .env com suas credenciais
pip install -r requirements.txt
```

### 2.3 Configurar `.env`

```env
DATA_SOURCE=postgres           # ou "sheets"
DATABASE_URL=postgresql://user:pass@localhost:5432/coupler_monitor
SPEND_THRESHOLD=1.0
```

### 2.4 Rodar

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.5 Testar manualmente

```bash
# Simular webhook do Coupler
curl -X POST http://localhost:8000/coupler-webhook \
  -H "Content-Type: application/json" \
  -d '{"status": "success"}'

# Health check
curl http://localhost:8000/health
```

---

## 3. Estrutura do Projeto

```
project/
├── app/
│   ├── main.py                  # FastAPI app
│   ├── config.py                # Settings via pydantic
│   ├── api/
│   │   └── webhook.py           # POST /coupler-webhook + GET /health
│   ├── services/
│   │   ├── coupler_reader.py    # Lê Postgres ou Sheets
│   │   └── monitor.py           # Snapshots, detecção, alertas
│   ├── models/
│   │   └── campaign.py          # SQLAlchemy models
│   └── database/
│       └── connection.py        # Engine + session
├── requirements.txt
└── .env.example
```

---

## 4. Regras de Detecção

| Evento              | Condição                                       |
|---------------------|-------------------------------------------------|
| Campanha parou      | impressions hoje = 0 AND ontem > 0              |
| Spend zerou         | cost hoje = 0 AND ontem > SPEND_THRESHOLD       |
| Status mudou        | status hoje ≠ status ontem                      |

---

## 5. Garantias de Produção

- **Idempotência:** cada batch recebe um hash do conteúdo; reprocessar os mesmos dados é ignorado.
- **Alertas únicos por dia:** `alert_key = tipo:campaign_id:data` — mesmo alerta não dispara duas vezes no mesmo dia.
- **Snapshots versionados:** toda execução grava um snapshot imutável no banco para auditoria.
- **Logs estruturados:** toda operação é logada com nível e contexto.

---

## 6. Próximos Passos

- Trocar `send_alert()` por integração real (Slack, email, PagerDuty).
- Adicionar autenticação no webhook (HMAC ou token).
- Dashboard com histórico de snapshots.
- Adicionar métricas de CTR, conversões, etc.
