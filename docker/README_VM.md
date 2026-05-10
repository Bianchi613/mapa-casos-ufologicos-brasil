# Deploy do banco ufologia na VM

Arquivo do pacote:

```text
ufologia-vm-package_2026-05-10.tar.gz
```

## 1. Enviar para a VM

Na maquina local:

```powershell
scp docker/ufologia-vm-package_2026-05-10.tar.gz usuario@IP_DA_VM:/opt/ufologia/
```

## 2. Subir na VM

Na VM:

```bash
cd /opt/ufologia
tar -xzf ufologia-vm-package_2026-05-10.tar.gz
docker load -i ufologia-postgres_2026-05-10.tar
docker compose -f docker-compose.ufologia.yml up -d
```

## 3. Validar

```bash
docker exec ufologia-db psql -U postgres -d ufologia -c "select count(*) from public.casos;"
```

O resultado esperado para `public.casos` no dump atual e `128`.

Credenciais padrao:

- database: `ufologia`
- usuario: `postgres`
- senha: `12345`
- porta publicada: `5432`

Para usar outra senha ou porta, exporte as variaveis antes do `docker compose up`:

```bash
export UFOLOGIA_DB_PASSWORD="sua-senha"
export UFOLOGIA_DB_PORT="5433"
docker compose -f docker-compose.ufologia.yml up -d
```

Observacao: o dump so e restaurado quando o volume do Postgres esta vazio. Para recriar tudo do zero:

```bash
docker compose -f docker-compose.ufologia.yml down -v
docker compose -f docker-compose.ufologia.yml up -d
```
