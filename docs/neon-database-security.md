# Segurança PostgreSQL: implantação manual revisável

## Escopo e estado

Branch/PR prepara separação administrativa/operacional, grants e RLS. Nenhum
comando deste procedimento foi executado no Neon ou Supabase; nenhuma senha ou
`.env` real foi alterado. Somente PostgreSQL local descartável com dados sintéticos
foi modificado nos testes. Seis modelos, índices, FKs, revisões Alembic e TLS
permanecem preservados. Supabase Auth continua verificando JWT/JWKS.

`BIOSAUDE_CATALOG_ENABLED=false` permanece padrão. O script SQL não habilita a API
nem é executado por startup/Alembic. Sua aplicação no Neon **requer aprovação própria**.

## Contrato de acesso

| Recurso | `biosaude_app` |
| --- | --- |
| Banco conectado | CONNECT; sem CREATE/TEMP |
| Schema public | USAGE; sem CREATE |
| companies/users | SELECT protegido por identidade; sem escrita |
| hospitals/products | SELECT, INSERT em campos definidos e UPDATE só campos editáveis |
| Identificadores/empresa | Sem UPDATE em id/company_id |
| quote_requests/quote_items | Sem privilégios e sem policies (deny all) |
| alembic_version | Sem acesso; reservado ao administrador |
| Sequences | Nenhum grant: PKs são UUIDs gerados no backend |
| Administração | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS, NOINHERIT |
| Memberships | App não pertence a outras roles; não pode SET ROLE administrativo |
| Objetos | App não pode ser proprietária de objetos; não tem GRANT OPTION |

A conta administrativa continua exclusivamente em `BIOSAUDE_DATABASE_MIGRATION_URL`
(direct). A aplicação deve usar `biosaude_app` em `BIOSAUDE_DATABASE_URL` (pooled).
`neondb_owner` não deve ser a conta operacional após a implantação aprovada.
SQLAlchemy não deduz privilégios pelo username da URL: verificar current_user e
os atributos/grants efetivos com o script de leitura, inclusive em pools reais.

## Pré-requisitos e backup

1. Confirmar no Console: projeto Biosaúde, branch `production`, database `neondb`,
   conexão **direta**, revisão `8c41e2f67b90` e as seis tabelas mais alembic_version.
   Verificar aprovações e janela de manutenção. Suspender escritores/integrações
   conforme procedimento autorizado; manter catálogo desabilitado.
2. Inventariar consumidores do banco e direitos via PUBLIC, memberships, ownership,
   schemas, functions SECURITY DEFINER, sequences, policies e defaults de cada role
   criadora. ACLs e RLS não são universais entre ambientes.
3. Obter backup consistente e testar restauração em ambiente isolado. Exemplo de
   comandos **a executar manualmente somente após autorização**, com psql/libpq
   service `biosaude_admin` configurado fora do checkout usando TLS verify-full:

   ```powershell
   pg_dump --dbname="service=biosaude_admin" --format=custom --file="C:\Biosaude_Secure\Backups\before-security.backup"
   pg_dump --dbname="service=biosaude_admin" --schema-only --create --file="C:\Biosaude_Secure\Backups\before-security-schema.sql"
   pg_dumpall --dbname="service=biosaude_admin" --database=neondb --roles-only --no-role-passwords --file="C:\Biosaude_Secure\Backups\before-security-roles.sql"
   ```

   Credenciais devem vir de configuração libpq/gerenciador seguro ou prompt, sem
   URL/senha em argumentos, histórico ou logs. Proteger serviço, pgpass e backups
   por ACL do sistema; os backups podem conter dados sensíveis e metadados de roles.
   Não versionar, colar ou restaurar esses arquivos cegamente: os dumps têm DDL.
   Se o Neon limitar pg_dumpall/catálogos, usar inventário autorizado equivalente
   e suporte/backup do provedor, sem buscar senha/hash no catálogo. Após FORCE RLS, um owner sem BYPASSRLS pode não conseguir fazer pg_dump completo;
   validar também a continuidade dos backups administrativos/provedor. Não usar
   --enable-row-security como atalho que pode gerar backup parcial. A operação
   aborta se não houver snapshot de ACLs/defaults/policies suficiente para reversão.
4. Testar previamente este pacote em branch/banco descartável **separadamente
   autorizado** com estrutura equivalente. Neon pode limitar CREATEROLE/ownership:
   confirmar capacidade real do administrador antes da janela.

## Aplicação controlada — não executada no Neon

