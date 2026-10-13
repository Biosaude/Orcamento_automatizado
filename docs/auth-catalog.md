# Autenticação e cadastros por empresa

As rotas operacionais usam `/api/v1` e ficam desabilitadas por padrão.
Apenas definir `BIOSAUDE_SUPABASE_URL` não habilita os cadastros.
`BIOSAUDE_CATALOG_ENABLED=true` deve ser configurado somente após auditoria
autorizada da proteção de acesso direto ao banco (RLS/grants/PostgREST).
Sem essa habilitação, as rotas não são registradas nem aparecem no OpenAPI;
retornam 404. Essa flag é um controle de implantação, não cria políticas nem
comprova por si só que a auditoria foi feita. `/health` e o diagnóstico protegido de
banco mantêm o contrato anterior. Os seis modelos ORM, a revisão Alembic existente
e a configuração PostgreSQL/TLS não são alterados por este módulo.

## Autenticação externa

Configurar `BIOSAUDE_SUPABASE_URL` com a origem HTTPS do projeto Supabase confiável,
sem path, query ou credenciais. O backend deriva o issuer `<origem>/auth/v1` e
busca exclusivamente `<issuer>/.well-known/jwks.json`, com TLS verificado,
timeout de 5 segundos e cache JWKS de 300 segundos. Nunca escolhe URLs a partir
de claims ou headers do token. Não requer chave `service_role`, segredo JWT ou
certificado privado. Liberar esse hostname HTTPS na política de rede.

Configurar o Supabase Auth com chave de assinatura assimétrica ES256 ou RS256.
Tokens legados HS256 e tokens anônimos/service_role são rejeitados. O cliente deve
fazer login com o fluxo oficial Supabase Auth (por exemplo, PKCE), incluindo
redirects HTTPS autorizados pelo provedor, e enviar o access token em
`Authorization: Bearer ...`. Não há login fictício, armazenamento de senhas,
endpoint de emissão de tokens, signup automático ou acesso administrativo sem
identidade verificada. Refresh/logout ficam a cargo do provedor e cliente.

O backend verifica assinatura, algoritmo permitido, issuer, audience
`authenticated`, expiração, emissão, eventual `nbf`, subject UUID e role de acesso
`authenticated`. Não confundir essa role do provedor com os perfis empresariais.
Ausência/invalidade do token retorna 401; provedor/configuração indisponível retorna
503. Tokens e erros sensíveis não são retornados. Não registrar Authorization.
Revogação de sessões no provedor não invalida imediatamente JWTs já emitidos:
usar vida curta de access token e remover o vínculo local para bloquear o usuário.

## Autorização empresarial

Antes da operação, consultar `users.identity_subject` usando o subject autenticado,
vinculado a `companies.active = true`. O perfil e a empresa vêm do banco, nunca
de `user_metadata`, `app_metadata` ou `company_id` enviado no corpo. Não são
criadas empresas ou identidades automaticamente. Um administrador autorizado
precisa provisionar previamente os vínculos no banco por procedimento separado,
com o UUID do usuário Supabase em `identity_subject` e um perfil reconhecido.
Esta entrega não executa esse provisionamento nem altera dados de produção.

Se houver um único vínculo ativo, ele é selecionado. Para usuários com múltiplos
vínculos, enviar `X-Company-ID` como seletor: o backend verifica novamente o
vínculo entre aquele subject e a empresa. Selecionar empresa de outro usuário ou
omitir o seletor em caso ambíguo retorna 403. Sem vínculo, empresa inativa ou
perfil desconhecido, o acesso também é negado.

| Perfil armazenado em `users.role` | Consultar/listar | Cadastrar/atualizar |
| --- | --- | --- |
| `administrator` | Sim | Sim |
| `operator` | Sim | Sim |
| `reviewer` | Sim | Não |

Todos os selects de cadastro incluem o escopo empresarial. Creates atribuem a
empresa no servidor. Updates consultam o registro pelo par empresa/id antes de
alterar campos. Um ID inexistente ou de outra empresa retorna o mesmo 404.
O corpo não aceita `company_id`, `id` ou campos extras. Não há exclusão nem rotas
de administração de empresas, vínculos ou permissões.

## Endpoints

| Método e caminho | Comportamento |
| --- | --- |
| `GET /api/v1/auth/me` | ID local, empresa autorizada e perfil |
| `POST /api/v1/hospitals` | Cadastro, 201 |
| `GET /api/v1/hospitals` | Lista da empresa |
| `GET /api/v1/hospitals/{id}` | Consulta da empresa |
| `PUT /api/v1/hospitals/{id}` | Substituição dos campos editáveis |
| `POST /api/v1/products` | Cadastro, 201 |
| `GET /api/v1/products` | Lista da empresa |
| `GET /api/v1/products/{id}` | Consulta da empresa |
| `PUT /api/v1/products/{id}` | Substituição dos campos editáveis |

