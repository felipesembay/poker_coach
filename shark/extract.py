import requests
import json
import time

from pathlib import Path
from urllib.parse import quote


# ============================================================
# CONFIGURAÇÕES
# ============================================================

name = "PowderyMaple763"

network = "PartyPoker"

base_url = (
    "https://www.sharkscope.com/poker-statistics/networks"
)

url = (
    f"{base_url}/{quote(network)}/players/{quote(name)}"
)


# ============================================================
# HEADERS
# ============================================================

headers = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/json;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9"
}


# ============================================================
# EXTRAÇÃO
# ============================================================

def extract_api(url, headers=None, timeout=30):

    session = requests.Session()

    response = session.get(
        url,
        headers=headers,
        timeout=timeout
    )

    print("Status code:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("URL final:", response.url)

    response.raise_for_status()

    return response


# ============================================================
# EXECUÇÃO
# ============================================================

response = extract_api(
    url=url,
    headers=headers
)


# ============================================================
# SALVAR RESPOSTA BRUTA
# ============================================================

Path("data/raw").mkdir(
    parents=True,
    exist_ok=True
)

content_type = response.headers.get(
    "Content-Type",
    ""
).lower()


if "application/json" in content_type:

    data = response.json()

    with open(
        "data/raw/player.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("JSON salvo com sucesso!")


else:

    with open(
        "data/raw/player.html",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(response.text)

    print("HTML salvo com sucesso!")