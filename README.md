# Biosaúde OPME Automation

Base do MVP empresarial `biosaude-opme-automation`, preparada no repositório
`Biosaude/Orcamento_automatizado`. Python 3.12, FastAPI e Streamlit. A entrega
contém API de saúde, navegação dos oito módulos, contratos de domínio, conexão
PostgreSQL compatível com Neon e Supabase e cadastros autenticados de hospitais/produtos por empresa.
Não há cálculos financeiros, aprovação ou envio de orçamentos.

Preparação Neon pooled/direct e Windows em [conexão PostgreSQL](docs/database.md)
e [plano de migração](docs/neon-migration.md). Nenhuma migração ou transferência
de dados é automática. Supabase Auth continua como provedor de identidade.

Configuração de Supabase Auth, perfis e rotas `/api/v1` em
[autenticação e cadastros](docs/auth-catalog.md). Os vínculos empresariais devem
ser provisionados por administrador autorizado; sem configuração e vínculo o
acesso operacional é negado. Os cadastros são desabilitados por padrão;
habilitar `BIOSAUDE_CATALOG_ENABLED=true` somente após auditar RLS/grants e
acessos diretos ao banco. A UI continua informativa, sem integração com CRUD.

## Instalação

Requisitos: Python 3.12, Git e [uv](https://docs.astral.sh/uv/getting-started/installation/)
(validado com uv 0.12.23).
Executar da raiz do checkout. O `uv.lock` fixa dependências transitivas e hashes;
usar instalação bloqueada e manter a verificação TLS ativa.

Em máquinas cloud com diretório pessoal somente leitura, definir um cache gravável
antes dos comandos diretos de `uv` (os scripts já fazem isso automaticamente):

```bash
export UV_CACHE_DIR="${TMPDIR:-/tmp}/biosaude-uv-cache"
```

```bash
bash scripts/setup.sh
# Opcional: criar configuração local somente se .env ainda não existir.
test -e .env || cp .env.example .env
```

O `.env` é opcional. Seus exemplos são fictícios e não habilitam integrações.
Variáveis do processo prevalecem sobre `.env`. Não substituir segredos existentes
nem colocar dados reais no checkout. As opções reconhecidas estão em
`.env.example` e `backend/app/core/config.py`. O prefixo é `BIOSAUDE_`.

## Execução

Em dois terminais separados, a partir da raiz:

```bash
bash scripts/run_backend.sh
```

```bash
bash scripts/run_frontend.sh
```

Equivalentes:

```bash
uv run --frozen uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
uv run --frozen streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

A API usa porta 8000 e o Streamlit 8501. Interromper com Ctrl+C. Verificação local:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8501/_stcore/health
```

Resposta padrão da API:

```json
{"status":"ok","service":"biosaude-opme-automation","version":"0.1.0","environment":"development","external_integrations":"disabled"}
```

`/health` indica saúde do processo, sem alegar prontidão de banco ou operação.
`/health/database` exige `X-Database-Health-Token`, comparado ao segredo
`BIOSAUDE_DATABASE_HEALTH_TOKEN`: sem configuração ou autorização válida retorna
403, sem consultar o banco. Após autorização, executa apenas `SELECT 1`: 200
quando conectado, 503 quando desabilitado ou indisponível. Configuração segura
em [docs/database.md](docs/database.md).
O campo legado `external_integrations` refere-se às integrações operacionais
ainda desabilitadas; a disponibilidade PostgreSQL tem diagnóstico separado.
Documentação OpenAPI em `/docs`. Em ambientes cloud, requisições locais servem
para validação interna; a disponibilidade da UI ao usuário depende da plataforma.

## Testes e qualidade

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

Os testes verificam API, mascaramento de configurações sensíveis, escopo obrigatório
de empresa, restrições dos modelos, padrões de hospital, navegação efetiva em todas
as páginas do Streamlit e exclusão de caminhos confidenciais pelo Git. Não requerem
banco, chave de API nem serviços externos. Dados sintéticos existem somente nos testes.

## Estrutura e limites

- `backend/app`: rotas, configuração, modelos e interfaces.
- `frontend`: Dashboard, Solicitações, Simulador, Produtos, Estoque, Hospitais,
  Histórico e Configurações, com avisos explícitos de módulos ainda indisponíveis.
- `workers`: espaço reservado, sem jobs ou envio.
- `scripts`, `tests`, `docs`: execução, validação e decisões arquiteturais.

Ler [arquitetura](docs/architecture.md), [regras de negócio](docs/business-rules.md)
e [orientações de desenvolvimento](AGENTS.md).

A IA nunca aprovará ou enviará orçamentos. O motor financeiro dependerá do
simulador oficial validado, sem fórmulas inventadas. Similares exigirão validação
humana; São Camilo terá exceção configurável e os outros hospitais usarão o PDF
VS|OPME. O envio futuro responderá ao e-mail original. `company_id` prepara
isolamento futuro, mas autenticação e políticas de banco ainda não existem.

Segredos, documentos hospitalares, planilhas e pacientes devem ficar fora do
checkout. `.gitignore` protege padrões comuns, mas não detecta todo conteúdo
sensível nem remove arquivos já rastreados: revisar o diff antes de cada commit.

## Pendências deliberadas

Receber o simulador e modelos oficiais; auditar RLS e grants existentes no Supabase;
evoluir persistência de solicitações, auditoria e observabilidade; criar adaptadores
externos em tarefas autorizadas separadas. Não usar esta estrutura para operação
real ou armazenamento de dados de pacientes.
