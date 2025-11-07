# app.py
import os
import time
import requests
import streamlit as st

st.set_page_config(page_title="Cast-Overlap Recommender", layout="wide")

TMDB_BASE = "https://api.themoviedb.org/3"

def _is_bearer(token: str) -> bool:
    return "." in (token or "")

def tmdb_get(endpoint: str, key: str, params: dict | None = None, tries: int = 4):
    if params is None: params = {}
    headers = {"Accept": "application/json"}
    url = f"{TMDB_BASE}{endpoint}"
    if _is_bearer(key):
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key

    backoff = 0.7
    for i in range(tries):
        r = requests.get(url, params=params, headers=headers, timeout=20)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            retry_after = float(r.headers.get("Retry-After") or 0)
            time.sleep(min(backoff * (2**i), 6.0) if not retry_after else retry_after)
            continue
        try:
            msg = r.json().get("status_message")
        except Exception:
            msg = r.text
        raise RuntimeError(f"TMDb error {r.status_code}: {msg} [{endpoint}]")
    raise RuntimeError("TMDb: retries exhausted")

@st.cache_data(ttl=24*3600, show_spinner=False)
def tmdb_configuration(key: str):
    return tmdb_get("/configuration", key)

def img_url(path: str | None, key: str, kind="poster", size="w185"):
    if not path: return None
    cfg = tmdb_configuration(key)
    base = cfg["images"]["secure_base_url"]
    sizes = cfg["images"]["poster_sizes" if kind=="poster" else "profile_sizes"]
    if size not in sizes:
        size = sizes[0]
    return f"{base}{size}{path}"

@st.cache_data(ttl=24*3600, show_spinner=False)
def search_multi(query: str, key: str):
    return tmdb_get("/search/multi", key, {"query": query, "include_adult": "false"})

@st.cache_data(ttl=24*3600, show_spinner=False)
def movie_credits(movie_id: int, key: str):
    return tmdb_get(f"/movie/{movie_id}/credits", key)

@st.cache_data(ttl=24*3600, show_spinner=False)
def tv_aggregate_credits(tv_id: int, key: str):
    return tmdb_get(f"/tv/{tv_id}/aggregate_credits", key)

@st.cache_data(ttl=24*3600, show_spinner=False)
def person_combined_credits(person_id: int, key: str):
    return tmdb_get(f"/person/{person_id}/combined_credits", key)

@st.cache_data(ttl=24*3600, show_spinner=False)
def get_videos(media_type: str, media_id: int, key: str):
    """Get trailers and videos for a movie or TV show."""
    endpoint = f"/{media_type}/{media_id}/videos"
    return tmdb_get(endpoint, key)

@st.cache_data(ttl=24*3600, show_spinner=False)
def get_watch_providers(media_type: str, media_id: int, key: str):
    """Get streaming availability for a movie or TV show."""
    endpoint = f"/{media_type}/{media_id}/watch/providers"
    return tmdb_get(endpoint, key)

@st.cache_data(ttl=24*3600, show_spinner=False)
def search_person(query: str, key: str):
    """Search for actors/people."""
    return tmdb_get("/search/person", key, {"query": query, "include_adult": "false"})

@st.cache_data(ttl=24*3600, show_spinner=False)
def get_genre_list(key: str):
    """Get list of all genres for movies and TV."""
    movie_genres = tmdb_get("/genre/movie/list", key).get("genres", [])
    tv_genres = tmdb_get("/genre/tv/list", key).get("genres", [])
    # Combine and deduplicate
    all_genres = {g["id"]: g["name"] for g in movie_genres + tv_genres}
    return all_genres

st.title("🎭 Cast-Overlap Recommender")

api_key = os.environ.get("TMDB_KEY")
if not api_key:
    st.error("Missing TMDB_KEY environment variable. Please set it and restart.")
    st.stop()
st.text("Using TMDb key from TMDB_KEY env var.")

