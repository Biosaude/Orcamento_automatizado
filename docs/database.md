# Conexão PostgreSQL / Neon

SQLAlchemy 2 com psycopg 3 síncrono, sem SDK Neon. O engine da aplicação é criado
no lifespan FastAPI, sem conexão na importação/inicialização, e liberado no
encerramento. Não executa DDL, migrations ou commits automáticos.

## Duas URLs independentes

| Variável | Uso |
| --- | --- |
| `BIOSAUDE_DATABASE_URL` | Aplicação: copiar a URL **pooled** no Console Neon (`-pooler` no host) |
| `BIOSAUDE_DATABASE_MIGRATION_URL` | Alembic: copiar a URL **direct**, sem `-pooler` |

Ambas usam `SecretStr`, ficam no `.env` local ignorado ou em injeção segura de
variáveis do processo e não são exibidas em endpoints/logs. Variáveis do processo
prevalecem sobre `.env`. Não inserir valores em chat, argumentos de comandos,
commits ou documentos. Senhas com caracteres reservados exigem percent-encoding.
Aceitar `postgresql://` ou `postgresql+psycopg://`, com usuário, senha, host e banco.
Não converter host pooled para direct por manipulação de texto: copiar as duas
URLs do Console e confirmar projeto, branch e database separadamente.

URL operacional vazia mantém o banco da aplicação desabilitado, mesmo se houver
URL administrativa. Alembic exige sua própria URL e **não faz fallback** para a
operacional; rejeita host Neon `-pooler` e o pooler Supabase conhecido. Usa
`NullPool` e descarta a conexão após o comando. Não conecta ao banco no startup.
A conexão operacional genérica PostgreSQL/direta continua compatível para testes
locais e retorno controlado ao banco antigo; Neon pooled é a escolha operacional.

## TLS e parâmetros da URL

Todas as conexões usam `sslmode=verify-full`, validando cadeia de confiança,
validade do certificado e hostname. Na query da URL são aceitos somente:

- `sslmode=require`: formato comum do Console; promovido a **verify-full**, nunca
  usado para reduzir a validação;
- `sslmode=verify-full`;
- `channel_binding=require`: preservado e enviado ao psycopg/libpq.

Parâmetros repetidos, vazios, fragmentos e quaisquer parâmetros adicionais são
rejeitados. `disable`, `prefer`, `allow`, `verify-ca`, caminhos de certificados,
`hostaddr`, `options` e overrides de timeouts na URL são recusados. Configurar os
controles por variáveis específicas. A URL passada ao driver tem a query removida;
as opções aceitas são reconstruídas em `connect_args` com TLS sempre verificado.

`BIOSAUDE_DATABASE_SSL_ROOT_CERT` aceita caminho de bundle CA legível. Vazio usa
`/etc/ssl/certs/ca-certificates.crt` se disponível, ou o bundle público de **certifi**
(portável para Windows). Certifi já existia no lockfile como dependência transitiva;
agora é direta e fixada para garantir essa função de confiança sem depender da UI.
Não se usa o repositório nativo de certificados do Windows implicitamente.

Neon utiliza uma cadeia pública com ISRG Root X1/Let's Encrypt conforme a documentação
oficial. Não copiar uma CA específica do Supabase para Neon. Remover esse override
antigo para usar o bundle público, ou fornecer bundle oficial corporativo aprovado.
Não baixar certificados privados nem desabilitar verificação para contornar erros.
Um arquivo existente não comprova confiança: o handshake do driver a verifica.

## Pool, sessões e timeouts

| Variável | Padrão | Limites |
| --- | --- | --- |
| `BIOSAUDE_DATABASE_CONNECT_TIMEOUT` | 5 segundos | 1–30 |
| `BIOSAUDE_DATABASE_STATEMENT_TIMEOUT_MS` | 5000 ms | 1–30000 |
| `BIOSAUDE_DATABASE_MIGRATION_STATEMENT_TIMEOUT_MS` | 60000 ms | 1–300000 |
| `BIOSAUDE_DATABASE_POOL_SIZE` | 5 | 1–20 por processo |
| `BIOSAUDE_DATABASE_MAX_OVERFLOW` | 0 | 0–20 por processo |
| `BIOSAUDE_DATABASE_POOL_TIMEOUT` | 5 segundos | 1–30 |

