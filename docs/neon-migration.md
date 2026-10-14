# Plano de migração PostgreSQL: Supabase para Neon

## Estado desta entrega

Somente preparação de código, testes sintéticos e documentação. Nenhuma conexão
real, exportação de dados, migration, concessão de privilégios, deploy, habilitação
de cadastros ou merge foi executado. O banco Supabase permanece intacto.
A migração não está concluída: conexão real, schema, dados e identidade exigem
etapas separadas autorizadas. As skills neon/neon-postgres instaladas no Windows
não estavam disponíveis no ambiente cloud; foi consultada documentação oficial.

Destino informado: projeto `biosaude-orcamento-automatizado`, branch `production`,
banco `neondb`, AWS US East 2. Esses nomes não permitem inferir hostname/credenciais.
Confirmar o destino no Console Neon ao copiar as URLs pooled/direct.

## Sequência por etapas, sem execução automática

1. Revisar e aprovar o PR. Preservar o Supabase, backups e configuração antiga em
   armazenamento seguro fora do checkout, sem imprimir/exportar segredos para logs.
   Inventariar dados existentes, extensão/schema, volumes, grants e políticas com
   acesso somente leitura autorizado. Não assumir que o banco antigo está vazio.
2. Configurar as duas URLs e o bundle CA conforme `database.md`. Verificar SELECT 1
   pela aplicação pooled e a revisão Alembic pela conexão direta, após autorização.
   Confirmar projeto/branch/banco em cada conexão e que o destino é novo/vazio.
3. Planejar usuário operacional com privilégios mínimos. `neondb_owner` é a role
   inicial informada para administração; não utilizá-la como conta operacional
   definitiva sem justificativa. As URLs podem usar roles distintas para aplicação
   e migrations. Não provisionar usuários, grants ou RLS automaticamente.
4. Obter autorização específica para criar a estrutura no Neon. **Somente então**,
   a partir da raiz e usando `BIOSAUDE_DATABASE_MIGRATION_URL` direta:

   ```powershell
   uv run --no-sync alembic upgrade head
   uv run --no-sync alembic current
   uv run --no-sync alembic check
   ```

   Esses comandos não foram executados nesta entrega. A cadeia existente é
   `2bfff13426c5` → `8c41e2f67b90`: cria companies, users, hospitals, products,
   quote_requests e quote_items, depois o índice de identidade. As revisões e
   operações são preservadas. Não aplicar a cadeia sobre tabelas existentes sem
   conciliação de schema/revisão. Não alterar operações aplicadas nem usar stamp
   para pular criação. Planejar locks e timeout de migrations para volumes grandes.
5. Projetar uma transferência de dados em tarefa autorizada independente: backup
   consistente, janela de escrita/quiescência, validação de contagens e integridade,
   preservação de UUIDs, company_id, identity_subject, perfis, FKs e vínculos de
   solicitação/itens; executar o transporte apenas após autorização. A criação de
   seis tabelas vazias não migra cadastros ou vínculos e não autoriza cutover.
6. Auditar a segurança real, testar negativos entre empresas e revisar grants
   antes de qualquer habilitação de catálogo. Manter `BIOSAUDE_CATALOG_ENABLED=false`.
7. Autorizar separadamente deploy/cutover e qualquer habilitação de cadastros,
   observando as duas URLs, contas de acesso e plano de reversão. Não apagar o
   banco antigo após teste de conexão nem como parte da migração inicial.

## Auditoria de segurança a realizar no destino

| Controle | Evidência exigida antes da operação |
| --- | --- |
| Roles | Papel administrativo separado; conta operacional sem privilégios administrativos/BYPASSRLS desnecessários |
| Grants | Privilégios mínimos de schema/tabelas/sequences; PUBLIC e roles externas revisados |
| Leitura/escrita | Operador acessa apenas operações autorizadas; leitor não grava; identidades desconhecidas recusadas |
| Isolamento | API filtra empresa derivada de users; seletores/IDs de outra empresa negados; acesso SQL direto também protegido |
| RLS | Verificar políticas, permissive/restrictive, ownership e bypass; não presumir cópia de políticas Supabase |
| Caminhos externos | Inventariar SQL direto, Data API e demais serviços habilitados no Neon; negar acesso amplo ao schema público |
| Transporte | TLS verify-full e CA pública adequada; grants de rede/porta, sem exposição de URLs/logs |
| Dados | Chaves e FKs preservadas, constraints/índices correspondentes e referências oficiais São Camilo mantidas |

O isolamento testado na API não comprova isolamento em acesso SQL externo.
A flag de habilitação é controle de implantação, não substitui essa auditoria.
Mudanças de segurança no banco exigem aprovação própria e testes no ambiente
adequado, nunca alterações silenciosas no Supabase ou Neon production.

## Identidade continua no Supabase

O provedor de dados passa a poder ser Neon; o provedor de identidade **ainda é
Supabase Auth**. Preservar `BIOSAUDE_SUPABASE_URL`, assinatura JWT/JWKS, issuer,
audience, expiração, resolução de vínculos em users e autorização por perfil.
Os identity_subject existentes devem manter correspondência com os usuários
Supabase após a transferência autorizada de dados. Não gerar usuários ou tokens
fictícios para substituir vínculos ausentes. A troca para provedor de identidade
independente será outro projeto/PR, com plano de continuidade das identidades.

## Reversão sem destruir bancos

Antes do cutover, manter cópia segura dos valores anteriores de URL operacional,
URL direta e override CA. Se a validação falhar, não habilitar o catálogo. Reverter
apenas a configuração autorizada e reiniciar o serviço somente quando autorizado.
O Alembic antigo também requer URL direta explícita; não reutiliza a pooled.
Não rodar downgrade, apagar tabelas ou remover o Neon/Supabase como rollback.

Se houver escritas no Neon após um cutover futuro, restaurar simplesmente a URL
pode perder/divergir dados: interromper a mudança e executar plano de reconciliação
aprovado. Preservar ambas as bases até validar integridade e continuidade.

## Testes e limites de evidência

`uv sync --locked`, seguido de `uv run --no-sync pytest -q`,
`uv run --no-sync ruff check .` e `uv run --no-sync ruff format --check .`.
Os testes de conexão usam URLs fictícias/engines lazy; seleção do Alembic usa
contexto mock e não executa DDL real. Os testes opcionais PostgreSQL usam apenas
banco local sintético descartável com TLS e guardas de hostname/database.
Não definir BIOSAUDE_TEST_DATABASE_URL com credenciais de Neon ou Supabase.

A seleção de CA para Windows é testada por simulação de ausência do bundle Linux;
esses testes não substituem o handshake no Windows ou no Neon real. O pooler Neon,
o channel binding e as permissões do projeto real precisam de validação posterior
somente leitura autorizada. Não declarar migração concluída a partir desses testes.
