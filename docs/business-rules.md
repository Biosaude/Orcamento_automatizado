# Regras de negócio e critérios para evolução

| Regra | Preparação nesta entrega | Condição para implementação futura |
| --- | --- | --- |
| IA não aprova nem envia | Nenhuma rota, worker ou cliente de aprovação/envio | Aprovação humana explícita e auditável; IA limitada a sugestões |
| Finanças determinísticas | Interface `OfficialFinancialEngine`, sem implementação | Receber simulador oficial, definir entradas, versionar e validar resultados contra ele |
| Produtos similares | Catálogo modelado; nenhuma correspondência automática | Validação humana registrada antes de incluir similar no orçamento |
| São Camilo | `quote_template=sao_camilo`, `official_table_id` e variável de configuração | Tabela oficial validada e configuração por empresa/hospital; falhar se tabela não estiver disponível |
| Outros hospitais | `quote_template=standard_vs_opme` como padrão | Receber modelo PDF VS\|OPME oficial; nenhuma geração de PDF nesta entrega |
| Responder ao e-mail original | Referências de mensagem/thread em `QuoteRequest` | Preservar remetente, Message-ID, In-Reply-To e References no futuro adaptador, após aprovação humana |
| Isolamento empresarial | `company_id` obrigatório nas entidades de cada empresa e nos contratos de repositório | Autenticação, autorização, chaves compostas/relações e RLS; testes de acesso cruzado |

Não existem fórmulas, pacientes, produtos reais, estoque, cotações, filas ou envios
nesta base. Preço unitário opcional é somente um valor recebido; não há cálculo
de total. Identificadores e preços sintéticos aparecem exclusivamente em testes.

Estados de solicitação disponíveis nos contratos são recebido e em revisão
humana. Não há fluxo de aprovação. A configuração global da tabela São Camilo
é apenas um ponto de preparação; a política por empresa será definida antes do
uso em produção. O frontend não assume sucesso de APIs ou integrações.