Revisar integralmente `scripts/database/apply_security.sql`. O arquivo abre uma
transação, aplica lock_timeout de 5s e statement_timeout de 60s. Se algum guard
falhar, a transação é abortada; desconectar/ROLLBACK antes de tentar novamente.
Nada é aplicado pela aplicação ou pelo Alembic.

Somente após aprovação:

```powershell
psql "service=biosaude_admin" -X -v ON_ERROR_STOP=1 -f scripts/database/apply_security.sql
```

O script cria `biosaude_app` LOGIN **sem senha**, apenas se não existir. Não altera
senha de role existente. Interrompe se encontrar privilégios administrativos,
membership da app em qualquer role, membros da app além do executor administrativo,
ownership de qualquer objeto, policies desconhecidas, schemas graváveis, functions
SECURITY DEFINER executáveis ou acessos residuais a outras tabelas/sequences.
O administrador criador pode ter grant implícito da role no PostgreSQL 16; isso não
concede poderes à app. Revisar esses grants e não delegar a role a clientes finais.
Se role criada pelo Console herdar neon_superuser, conciliar essa membership por
procedimento administrativo específico aprovado; o script não a remove às cegas.

PUBLIC perde privilégios de banco (incluindo CONNECT/TEMP), schema public, tabelas,
colunas e sequences públicas. Isso pode interromper **outros consumidores** que
usavam PUBLIC: inventariar e planejar grants explícitos antes de aplicar. Grants
antigos em coluna são removidos também; REVOKE de tabela sozinho não os apaga.
Defaults globais do executor neste banco e os específicos de public deixam de
conceder acesso automático à app/PUBLIC. Isso afeta objetos futuros desse criador
no banco, não apenas estas seis tabelas: revisar dependências. Grants globais não
são removidos por REVOKE apenas por schema; o script trata ambos. Defaults de
outras roles criadoras e de outros schemas ainda exigem auditoria.
Revalidar após novas migrations, roles, grants ou policies.

A role nova sem senha não está pronta para autenticação por senha. O administrador
pode definir o segredo pelo canal seguro do provedor ou `\password biosaude_app`
em psql direto com TLS, **somente em etapa autorizada posterior**. Não incluir o
segredo no SQL, chat ou `.env.example`. Nenhuma senha real é criada por este PR.

Atualizar a URL operacional no mecanismo seguro de configuração para a conta
nova, mantendo Alembic com administrador/direta, somente após testes e aprovação.
Não alterar host/TLS para contornar erro de login e não promover a app a owner.
Não habilitar os cadastros nem realizar deploy como efeito colateral desta etapa.

## RLS e identidade confiável

As policies são instaladas e ENABLE/FORCE RLS é aplicado nas seis tabelas na mesma
transação. Não existe etapa intermediária de RLS sem políticas de leitura/escrita
dos cadastros. Empresas/usuários só têm SELECT; domínio de orçamentos permanece
negado, pois não existe fluxo operacional autorizado para ele.

Após JWT válido, o servidor instala `biosaude.subject` local à transação. A consulta
de users permite ler apenas os vínculos desse subject; companies exige vínculo
com perfil reconhecido e empresa ativa. Após selecionar um vínculo autorizado,
o servidor instala `biosaude.company_id`. Hospitais/produtos exigem a empresa
selecionada **e** vínculo do subject, empresa ativa e perfil adequado. Ausência,
identidade desconhecida, empresa alheia ou inativa negam leitura/escrita. Políticas
FOR UPDATE usam USING e WITH CHECK; INSERT usa WITH CHECK. Revisor só lê.

O valor do header X-Company-ID não autoriza acesso: é usado apenas na consulta
que verifica o vínculo. Claims de role/company do cliente não definem esse contexto.
SQLAlchemy reaplica o contexto em cada nova transação da Session, inclusive após
commit/rollback; set_config(..., true) não persiste após a transação. As Sessions
continuam exclusivas de cada requisição. Isso funciona com transaction pooling;
não é SET de sessão permanente e não depende de conexão física exclusiva.

O lock de concorrência agora é advisory **transacional**, por hash estável do UUID
da empresa. Isso preserva a serialização dos cadastros sem conceder UPDATE em
companies apenas para SELECT FOR UPDATE. Colisões só serializam empresas extras;
não autorizam acesso. O lock é liberado com commit/rollback e suporta PgBouncer.

### Limite da fronteira de confiança

