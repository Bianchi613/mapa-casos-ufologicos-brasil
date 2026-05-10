# Mapa de Casos Ufológicos Brasileiros

![Mapa de Casos Ufológicos Brasileiros](assets/mapa-casos-ufologicos-brasil.png)

Este projeto publica um mapa HTML estático com casos ufológicos brasileiros. O site fica rodando em uma VM Oracle e o HTML é gerado a partir de um banco PostgreSQL local em Docker.

## Endereço do site

Site principal:

```text
http://mapaufologico.duckdns.org/
```

Endereço alternativo pelo IP:

```text
http://136.248.84.8/
```

O subdomínio grátis `mapaufologico.duckdns.org` aponta para o IP público da VM.

## Como o site funciona

O site publicado é estático. Ele serve estes arquivos da pasta do projeto:

```text
/home/ubuntu/Projeto/index.html
/home/ubuntu/Projeto/mapa_casos_brasileiros.html
/home/ubuntu/Projeto/vendor/
```

O arquivo `index.html` redireciona para `mapa_casos_brasileiros.html`.

O serviço web não consulta o banco em tempo real. Ele apenas entrega o HTML que já foi gerado.

## Serviço web

O site é servido pelo serviço systemd:

```text
mapa-casos.service
```

Ele roda:

```bash
/usr/bin/python3 -m http.server 80 --bind 0.0.0.0
```

Diretório servido:

```text
/home/ubuntu/Projeto
```

Ver status:

```bash
systemctl status mapa-casos.service
```

Reiniciar:

```bash
sudo systemctl restart mapa-casos.service
```

Ver se a porta 80 está respondendo localmente:

```bash
curl -I http://127.0.0.1/
```

Existe também um serviço alternativo na porta 8000:

```text
mapa-casos-8000.service
```

Ele serve o mesmo projeto em:

```text
http://mapaufologico.duckdns.org:8000/
```

## Banco de dados

O banco roda em Docker na própria VM.

Container:

```text
ufologia-db
```

Imagem:

```text
ufologia-postgres:2026-05-10
```

Banco:

```text
ufologia
```

Usuário:

```text
postgres
```

Senha:

```text
12345
```

Porta:

```text
127.0.0.1:5432
```

Importante: o banco está exposto somente para dentro da VM, porque a porta foi publicada em `127.0.0.1`. Ele não fica aberto publicamente na internet.

Ver containers:

```bash
docker ps
```

Ver logs do banco:

```bash
docker logs --tail 80 ufologia-db
```

Validar contagem de casos:

```bash
docker exec ufologia-db psql -U postgres -d ufologia -c "select count(*) from public.casos;"
```

Resultado esperado no dump atual:

```text
128
```

O container foi criado com restart automático:

```text
unless-stopped
```

Então ele deve voltar sozinho se a VM ou o Docker reiniciar.

## Gerador do HTML

O script que gera o mapa fica em:

```text
/home/ubuntu/Projeto/scripts/app.py
```

Ele lê o banco PostgreSQL local usando:

```text
postgresql+psycopg2://postgres:12345@localhost:5432/ufologia
```

No contexto da VM, `localhost` significa a própria VM. Portanto, o script lê o Postgres Docker que está rodando dentro dela.

O script busca dados em:

```text
public.casos
```

Principalmente a coluna:

```text
localizacao
```

Ele também usa o GeoJSON do IBGE para desenhar os estados do Brasil. Esse dado é salvo/cacheado em:

```text
/home/ubuntu/Projeto/output/brasil_ufs_ibge.geojson
```

Os casos vêm do banco. O IBGE fornece apenas o desenho das UFs.

## Atualizar o site depois de mudar o banco

Sempre que os dados do banco mudarem, gere o HTML novamente:

```bash
cd /home/ubuntu/Projeto
python3 scripts/app.py
```

O script substitui automaticamente:

```text
/home/ubuntu/Projeto/mapa_casos_brasileiros.html
```

Como o serviço web serve esse mesmo arquivo, o que está no ar é atualizado automaticamente. Não precisa reiniciar o `mapa-casos.service`.

Se o navegador mostrar a versão antiga, use:

```text
Ctrl + F5
```

ou abra em uma aba anônima.

Confirmar data e tamanho do HTML atualizado:

```bash
ls -lh mapa_casos_brasileiros.html
```

Testar o HTML diretamente:

```bash
curl -I http://mapaufologico.duckdns.org/mapa_casos_brasileiros.html
```

## Substituição do HTML

Quando `python3 scripts/app.py` roda com sucesso, ele sobrescreve o arquivo antigo.

O servidor `python3 -m http.server` não guarda uma cópia antiga do HTML na memória. Cada nova requisição lê o arquivo atual do disco.

Portanto:

1. O banco é atualizado.
2. `python3 scripts/app.py` é executado.
3. `mapa_casos_brasileiros.html` é substituído.
4. O site passa a servir o HTML novo.

## Pacote Docker original

Os arquivos usados para subir o banco estão em:

```text
/home/ubuntu/Projeto/docker/
```

Arquivos principais:

```text
docker-compose.ufologia.yml
ufologia-postgres_2026-05-10.tar
ufologia-vm-package_2026-05-10.tar.gz
README_VM.md
```

Nesta VM, o container foi iniciado manualmente com `docker run`, porque o comando `docker compose` não estava disponível.

Comando equivalente usado:

```bash
docker volume create ufologia_pgdata

docker run -d \
  --name ufologia-db \
  --restart unless-stopped \
  -e POSTGRES_DB=ufologia \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=12345 \
  -p 127.0.0.1:5432:5432 \
  -v ufologia_pgdata:/var/lib/postgresql/data \
  ufologia-postgres:2026-05-10
```

## Portas

Portas usadas:

```text
80    site público
8000  site alternativo
5432  PostgreSQL local, preso em 127.0.0.1
```

A porta `80` precisa estar liberada na Oracle Cloud para o site abrir sem `:8000`.

## Observações sobre custo

Esta configuração não cria domínio pago, load balancer, IP novo, storage adicional da Oracle ou outro recurso pago.

Ela usa:

```text
VM existente
Docker local
DuckDNS gratuito
sslip.io como alternativa gratuita
```

Ainda assim, tráfego público no site consome rede da VM. Para uso pequeno, normalmente é tranquilo, mas tráfego alto pode bater limites do plano da Oracle.