O pool SQLAlchemy continua limitado e usa `pool_pre_ping`, sem echo SQL e com
parâmetros ocultos. Considerar número de workers e limites do compute Neon.
`prepare_threshold=None` desabilita prepared statements automáticos no psycopg.
O pooler Neon usa transaction pooling: não depender de SET de sessão, tabelas
temporárias persistentes, LISTEN ou locks de sessão. Para o pooler, cada transação
recebe `SET LOCAL statement_timeout`; a configuração não vaza para transações de
outros clientes. Conexões diretas mantêm timeout de startup via `options`.
Migrações têm timeout independente; índices grandes exigem planejamento antes de
ajustar o limite, sem retries automáticos de operações de escrita.

`get_session` continua fechando a sessão e descartando transações não confirmadas,
inclusive em falhas; não faz commit implícito. Autorização e commits dos cadastros
são preservados em [auth-catalog.md](auth-catalog.md). Neon não recebe RLS/grants
Supabase automaticamente. Manter `BIOSAUDE_CATALOG_ENABLED=false` até auditoria.
`BIOSAUDE_SUPABASE_URL` continua indicando **Supabase Auth**, independentemente da
URL PostgreSQL. Não é hostname Neon. Nenhuma chave service_role é necessária.

Na nuvem, o hostname/porta PostgreSQL precisa de rota TCP autorizada; allowlist
HTTPS não comprova esse acesso. Secrets que são placeholders apenas em proxy
HTTPS não fornecem senha bruta ao psycopg. Acesso ao JWKS Supabase usa HTTPS e é
separado do acesso PostgreSQL. Não copiar placeholders para arquivos locais.

## Diagnóstico e procedimento Windows

`/health` permanece público e indica só o processo HTTP. `/health/database` exige
`X-Database-Health-Token` igual a `BIOSAUDE_DATABASE_HEALTH_TOKEN` (`SecretStr`),
comparado em tempo constante. Sem token configurado/válido retorna 403 antes de
consultar o banco. Após autorização, executa somente `SELECT 1`: 200/`ok` quando
conectado, 503/`unavailable` sem banco ou com falha. Não comprova RLS/autorização.
Não passar o token em URL, logs ou argumentos de shell. Usar HTTPS fora do loopback.

Preparação em PowerShell, sem substituir configuração existente:

```powershell
Set-Location C:\Projetos_Biosaude\Orcamento_automatizado
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Editar `.env` por editor local seguro: inserir as duas URLs do Console, deixar o
catálogo desabilitado e revisar o override de CA. Não compartilhar esse arquivo.
Para obter apenas o caminho público de CA (não imprime configuração ou segredos):

```powershell
uv run --no-sync python -c "import certifi; print(certifi.where())"
```

Após configuração e autorização para acesso **somente leitura**, testar o pooled:

```powershell
uv run --no-sync python -c "from backend.app.core.config import Settings; from backend.app.core.database import Database; db=Database(Settings()); ok=db.probe(); db.dispose(); print('Disponivel' if ok else 'Indisponivel'); raise SystemExit(0 if ok else 1)"
```

O probe é SELECT 1, não grava dados. Não executar testes automatizados contra as
URLs reais. Para consultar a revisão atual pela URL **direta**, somente com acesso
autorizado ao banco alvo: `uv run --no-sync alembic current`. Um Neon novo pode
não ter revisão/tabelas. Não usar `stamp head` para fingir que a estrutura existe.
Procedimento de criação autorizada, auditoria, cutover e rollback em
[neon-migration.md](neon-migration.md). Nenhum comando de migração é automático.

Erros de configuração são genéricos, sem URL/senha. Investigar separadamente:
URL direta ausente/pooler no Alembic; CA antiga/ausente; hostname não correspondente
ao certificado; porta/rota bloqueada; cold start (ajustar connect timeout dentro
dos limites); falta de privilégios; revisão ainda não aplicada. Falha de channel
binding exige corrigir driver/configuração; não enfraquecer TLS nem remover a
exigência silenciosamente. Não registrar a exceção original do driver com segredos.

Referências oficiais consultadas: [TLS Neon](https://neon.com/docs/connect/connect-securely)
e [pooling Neon](https://neon.com/docs/connect/connection-pooling), também disponíveis
no [repositório oficial](https://github.com/neondatabase/website/tree/main/content/docs/connect).