Listas têm `limit` (1–100, padrão 50) e `offset` (0–100000, padrão 0), ordenadas
por ID. Produtos exigem code (até 100) e name (até 500), manufacturer opcional
(até 255). Hospitais exigem name (até 255), quote_template reconhecido e
identificador oficial de tabela (até 255) quando o modelo for São Camilo.
A validação desse identificador não comprova conteúdo ou existência da tabela;
a validação oficial do fluxo financeiro permanece fora deste módulo.

Strings são aparadas e vazias rejeitadas. Nomes de hospitais e códigos de produtos
são comparados sem distinção de caixa dentro da empresa; duplicidades retornam
409. PUT exige os campos obrigatórios; campos opcionais omitidos voltam ao padrão.
Entradas inválidas retornam 422; perfil sem permissão, 403. Erros de banco são
tratados sem retornar SQL, credenciais ou detalhes internos.

Cada escrita bloqueia a linha da empresa (`SELECT ... FOR UPDATE`) na transação
antes de conferir duplicidades e gravar. Isso serializa escritas deste módulo por
empresa, sem migrations ou locks globais. A constraint de código do produto é
preservada. Como o schema de hospitais não tem UNIQUE por nome, escritores externos
que não adotem esse protocolo ainda podem criar duplicidades; uma constraint
adicional exigirá uma tarefa de schema separada. O isolamento esperado do
PostgreSQL é READ COMMITTED. Falhas fazem rollback; commits são explícitos somente
nas operações autorizadas. O pool e TLS existentes são reutilizados.

## Limites e configuração de produção

Este módulo aplica autorização e escopo nos comandos SQL da API; não cria nem
altera RLS, grants ou políticas Supabase. Antes de disponibilizar dados reais,
auditar os grants e RLS existentes: as tabelas não podem ficar acessíveis
irrestritamente por PostgREST com chaves anon/authenticated ou SQL direto.
Usar uma conta PostgreSQL exclusiva do backend com permissões mínimas, nunca
chave service_role para autenticar usuários. A verificação desses controles no
Supabase exige acesso autorizado e é independente dos testes locais.

HTTPS no acesso à API, configurações de redirects/login, proteção de logs,
rate limiting no gateway e observabilidade sem dados sensíveis são responsabilidades
de implantação. A UI atual não foi conectada a estes cadastros. E-mail, IA,
WhatsApp, PDF e operações financeiras não estão implementados.

## Validação reproduzível

`uv sync --locked` e `uv run --frozen pytest` executam os testes originais e os novos.
Os testes novos verificam JWTs assinados com chave de teste e resposta JWKS
controlada, sem substituir as dependências de autenticação/autorização ou sessão.
Por padrão usam SQLite em memória com dados sintéticos; os dois testes de
concorrência PostgreSQL ficam explicitamente skipped.

Para validar PostgreSQL real, usar apenas instância descartável local, banco
`biosaude_synthetic_tests`, host localhost/127.0.0.1 e certificado de teste com
SAN válido. Configurar `BIOSAUDE_TEST_DATABASE_URL` e `BIOSAUDE_TEST_DATABASE_CA`
apenas no processo de testes. A fixture recusa hosts/bancos diferentes e cria
quatro tabelas de cadastro somente nesse banco sintético. Nunca apontar esses
valores para Supabase ou produção. Com essas variáveis, toda a suíte usa o driver,
pool e TLS verify-full existentes nas novas operações, incluindo concorrência.
Eliminar a instância descartável após os testes.

Não executar migrations como parte do startup ou dos testes. `uv run alembic check`
requer acesso ao banco alvo previamente autorizado; não é evidência produzida por
SQLite ou por schema sintético criado nos testes. Nenhuma migration foi executada
por este módulo.

## Índice de autenticação

A revisão aditiva `8c41e2f67b90` prepara um índice não único em
`users.identity_subject`, compatível com a consulta sem seletor de empresa.
Não modifica colunas, dados ou constraints, nem reescreve os comandos da revisão
`2bfff13426c5`. A aplicação dessa nova revisão no Supabase é uma operação
separada, que requer autorização e planejamento de bloqueios em tabelas grandes.
O startup não aplica migrations. O índice é declarado também na metadata ORM
para manter o contrato com o Alembic.
