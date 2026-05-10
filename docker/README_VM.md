# Banco Local

Este diretório contém um exemplo de `docker-compose` para subir um PostgreSQL local usado pelo gerador do mapa.

## Variáveis

Defina as variáveis antes de iniciar:

```bash
export UFOLOGIA_DB_PASSWORD="troque-esta-senha"
export UFOLOGIA_DB_PORT="5432"
```

## Subir

```bash
docker compose -f docker-compose.ufologia.yml up -d
```

## Validar

```bash
docker exec ufologia-db psql -U postgres -d ufologia -c "select count(*) from public.casos;"
```

## Observações

- Não versione dumps, imagens exportadas ou pacotes `.tar`/`.tar.gz`.
- Não publique senhas reais no repositório.
- Se usar um dump inicial, documente a origem e mantenha o arquivo fora do Git quando ele for grande ou sensível.
