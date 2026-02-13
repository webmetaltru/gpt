# Dashboard Looker Studio: Mercado Livre + Shopee

Este repositório traz um **starter kit** para consolidar pedidos das APIs do Mercado Livre e Shopee em um CSV único, que você pode conectar no **Google Looker Studio** (via Google Sheets, BigQuery ou upload de arquivo).

## 1) Arquitetura recomendada

1. Script Python (`src/fetch_marketplaces.py`) busca pedidos nas APIs.
2. Script gera `data/orders_consolidado.csv` com schema padronizado.
3. Você conecta esse dataset no Looker Studio.

Campos gerados:

- `marketplace`
- `order_id`
- `created_at`
- `status`
- `currency`
- `total_amount`
- `shipping_cost`
- `items_count`
- `buyer_nickname`

## 2) Pré-requisitos

- Python 3.10+
- Credenciais de API:
  - Mercado Livre: `access_token` e `seller_id`
  - Shopee Partner API: `partner_id`, `partner_key`, `shop_id`, `access_token`

## 3) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha a `.env` com suas credenciais.

> Dica: use `export $(cat .env | xargs)` para carregar variáveis rapidamente no shell.

## 4) Extração dos dados

Exemplo para janeiro de 2026:

```bash
export $(cat .env | xargs)
python src/fetch_marketplaces.py \
  --date-from 2026-01-01T00:00:00.000Z \
  --date-to 2026-01-31T23:59:59.999Z \
  --output data/orders_consolidado.csv
```

## 5) Conectar no Looker Studio

### Opção A (mais simples): Google Sheets

1. Faça upload de `data/orders_consolidado.csv` para uma planilha Google.
2. No Looker Studio, clique em **Criar > Fonte de dados > Google Sheets**.
3. Selecione a aba com os dados.
4. Ajuste tipos:
   - `created_at`: Data/Hora
   - `total_amount` e `shipping_cost`: Número moeda
   - `items_count`: Número

### Opção B (mais robusta): BigQuery

1. Crie dataset no BigQuery (ex: `ecommerce_raw`).
2. Carregue o CSV para uma tabela (ex: `orders_consolidado`).
3. No Looker Studio, conecte a fonte BigQuery.

## 6) Layout sugerido do dashboard

Página "Visão Geral":

- Scorecards:
  - Receita total (`SUM(total_amount)`)
  - Pedidos (`COUNT_DISTINCT(order_id)`)
  - Ticket médio (`SUM(total_amount)/COUNT_DISTINCT(order_id)`)
- Série temporal por `created_at`
- Pizza por `marketplace`
- Tabela de status (`status`, pedidos, receita)

Página "Operacional":

- Frete médio por marketplace (`AVG(shipping_cost)`)
- Itens por pedido (`AVG(items_count)`)
- Filtro por período e marketplace

## 7) Observações importantes

- A Shopee exige assinatura HMAC e permissões corretas para cada endpoint.
- Alguns endpoints variam por região/conta (partner vs seller).
- Para produção, recomenda-se:
  - agendamento (Cloud Run + Cloud Scheduler)
  - armazenar em BigQuery
  - camada de transformação (dbt ou SQL views)

## 8) Próximos passos (se você quiser evoluir)

- Adicionar métricas de cancelamento/devolução
- Enriquecer com custo de produto e margem
- Criar metas mensais e comparação vs mês anterior
