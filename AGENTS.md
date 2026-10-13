# Regras de desenvolvimento

- Usar Python 3.12; executar comandos da raiz do checkout existente. Tarefas cloud
  já são isoladas: não criar worktrees sem solicitação explícita.
- Preservar funcionalidades e alterações existentes; não sobrescrever trabalho
  local nem remover testes para fazer a validação passar.
- Separar HTTP (`backend/app/api`), configuração (`core`), domínio (`domain`),
  interface (`frontend`) e tarefas assíncronas futuras (`workers`).
- Não declarar módulo operacional sem implementação e evidência. Manter os
  avisos de indisponibilidade até a entrega real de cada fluxo.
- Alterações de dependências devem atualizar `pyproject.toml` e `uv.lock` juntas,
  com versões revisadas. Instalar com `uv sync --locked`; não usar `latest`.
- Executar `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`
  e `uv run --frozen pytest`. Para alterações de execução, iniciar os serviços e
  validar respostas HTTP; para UI, manter testes de navegação via AppTest.

## Segurança e privacidade

- Nunca versionar `.env`, segredos, tokens, documentos hospitalares, planilhas
  confidenciais ou dados de pacientes. `.env.example` contém apenas exemplos
  fictícios. `.gitignore` é defesa adicional, não um controle de acesso.
- Não ler, imprimir, registrar ou enviar valores de credenciais. Configuração
  sensível usa `SecretStr`; não expor `Settings` em endpoints ou na UI.
- Usar somente dados sintéticos identificados como testes. Guardar material
  real fora do checkout. Não copiar arquivos reais para exemplos ou fixtures.
- Novas integrações, e-mails ou mensagens exigem tarefa específica autorizada.
  Esta base não contém clientes externos nem envio.
- Futuras rotas devem derivar `company_id` da identidade autenticada, validar
  relações na mesma empresa e aplicar RLS/autorização no banco. A presença do
  campo nos modelos não implementa isolamento. Não expor CRUD antes disso.

## Regras obrigatórias de negócio

- IA jamais aprova ou envia orçamentos autonomamente.
- Cálculos somente pelo motor determinístico validado contra o simulador oficial
  da Biosaúde. Não inventar fórmulas, margens, impostos ou preços.
- Correspondência de produtos similares exige validação humana registrada.
- São Camilo é uma exceção configurável baseada na tabela oficial; demais
  hospitais usam o PDF padrão VS|OPME. Não inferir exceção por comparação de nome.
- Envio futuro deverá responder ao e-mail original e manter sua thread; requer
  aprovação humana, auditoria e implementação autorizada separadamente.
- Consultar `docs/business-rules.md` e `docs/architecture.md` antes de evoluir os fluxos.
