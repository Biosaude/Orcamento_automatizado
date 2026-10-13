# Conexão PostgreSQL / Supabase — Tarefa 2.1

SQLAlchemy 2 com psycopg 3 síncrono. O engine é criado no lifespan FastAPI, sem
conexão na importação/inicialização, e seu pool é liberado no encerramento.
`/health` permanece público e independente do banco. `/health/database` exige
o header `X-Database-Health-Token` com o segredo configurado em
`BIOSAUDE_DATABASE_HEALTH_TOKEN` (`SecretStr`). Sem token configurado, ausente ou
inválido, retorna 403 antes de qualquer consulta. A comparação usa tempo constante;
headers de proxy ou endereço loopback não substituem autorização.
Após autorização, sem URL, `/health/database` retorna 503
com `{"status":"unavailable"}`. Com conexão válida, o diagnóstico executa somente
`SELECT 1`, fecha a conexão e retorna 200 com `{"status":"ok"}`. Falhas retornam
resposta genérica, sem URL, senha ou detalhes do driver.

Injetar o token de diagnóstico por configuração segura, usar valor aleatório
forte e distinto das credenciais do banco, e transportar somente sobre HTTPS
fora do loopback. Não colocá-lo em URLs ou logs; restringir seu uso ao monitoramento
interno. O exemplo deixa esse token vazio e não habilita o diagnóstico.

## Configuração segura

Obter a URI PostgreSQL em **Connect** no projeto Supabase e configurar
`BIOSAUDE_DATABASE_URL` por injeção segura de variáveis do processo ou `.env`
local ignorado. Nunca colocar credenciais em chat, commits, argumentos de shell
ou logs. Variáveis do processo prevalecem sobre `.env`. Aplicar percent-encoding
na senha quando houver caracteres reservados. Formatos aceitos: `postgresql://`
e `postgresql+psycopg://`, com usuário, senha, host e banco. Parâmetros na query
da URI são rejeitados; TLS e timeouts são controlados exclusivamente pela camada.

Escolher conexão direta se a rede suportar o endereço do projeto, ou Supavisor
session pooler para redes IPv4. Transaction pooler exige avaliar limitações de
sessão; prepared statements do psycopg estão desabilitados para compatibilidade.
Usar host, usuário e porta fornecidos pelo Supabase, sem inferi-los da URL HTTP.
`BIOSAUDE_SUPABASE_URL` e `service_role` não autenticam PostgreSQL e não são
necessários. A chave privilegiada não é sugerida no `.env.example`; o campo
`supabase_service_role_key` em `Settings` permanece por compatibilidade, sem uso
pela conexão. Preferir usuário com permissões mínimas; esta camada não fornece
isolamento RLS nem autenticação empresarial.

TLS obrigatório: `sslmode=verify-full` verifica cadeia de confiança e hostname.
`BIOSAUDE_DATABASE_SSL_ROOT_CERT` aponta para bundle CA legível; padrão Linux:
`/etc/ssl/certs/ca-certificates.crt`. Se o projeto exigir CA específica, obter o
certificado por fonte oficial Supabase e apontar para arquivo fora do checkout.
Em outros sistemas ajustar esse caminho. Não desabilitar a verificação para
corrigir falhas; não usar `require`, `prefer` ou `disable` como atalho.

| Variável | Padrão | Limites |
| --- | --- | --- |
| `BIOSAUDE_DATABASE_CONNECT_TIMEOUT` | 5 segundos | 1–30 |
| `BIOSAUDE_DATABASE_STATEMENT_TIMEOUT_MS` | 5000 ms | 1–30000 |
| `BIOSAUDE_DATABASE_POOL_SIZE` | 5 | 1–20 por processo |
| `BIOSAUDE_DATABASE_MAX_OVERFLOW` | 0 | 0–20 por processo |
| `BIOSAUDE_DATABASE_POOL_TIMEOUT` | 5 segundos | 1–30 |

Pool com `pool_pre_ping`, sem echo SQL e com parâmetros ocultos. Dimensionar
conexões considerando o número de workers. Na nuvem, o host e a porta PostgreSQL
precisam de rota TCP suportada; allowlist HTTPS sozinha não comprova esse acesso.
Segredos substituídos somente pelo proxy HTTPS não fornecem senha bruta ao
psycopg: usar injeção segura compatível com PostgreSQL, sem copiar placeholders.

## Sessões e validação

`backend.app.core.database.get_session` está disponível como dependência FastAPI
para futuras rotas autorizadas. Cada requisição tem sua sessão, fechada inclusive
em falhas; o fechamento descarta transações não confirmadas. Não há commit
implícito. Rotas futuras precisarão autorizar operações e tratar exceções sem
registrar informações sensíveis. Nenhuma rota CRUD foi criada.

Da raiz, executar `bash scripts/setup.sh`, os comandos de qualidade do README
e `bash scripts/run_backend.sh`. Uma requisição autorizada a `/health/database`
abre conexão apenas quando solicitada. Não executa DDL, migrations ou gravações,
nem comprova RLS/autorização. Não expor esse diagnóstico publicamente sem proteção.

Testes usam dados sintéticos, mocks para sucesso/falhas e driver real contra porta
loopback inacessível; não requerem banco remoto. O sucesso de conexão ao Supabase
real exige validação separada após configuração segura. Não há tabelas, models
ORM, migrations, políticas RLS ou usuários criados nesta tarefa.
