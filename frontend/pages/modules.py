"""Páginas informativas: nenhuma operação fictícia é apresentada como disponível."""

import streamlit as st

PAGE_DESCRIPTIONS = {
    "Dashboard": "Visão inicial do projeto e dos limites desta entrega.",
    "Solicitações": "Entrada e revisão humana de solicitações de orçamento OPME.",
    "Simulador": "Motor financeiro determinístico baseado no simulador oficial da Biosaúde.",
    "Produtos": "Catálogo de produtos e validação humana de correspondências similares.",
    "Estoque": "Consulta futura de disponibilidade por empresa.",
    "Hospitais": "Cadastro de hospitais e configuração de modelos e tabelas oficiais.",
    "Histórico": "Trilha futura de auditoria das ações e decisões humanas.",
    "Configurações": "Configuração futura de empresas e provedores por variáveis de ambiente.",
}


def render_page(page: str) -> None:
    st.header(page)
    st.write(PAGE_DESCRIPTIONS[page])
    if page == "Dashboard":
        st.info("Base do MVP criada. Ainda não há dados operacionais, indicadores ou persistência.")
        st.subheader("Disponível nesta entrega")
        st.markdown("- API de saúde em `/health`\n- Navegação dos módulos\n- Contratos de domínio")
        st.caption("O estado da API deve ser verificado em /health; esta tela não consulta a API.")
    else:
        st.info("Módulo em preparação. Nenhuma operação ou integração está habilitada.")

    if page == "Simulador":
        st.warning("Cálculos aguardam o simulador oficial validado. Nenhuma fórmula foi definida.")
    elif page == "Produtos":
        st.write("Produtos similares exigirão validação humana antes de uso em um orçamento.")
    elif page == "Hospitais":
        st.write("Padrão previsto: PDF VS|OPME. São Camilo terá exceção configurável e validada.")
    elif page == "Solicitações":
        st.write(
            "A IA nunca aprovará ou enviará orçamentos. "
            "O envio futuro responderá ao e-mail original."
        )
    elif page == "Configurações":
        st.write(
            "Supabase, Locaweb, OpenAI e Twilio: apenas nomes de configuração foram preparados."
        )
        st.write(
            "Credenciais devem permanecer fora do Git. Seus valores não são exibidos nesta tela."
        )
        st.code(
            "BIOSAUDE_DATABASE_URL\nBIOSAUDE_SUPABASE_URL\n"
            "BIOSAUDE_LOCAWEB_SMTP_HOST\nBIOSAUDE_OPENAI_API_KEY\n"
            "BIOSAUDE_TWILIO_ACCOUNT_SID\nBIOSAUDE_SAO_CAMILO_TABLE_ID"
        )
