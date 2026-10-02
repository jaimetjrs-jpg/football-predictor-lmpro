import streamlit as st

st.set_page_config(
    page_title="Football AI Pro",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ Football AI Pro")

st.caption("Analyse de matchs de football")

home_team = st.text_input(
    "Équipe domicile"
)

away_team = st.text_input(
    "Équipe extérieure"
)

if st.button("Analyser"):
    if home_team and away_team:
        st.success(
            f"Match sélectionné : {home_team} vs {away_team}"
        )
    else:
        st.warning(
            "Veuillez renseigner les deux équipes."
        )
