# Arquitetura inicial

```text
backend/app/
  api/          HTTP: GET /health e /health/database
  core/         Settings e camada PostgreSQL/SQLAlchemy/psycopg
  domain/       Modelos Pydantic e interfaces sem implementação
frontend/
  app.py        Entrada Streamlit e navegação
  pages/        Oito módulos informativos
workers/        Reserva documentada, sem execução
tests/          API, configuração, domínio, UI e proteção de arquivos
scripts/        Instalação e execução a partir da raiz
docs/           Arquitetura e regras de negócio
```

FastAPI e Streamlit são processos separados. A UI atual não consulta a API nem
grava dados. `/health` indica apenas que o processo HTTP responde e identifica
o ambiente; não testa banco, credenciais nem prontidão de fluxos empresariais.

Python 3.12 é fixado em `.python-version` e limitado no manifesto. Dependências
diretas têm versões exatas, transitivas e hashes estão no `uv.lock`. O projeto
é instalado em modo editável por `uv`, permitindo imports consistentes nos
servidores, testes e comandos. Banco é opcional para desenvolver/testar; a conexão é configurável conforme `database.md`.

## Persistência e isolamento futuros

`Company` representa a empresa. Usuário, produto, hospital, solicitação e item
de orçamento carregam `company_id`. `TenantRepository[T]` exige esse escopo em
todas as operações. A camada de conexão, os seis modelos ORM e a revisão Alembic inicial são
preservados. Hospitais e produtos têm cadastros autenticados conforme
`auth-catalog.md`. O escopo vem do vínculo da identidade verificada no banco;
IDs fornecidos pelo cliente não autorizam acesso. Relações hospital/solicitação e
produto/item deverão ser validadas no mesmo escopo. Os testes negativos cobrem isolamento entre empresas na API de cadastros.
Proteção de acesso direto ao banco/PostgREST depende de grants e RLS existentes,
que não são criados nem alterados por esta entrega.

## Provedores futuros

`Settings` reserva opções para PostgreSQL/Supabase, SMTP Locaweb, OpenAI e
Twilio. Campos sensíveis usam `SecretStr`. PostgreSQL tem engine lazy e diagnóstico explícito; consultar `database.md`.
Supabase Auth tem verificação JWT/JWKS explícita. Os demais provedores
continuam sem clientes ou habilitação automática. Não implementar envio nesta tarefa. Os futuros adaptadores deverão
usar TLS, tratamento de falhas, timeouts e auditoria sem conteúdo confidencial.

A identificação da tabela São Camilo não define valores nem critérios financeiros.
A política de modelos PDF ainda depende dos documentos oficiais. Consultar
`business-rules.md` para requisitos antes de implementar cada fluxo.

## Limites de produção

Esta entrega prepara desenvolvimento local/cloud, não uma implantação SaaS.
Autenticação e cadastros estão implementados no backend; configuração externa
do provedor e auditoria de RLS/grants permanecem necessárias. Armazenamento
protegido, auditoria persistente, observabilidade e políticas de retenção exigem
etapas posteriores. Não expor
os serviços na Internet como produto operacional. Os scripts usam loopback.

## Camada operacional de autenticação e cadastros

`api/catalog.py` implementa rotas `/api/v1` de hospitais/produtos com contratos
validados em `api/catalog_schemas.py`. `core/auth.py` verifica JWTs assimétricos
do Supabase Auth e resolve o vínculo empresarial e perfil em `UserORM`.
Os seis modelos em `persistence` e a revisão Alembic existente são preservados.
Consultas e alterações são limitadas à empresa autorizada; não há CRUD de
usuários/empresas. Consulte `auth-catalog.md` para contratos, configuração,
perfis, bloqueio de duplicidades e limites de implantação.

A aplicação não cria políticas RLS ou grants no Supabase; o isolamento desta
camada não comprova a proteção de PostgREST ou acesso SQL externo. Essas
configurações existentes precisam de auditoria autorizada antes da implantação.