# ---- Search + select ----
with st.expander("Search & select titles (movies or TV)", expanded=True):
    q = st.text_input("Search title:")
    if "selected" not in st.session_state:
        st.session_state.selected = []  # list of dicts
    if "selected_actors" not in st.session_state:
        st.session_state.selected_actors = []  # list of person dicts

    if q:
        res = search_multi(q, api_key) or {}
        hits = []
        for it in res.get("results", []):
            if it.get("media_type") not in ("movie", "tv"):
                continue
            title = it.get("title") or it.get("name")
            year = (it.get("release_date") or it.get("first_air_date") or "")[:4]
            hits.append({
                "media_type": it["media_type"],
                "id": it["id"],
                "title": title,
                "year": year,
                "poster_path": it.get("poster_path")
            })
        cols = st.columns(4)
        for i, h in enumerate(hits[:20]):
            with cols[i % 4]:
                poster_url = img_url(h["poster_path"], api_key)
                if poster_url:
                    st.image(poster_url, width=120)
                else:
                    st.write("🎬")  # Placeholder for missing poster
                st.write(f"**{h['title']}** ({h['year']}) · *{h['media_type']}*")
                if st.button(f"Add · {h['title']}", key=f"add_{h['media_type']}_{h['id']}"):
                    if not any(s["media_type"]==h["media_type"] and s["id"]==h["id"] for s in st.session_state.selected):
                        st.session_state.selected.append(h)

    if st.session_state.selected:
        st.write("### Selected")
        sel_cols = st.columns(6)
        for i, s in enumerate(st.session_state.selected):
            with sel_cols[i % 6]:
                poster_url = img_url(s.get("poster_path"), api_key)
                if poster_url:
                    st.image(poster_url, width=90)
                else:
                    st.write("🎬")
                st.caption(f"{s['title']} ({s['year']}) · *{s['media_type']}*")
                if st.button("✕ Remove", key=f"remove_{s['media_type']}_{s['id']}"):
                    st.session_state.selected = [item for item in st.session_state.selected
                                                  if not (item['media_type'] == s['media_type'] and item['id'] == s['id'])]
                    st.rerun()
        if st.button("Clear all selections"):
            st.session_state.selected = []
            st.rerun()

# ---- Actor search + select ----
with st.expander("Search & select individual actors", expanded=False):
    actor_q = st.text_input("Search actor/actress:")

    if actor_q:
        actor_res = search_person(actor_q, api_key) or {}
        actor_hits = []
        for person in actor_res.get("results", [])[:20]:
            if person.get("known_for_department") == "Acting":
                actor_hits.append({
                    "id": person["id"],
                    "name": person.get("name"),
                    "profile_path": person.get("profile_path"),
                    "known_for": person.get("known_for", [])
                })

        cols = st.columns(4)
        for i, actor in enumerate(actor_hits):
            with cols[i % 4]:
                profile_url = img_url(actor["profile_path"], api_key, kind="profile", size="h632")
                if profile_url:
                    st.image(profile_url, width=120)
                else:
                    st.write("👤")
                st.write(f"**{actor['name']}**")
                # Show what they're known for
                known_titles = [kf.get("title") or kf.get("name") for kf in actor["known_for"][:2]]
                if known_titles:
                    st.caption(f"Known for: {', '.join(known_titles)}")
                if st.button(f"Add · {actor['name']}", key=f"add_actor_{actor['id']}"):
                    if not any(a["id"] == actor["id"] for a in st.session_state.selected_actors):
                        st.session_state.selected_actors.append(actor)
                        st.rerun()

    if st.session_state.selected_actors:
        st.write("### Selected Actors")
        actor_cols = st.columns(6)
        for i, actor in enumerate(st.session_state.selected_actors):
            with actor_cols[i % 6]:
                profile_url = img_url(actor.get("profile_path"), api_key, kind="profile", size="h632")
                if profile_url:
                    st.image(profile_url, width=120)
                else:
                    st.write("👤")
                st.caption(f"{actor['name']}")
                if st.button("✕ Remove", key=f"remove_actor_{actor['id']}"):
                    st.session_state.selected_actors = [a for a in st.session_state.selected_actors if a['id'] != actor['id']]
                    st.rerun()
        if st.button("Clear all actors"):
            st.session_state.selected_actors = []
            st.rerun()