GUCs PostgreSQL não verificam assinatura JWT. **Quem obtiver a credencial da role
compartilhada ou capacidade de executar SQL arbitrário como backend pode forjar
esses GUCs.** RLS é proteção contra queries sem filtro/erros de aplicação sob o
contexto validado, não contenção criptográfica de comprometimento do backend.
Não distribuir credenciais de biosaude_app a usuários, Data API ou clientes SQL.
O acesso direto precisa estar restrito ao backend, com segredo protegido, TLS,
restrições de rede e ausência de SQL arbitrário vindo de usuários.

RLS FORCE cobre owner sem BYPASSRLS, mas superuser/BYPASSRLS ainda pode ignorá-la,
e um proprietário administrativo pode alterar/desabilitar políticas. A separação
operacional reduz esse risco; não transforma o administrador em principal restrito.
Outros bancos/schemas e roles do projeto exigem auditoria de acesso separada.

## Verificação posterior, antes de qualquer habilitação

```powershell
psql "service=biosaude_admin" -X -v ON_ERROR_STOP=1 -f scripts/database/verify_security.sql
psql "service=biosaude_app" -X -v ON_ERROR_STOP=1 -f scripts/database/verify_security.sql
```

O script é somente leitura: role/ACLs, memberships, ownership, RLS/policies,
permissões por coluna, funções e defaults. Conexões da aplicação devem indicar
session_user/current_user biosaude_app, sem bypass, CREATE, TEMP, TRUNCATE, DELETE,
grant option, acesso Alembic ou tabelas sem fluxo implementado. Para tabela não
se espera grant INSERT/UPDATE global: grants de coluna são intencionais.

Sem contexto, SELECT dos cadastros deve retornar vazio. Testes reais de escrita,
DDL proibido e cross-tenant pertencem a um banco/branch descartável explicitamente
autorizado, não à production. Revisar evidências desses testes, do provedor JWT,
dos grants, do pooler e dos demais caminhos externos antes de aprovar habilitação.
O diagnóstico SELECT 1 não comprova RLS nem identidade da conta operacional.

## Reversão

- Antes do COMMIT, erro implica rollback integral do script. Não reenviar ignorando
  erros nem fazer grants amplos para contornar guards.
- Após COMMIT, manter catálogo desabilitado e interromper somente consumidores
  autorizados. Se necessário e autorizado, `ALTER ROLE biosaude_app NOLOGIN;`
  impede novos logins; conexões já abertas precisam de encerramento controlado.
- Restaurar ACLs/defaults/policies **exatos do snapshot prévio**, em transação
  revisada e autorizada, com a role administrativa. Não há rollback universal:
  conceder PUBLIC/owner indiscriminadamente pode expor dados. Não remover RLS ou
  ampliar privilégios como tentativa automática de recuperação.
- Reverter configuração/versão do backend somente junto da compatibilidade com
  as políticas: versão anterior não instala contexto e obterá acesso vazio.
  Nunca reativar automaticamente a app com neondb_owner. Manter o tráfego fechado
  até validação de segurança. Não apagar tabelas, dados, roles ou revisões.
- Nenhuma reversão deste procedimento deve executar alembic downgrade ou restore
  integral destrutivo sobre a base real sem plano e aprovação independentes.

## Evidência local e execução dos testes

Os testes preservados verificam JWT, perfis, filtros SQL e autorização de cada
endpoint. `tests/test_postgres_security.py` executa o SQL completo, duas vezes,
em PostgreSQL sintético com TLS, cria senha **somente sintética** e conecta de fato
como biosaude_app. Prova grants/RLS sem mocks de privilégios: DDL/TRUNCATE/roles,
colunas protegidas, tabela Alembic, writes cruzados, contexto inválido, perfil
revisor, FORCE em owner não privilegiado, row_security=off e reciclagem do pool.
Também testa requests HTTP com JWT assinado real sob a conta não proprietária.

Para repetir, usar apenas container local descartável, host localhost/127.0.0.1,
banco biosaude_synthetic_tests e CA sintética. Definir no processo de teste
BIOSAUDE_TEST_DATABASE_URL e BIOSAUDE_SECURITY_TEST_DATABASE_URL com o mesmo alvo
sintético administrativo e BIOSAUDE_TEST_DATABASE_CA; a fixture rejeita banco/host
diferentes. A suíte cria dados/roles/policies somente nesse alvo sintético. Sem
essas variáveis os testes PostgreSQL são explicitamente skipped, não aprovados.

Neon real, suas limitações administrativas, memberships/defaults/grants existentes
e pooling real não foram auditados nem modificados. Essa validação externa e a
aprovação para aplicação manual são pendências; as evidências locais não autorizam
alterações de production.
