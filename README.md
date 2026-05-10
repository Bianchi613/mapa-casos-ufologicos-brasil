# Mapa de Casos Ufológicos Brasileiros

![Mapa de Casos Ufológicos Brasileiros](assets/mapa-casos-ufologicos-brasil.png)

Dashboard estático e interativo com casos ufológicos brasileiros em um mapa Leaflet. O HTML publicado é gerado a partir de uma base PostgreSQL e pode ser servido por qualquer servidor estático.

## Recursos

- Mapa interativo com marcadores agrupados.
- Contornos dos estados brasileiros via GeoJSON do IBGE.
- Filtros por busca, estado, década e presença de seres.
- Painel lateral com resumo dos casos.
- Linhas conectando casos com múltiplos pontos no mapa.
- Build final em HTML estático, sem backend em produção.

## Estrutura

```text
.
├── assets/                         # Imagens do README
├── deploy/                         # Exemplos de serviços systemd
├── docker/                         # Compose/README para banco local
├── output/                         # GeoJSON cacheado
├── scripts/app.py                  # Gerador do HTML
├── vendor/                         # Leaflet e plugins locais
├── index.html                      # Redireciona para o mapa
└── mapa_casos_brasileiros.html     # Dashboard gerado
```

## Configuração

Crie seu arquivo local de ambiente a partir do exemplo:

```bash
cp .env.example .env
```

Edite o `.env` com as credenciais do seu banco. O arquivo `.env` é ignorado pelo Git e não deve ser commitado.

Variável principal:

```text
DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost:5432/ufologia
```

O script espera encontrar a tabela `public.casos` com uma coluna `localizacao` em JSONB contendo latitude e longitude.

## Gerar o HTML

Instale as dependências Python necessárias:

```bash
python3 -m pip install --user sqlalchemy psycopg2-binary
```

Carregue as variáveis de ambiente e gere o mapa:

```bash
set -a
source .env
set +a
python3 scripts/app.py
```

Saída esperada:

```text
mapa_casos_brasileiros.html
```

Esse arquivo pode ser aberto diretamente no navegador ou servido como site estático.

## Servir Localmente

```bash
python3 -m http.server 8000
```

Depois acesse:

```text
http://localhost:8000/
```

## Banco Com Docker

Há um exemplo de `docker-compose` em:

```text
docker/docker-compose.ufologia.yml
```

Defina a senha local antes de subir:

```bash
export UFOLOGIA_DB_PASSWORD="troque-esta-senha"
export UFOLOGIA_DB_PORT="5432"
```

Se seu Docker tiver o plugin Compose:

```bash
docker compose -f docker/docker-compose.ufologia.yml up -d
```

Os pacotes/imagens `.tar` e `.tar.gz` não são versionados porque são grandes e não são adequados para o GitHub.

## Deploy

O diretório `deploy/` contém exemplos de serviços `systemd` para publicar a pasta do projeto com `python3 -m http.server`.

Para um deploy real, prefira configurar variáveis de ambiente e credenciais fora do repositório.

## Segurança

Não versione:

- tokens de GitHub;
- IPs privados ou credenciais de servidor;
- arquivos `.env`;
- dumps de banco com dados sensíveis;
- imagens Docker exportadas (`.tar`, `.tar.gz`).

Use `.env.example` apenas com valores demonstrativos.

## Dados

Os dados dos casos não são consultados em tempo real pelo dashboard. O fluxo é:

1. O script lê o PostgreSQL.
2. O HTML é gerado com os dados embutidos.
3. O site serve o HTML estático.

Ao alterar o banco, rode novamente:

```bash
python3 scripts/app.py
```

## Licença

Defina uma licença antes de publicar ou reutilizar este projeto.
