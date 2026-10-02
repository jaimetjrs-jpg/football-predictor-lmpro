import statistics

import requests
import streamlit as st


st.set_page_config(
    page_title="Football AI Pro",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football AI Pro")
st.caption("Matchs et cotes réelles fournis par The Odds API")


API_BASE_URL = "https://api.the-odds-api.com/v4"
REQUEST_TIMEOUT = 20


def get_api_key():
    try:
        return str(st.secrets["THE_ODDS_API_KEY"]).strip()
    except Exception:
        return ""


@st.cache_data(ttl=3600, show_spinner=False)
def get_soccer_competitions(api_key):
    response = requests.get(
        f"{API_BASE_URL}/sports/",
        params={
            "apiKey": api_key,
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 401:
        raise RuntimeError("Clé API invalide ou absente.")

    if response.status_code == 429:
        raise RuntimeError("Trop de requêtes. Réessaie plus tard.")

    response.raise_for_status()

    sports = response.json()

    soccer_sports = [
        sport
        for sport in sports
        if sport.get("active")
        and sport.get("group") == "Soccer"
        and not sport.get("has_outrights", False)
    ]

    return sorted(
        soccer_sports,
        key=lambda sport: sport.get("title", ""),
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_odds(api_key, sport_key):
    response = requests.get(
        f"{API_BASE_URL}/sports/{sport_key}/odds/",
        params={
            "apiKey": api_key,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 401:
        raise RuntimeError("Clé API invalide ou quota épuisé.")

    if response.status_code == 422:
        raise RuntimeError(
            "Cette compétition ou ce marché n’est pas disponible."
        )

    if response.status_code == 429:
        raise RuntimeError("Limite de requêtes atteinte.")

    response.raise_for_status()

    remaining = response.headers.get(
        "x-requests-remaining",
        "inconnu",
    )

    return response.json(), remaining


def extract_bookmaker_odds(event):
    rows = []

    for bookmaker in event.get("bookmakers", []):
        h2h_market = next(
            (
                market
                for market in bookmaker.get("markets", [])
                if market.get("key") == "h2h"
            ),
            None,
        )

        if not h2h_market:
            continue

        outcomes = {
            outcome.get("name"): float(outcome.get("price"))
            for outcome in h2h_market.get("outcomes", [])
            if outcome.get("name")
            and outcome.get("price")
        }

        rows.append(
            {
                "Bookmaker": bookmaker.get("title", "Inconnu"),
                "Domicile": outcomes.get(event["home_team"]),
                "Nul": outcomes.get("Draw"),
                "Extérieur": outcomes.get(event["away_team"]),
                "Mise à jour": bookmaker.get("last_update", ""),
            }
        )

    return rows


def valid_prices(rows, column):
    return [
        float(row[column])
        for row in rows
        if isinstance(row.get(column), (int, float))
        and row[column] > 1
    ]


def calculate_market_analysis(rows):
    home_prices = valid_prices(rows, "Domicile")
    draw_prices = valid_prices(rows, "Nul")
    away_prices = valid_prices(rows, "Extérieur")

    if not home_prices or not away_prices:
        return None

    average_home = statistics.mean(home_prices)
    average_draw = (
        statistics.mean(draw_prices)
        if draw_prices
        else None
    )
    average_away = statistics.mean(away_prices)

    raw_probabilities = {
        "Domicile": 1 / average_home,
        "Extérieur": 1 / average_away,
    }

    average_odds = {
        "Domicile": average_home,
        "Extérieur": average_away,
    }

    best_odds = {
        "Domicile": max(home_prices),
        "Extérieur": max(away_prices),
    }

    if average_draw:
        raw_probabilities["Nul"] = 1 / average_draw
        average_odds["Nul"] = average_draw
        best_odds["Nul"] = max(draw_prices)

    overround = sum(raw_probabilities.values())

    fair_probabilities = {
        outcome: probability / overround
        for outcome, probability in raw_probabilities.items()
    }

    fair_odds = {
        outcome: 1 / probability
        for outcome, probability in fair_probabilities.items()
    }

    return {
        "average_odds": average_odds,
        "best_odds": best_odds,
        "fair_probabilities": fair_probabilities,
        "fair_odds": fair_odds,
        "margin": (overround - 1) * 100,
    }


api_key = get_api_key()

if not api_key:
    st.error(
        "La clé THE_ODDS_API_KEY est absente des Secrets Streamlit."
    )
    st.stop()


try:
    with st.spinner("Chargement des compétitions..."):
        competitions = get_soccer_competitions(api_key)

    if not competitions:
        st.warning(
            "Aucune compétition de football n’est disponible "
            "avec ce compte actuellement."
        )
        st.stop()

    competition_names = {
        sport["title"]: sport["key"]
        for sport in competitions
    }

    selected_competition = st.selectbox(
        "Compétition",
        options=list(competition_names.keys()),
    )

    if st.button(
        "Charger les matchs et les cotes",
        use_container_width=True,
    ):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Récupération des cotes réelles..."):
        events, requests_remaining = get_odds(
            api_key,
            competition_names[selected_competition],
        )

    st.caption(
        f"Crédits API restants indiqués : {requests_remaining}"
    )

    if not events:
        st.info(
            "Aucun match coté n’est disponible actuellement "
            "pour cette compétition."
        )
        st.stop()

    event_labels = {
        (
            f"{event['home_team']} vs {event['away_team']} "
            f"• {event.get('commence_time', '')[:16]}"
        ): event
        for event in events
    }

    selected_label = st.selectbox(
        "Match",
        options=list(event_labels.keys()),
    )

    selected_event = event_labels[selected_label]

    st.subheader(
        f"{selected_event['home_team']} "
        f"vs {selected_event['away_team']}"
    )

    bookmaker_rows = extract_bookmaker_odds(selected_event)

    if not bookmaker_rows:
        st.warning(
            "Aucune cote 1-N-2 exploitable n’a été trouvée."
        )
        st.stop()

    analysis = calculate_market_analysis(bookmaker_rows)

    st.subheader("📊 Comparaison des bookmakers")
    st.dataframe(
        bookmaker_rows,
        use_container_width=True,
        hide_index=True,
    )

    if not analysis:
        st.warning(
            "Données insuffisantes pour calculer les probabilités."
        )
        st.stop()

    st.subheader("📈 Analyse du marché")

    outcomes = ["Domicile", "Nul", "Extérieur"]
    available_outcomes = [
        outcome
        for outcome in outcomes
        if outcome in analysis["fair_probabilities"]
    ]

    columns = st.columns(len(available_outcomes))

    for column, outcome in zip(columns, available_outcomes):
        probability = (
            analysis["fair_probabilities"][outcome] * 100
        )
        best_odd = analysis["best_odds"][outcome]

        column.metric(
            outcome,
            f"{probability:.1f} %",
            help=(
                f"Meilleure cote observée : {best_odd:.2f}"
            ),
        )

    st.metric(
        "Marge moyenne estimée du marché",
        f"{analysis['margin']:.2f} %",
    )

    summary_rows = []

    for outcome in available_outcomes:
        summary_rows.append(
            {
                "Résultat": outcome,
                "Cote moyenne": round(
                    analysis["average_odds"][outcome],
                    2,
                ),
                "Meilleure cote": round(
                    analysis["best_odds"][outcome],
                    2,
                ),
                "Probabilité sans marge": round(
                    analysis["fair_probabilities"][outcome]
                    * 100,
                    2,
                ),
                "Cote équitable": round(
                    analysis["fair_odds"][outcome],
                    2,
                ),
            }
        )

    st.dataframe(
        summary_rows,
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "Ces probabilités proviennent uniquement du marché "
        "des bookmakers après retrait mathématique de la marge. "
        "Elles ne constituent pas une garantie de résultat."
    )

except requests.Timeout:
    st.error(
        "The Odds API met trop de temps à répondre. "
        "Réessaie dans quelques instants."
    )

except requests.ConnectionError:
    st.error(
        "Connexion impossible à The Odds API."
    )

except requests.HTTPError as error:
    st.error(
        f"Erreur HTTP pendant l’appel API : {error}"
    )

except RuntimeError as error:
    st.error(str(error))

except Exception as error:
    st.error(
        f"Erreur inattendue : {error}"
    )