st.write("---")
st.subheader("Ranking options")
c1, c2, c3, c4 = st.columns(4)
min_overlap = c1.slider("Minimum overlapping actors", 1, 10, 2)
max_cast_per_title = c2.slider("Max cast used per selected title", 5, 150, 40)
min_tv_episodes = c3.slider("Min episodes to count a TV actor", 1, 50, 2)
max_credits_per_actor = c4.slider("Max candidate credits per actor", 20, 500, 250)
col_left, col_right = st.columns([1, 2])
with col_left:
    top_n = st.slider("How many results to show", 10, 300, 60)
with col_right:
    # Store in session state to preserve across reruns
    if "media_filter" not in st.session_state:
        st.session_state.media_filter = "Both"
    media_filter = st.radio("Show recommendations for:", ["Both", "Movies only", "TV shows only"],
                           horizontal=True,
                           key="media_filter_radio",
                           index=["Both", "Movies only", "TV shows only"].index(st.session_state.media_filter))

st.write("### Filters")
filter_col1, filter_col2 = st.columns(2)
with filter_col1:
    # Get all genres
    all_genres = get_genre_list(api_key)
    genre_names = sorted(all_genres.values())
    selected_genres = st.multiselect("Filter by genres (optional)", genre_names, default=[])
with filter_col2:
    actor_name_filter = st.text_input("Filter by actor name (optional)")

if not st.session_state.selected and not st.session_state.selected_actors:
    st.info("Add at least one title or actor to get recommendations.")
    st.stop()

# ---- Build seed cast ----
def total_eps_in_tv_agg(c):
    if "total_episode_count" in c:
        return c.get("total_episode_count") or 0
    roles = c.get("roles") or []
    return sum((r.get("episode_count") or 0) for r in roles)

def collect_seed_cast(selected, selected_actors):
    # person_id -> dict(name, profile_path, weight)
    actors = {}
    for s in selected:
        if s["media_type"] == "movie":
            data = movie_credits(s["id"], api_key)
            cast = sorted(data.get("cast", []), key=lambda x: x.get("order", 10**6))[:max_cast_per_title]
            for c in cast:
                pid = c["id"]
                entry = actors.setdefault(pid, {"name": c.get("name"), "profile": c.get("profile_path"), "weight": 0.0})
                order = c.get("order")
                bump = max(1.0, 10.0 - min(order if isinstance(order, int) else 1000, 9))
                entry["weight"] += bump
        else:
            data = tv_aggregate_credits(s["id"], api_key)
            cast = data.get("cast", [])
            cast = [c for c in cast if total_eps_in_tv_agg(c) >= min_tv_episodes]
            cast = sorted(cast, key=total_eps_in_tv_agg, reverse=True)[:max_cast_per_title]
            for c in cast:
                pid = c["id"]
                entry = actors.setdefault(pid, {"name": c.get("name"), "profile": c.get("profile_path"), "weight": 0.0})
                entry["weight"] += total_eps_in_tv_agg(c)

    # Add individually selected actors with high weight
    for actor in selected_actors:
        pid = actor["id"]
        entry = actors.setdefault(pid, {"name": actor.get("name"), "profile": actor.get("profile_path"), "weight": 0.0})
        entry["weight"] += 20.0  # Give individually selected actors high weight

    return actors

def is_talk_show(title: str) -> bool:
    """Detect if a title is likely a talk show based on common patterns."""
    if not title:
        return False

    title_lower = title.lower()

    # Common talk show patterns
    talk_show_patterns = [
        "tonight show",
        "late night",
        "late show",
        "live with",
        "live!",
        "watch what happens",
        "jimmy kimmel",
        "jimmy fallon",
        "conan",
        "daily show",
        "colbert",
        "real time with",
        "last week tonight",
        "ellen",
        "james corden",
        "seth meyers",
        "today show",
        "good morning",
        "the view",
        "the talk",
        "wendy williams"
    ]

    return any(pattern in title_lower for pattern in talk_show_patterns)

def titles_too_similar(title1: str, title2: str) -> bool:
    """Check if two titles are too similar (e.g., spin-offs, documentaries)."""
    if not title1 or not title2:
        return False

    # Normalize titles: lowercase, remove common punctuation
    def normalize(t):
        return t.lower().replace(":", "").replace("-", " ").replace("'", "").strip()

    t1_norm = normalize(title1)
    t2_norm = normalize(title2)

    # Extract main words (length > 2 to ignore articles like "a", "an", "the")
    words1 = set(w for w in t1_norm.split() if len(w) > 2)
    words2 = set(w for w in t2_norm.split() if len(w) > 2)

    if not words1 or not words2:
        return False

    # Calculate overlap ratio
    overlap = words1.intersection(words2)
    smaller_set_size = min(len(words1), len(words2))

    # If 70%+ of the smaller title's words appear in the other, they're too similar
    if smaller_set_size > 0 and len(overlap) / smaller_set_size >= 0.7:
        return True

    return False

def recommend(selected, selected_actors):
    seed = collect_seed_cast(selected, selected_actors)
    selected_keys = {(s["media_type"], s["id"]) for s in selected}
    selected_titles = [s["title"] for s in selected]
    # Map person_id to which selected title they came from
    person_to_source = {}
    for s in selected:
        if s["media_type"] == "movie":
            data = movie_credits(s["id"], api_key)
            for c in data.get("cast", []):
                person_to_source.setdefault(c["id"], []).append(s["title"])
        else:
            data = tv_aggregate_credits(s["id"], api_key)
            for c in data.get("cast", []):
                person_to_source.setdefault(c["id"], []).append(s["title"])

    # Add individually selected actors to source map
    for actor in selected_actors:
        person_to_source.setdefault(actor["id"], []).append(f"[Actor: {actor['name']}]")

    candidates = {}  # (mt,id) -> dict

    prog = st.progress(0.0, text="Collecting candidates from overlapping actors…")
    items = list(seed.items())
    for i, (pid, meta) in enumerate(items):
        cc = person_combined_credits(pid, api_key)
        seen_this_actor = set()  # Track which candidates this actor has already contributed to
        for cr in (cc.get("cast") or [])[:max_credits_per_actor]:
            mt = cr.get("media_type")
            if mt not in ("movie", "tv"):
                continue
            tid = cr.get("id")
            if (mt, tid) in selected_keys:
                continue

            # Skip if we've already counted this actor for this candidate
            cand_key = (mt, tid)
            if cand_key in seen_this_actor:
                continue
            seen_this_actor.add(cand_key)

            # Check if candidate title is too similar to any selected title
            candidate_title = cr.get("title") or cr.get("name")
            if any(titles_too_similar(candidate_title, sel_title) for sel_title in selected_titles):
                continue

            # Filter out talk shows
            if is_talk_show(candidate_title):
                continue

            rec = candidates.setdefault(cand_key, {
                "media_type": mt,
                "id": tid,
                "title": cr.get("title") or cr.get("name"),
                "year": (cr.get("release_date") or cr.get("first_air_date") or "")[:4],
                "poster": cr.get("poster_path"),
                "overlap_count": 0,
                "seed_weight_sum": 0.0,
                "candidate_episode_sum": 0,
                "vote_average": cr.get("vote_average", 0),
                "vote_count": cr.get("vote_count", 0),
                "genre_ids": cr.get("genre_ids", []),
                "actor_info": {}  # actor_name -> {sources: [], profile: path}
            })
            rec["overlap_count"] += 1
            rec["seed_weight_sum"] += meta["weight"]
            rec["candidate_episode_sum"] += int(cr.get("episode_count") or 0)
            # Track which selected title(s) this actor came from and their profile photo
            rec["actor_info"][meta["name"]] = {
                "sources": person_to_source.get(pid, []),
                "profile": meta.get("profile")
            }
        prog.progress((i+1)/max(len(items), 1))

    out = [c for c in candidates.values() if c["overlap_count"] >= min_overlap]
    out.sort(key=lambda x: (-x["overlap_count"], -x["seed_weight_sum"], -x["candidate_episode_sum"]))
    return out

results = recommend(st.session_state.selected, st.session_state.selected_actors)

# Update session state with current filter value
st.session_state.media_filter = media_filter

# Apply media type filter
if media_filter == "Movies only":
    results = [r for r in results if r["media_type"] == "movie"]
elif media_filter == "TV shows only":
    results = [r for r in results if r["media_type"] == "tv"]

# Apply genre filter
if selected_genres:
    # Convert genre names back to IDs
    genre_id_map = {v: k for k, v in all_genres.items()}
    selected_genre_ids = [genre_id_map[name] for name in selected_genres]
    results = [r for r in results if any(gid in r.get("genre_ids", []) for gid in selected_genre_ids)]

# Apply actor name filter
if actor_name_filter:
    filter_lower = actor_name_filter.lower()
    results = [r for r in results if any(filter_lower in actor_name.lower() for actor_name in r["actor_info"].keys())]

results = results[:top_n]

st.write("---")
st.subheader("Recommendations")
if not results:
    st.warning("No results met the current overlap threshold. Try lowering it.")
else:
    # Add CSS for consistent card heights
    st.markdown("""
        <style>
        .rec-card {
            min-height: 450px;
            max-height: 450px;
            overflow: hidden;
        }
        </style>
    """, unsafe_allow_html=True)

    cols = st.columns(5)
    for i, r in enumerate(results):
        with cols[i % 5]:
            # Truncate long titles
            title = r['title']
            if len(title) > 50:
                title = title[:47] + "..."

            poster_url = img_url(r["poster"], api_key)
            if poster_url:
                st.image(poster_url, width=150)
            else:
                st.write("🎬")
            st.markdown(f"**{title}** ({r['year']}) · *{r['media_type']}*")
            st.caption(f"Overlap: **{r['overlap_count']}** actors")

            # Get and display trailer
            try:
                videos_data = get_videos(r['media_type'], r['id'], api_key)
                trailers = [v for v in videos_data.get("results", [])
                           if v.get("type") == "Trailer" and v.get("site") == "YouTube"]
                if trailers:
                    trailer_key = trailers[0]["key"]
                    st.markdown(f"[▶️ Watch Trailer](https://www.youtube.com/watch?v={trailer_key})")
            except:
                pass

            # Get and display streaming platforms
            try:
                providers_data = get_watch_providers(r['media_type'], r['id'], api_key)
                us_providers = providers_data.get("results", {}).get("US", {})

                # Prioritize subscription services (flatrate)
                platforms = []
                if "flatrate" in us_providers:
                    platforms = [p["provider_name"] for p in us_providers["flatrate"][:3]]
                elif "buy" in us_providers:
                    platforms = [p["provider_name"] for p in us_providers["buy"][:3]]

                if platforms:
                    st.caption(f"📺 {', '.join(platforms)}")
            except:
                pass
            actor_info = r["actor_info"]
            if actor_info:
                with st.expander(f"Show {len(actor_info)} shared cast"):
                    for name in sorted(actor_info.keys()):
                        info = actor_info[name]
                        source_titles = info.get("sources", [])
                        profile_path = info.get("profile")

                        col1, col2 = st.columns([1, 4])
                        with col1:
                            profile_url = img_url(profile_path, api_key, kind="profile", size="h632")
                            if profile_url:
                                st.image(profile_url, width=120)
                            else:
                                st.write("👤")
                        with col2:
                            if source_titles:
                                sources_str = ", ".join(source_titles)
                                st.markdown(f"**{name}**  \n*from {sources_str}*")
                            else:
                                st.markdown(f"**{name}**")

st.write("---")
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray; font-size: 0.9em;'>"
    "This product uses the TMDb API but is not endorsed or certified by TMDb."
    "</div>",
    unsafe_allow_html=True
)
