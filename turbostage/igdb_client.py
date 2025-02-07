import json

import requests
from igdb.wrapper import IGDBWrapper

# API documentation: https://api-docs.igdb.com/#authentication


class IgdbClient:
    CLIENT_ID = "finu9rpxtjmau9p7gv6tmt5rejv3qz"
    CLIENT_SECRET = "mxp3b0ihmkza3lxihsu6vpm9otrq5v"
    DOS_PLATFORM_ID = 13

    def __init__(self):
        self._auth_token = self._get_auth()
        self._wrapper = IGDBWrapper(IgdbClient.CLIENT_ID, self._auth_token)

    @staticmethod
    def _get_auth():
        request_url = f"https://id.twitch.tv/oauth2/token?client_id={IgdbClient.CLIENT_ID}&client_secret={IgdbClient.CLIENT_SECRET}&grant_type=client_credentials"
        response = requests.post(request_url)
        if response.status_code != 200:
            raise RuntimeError("Unable to authenticate to IGDB.com")
        payload = json.loads(response.content)
        if "access_token" not in payload:
            raise RuntimeError("Malformed answer from IGDB.com")
        return payload["access_token"]

    def query(self, endpoint: str, fields: list[str], where_clause: str = "", limit: int = 10, sort: str = ""):
        query = f"fields {','.join(fields)}; limit {limit};"
        if where_clause:
            query += f" where {where_clause};"
        if sort:
            query += f" sort {sort};"
        byte_array = self._wrapper.api_request(endpoint, query)
        return json.loads(byte_array)

    def search(self, endpoint: str, fields: list[str], search_query: str, where_clause: str = ""):
        query = f"""search "{search_query}"; fields {','.join(fields)};"""
        if where_clause:
            query += f" where {where_clause};"
        byte_array = self._wrapper.api_request(endpoint, query)
        return json.loads(byte_array)

    def get_genres(self, genre_ids: list[int]) -> list[str]:
        response = self.query("genres", ["name"], f"id=({','.join([str(i) for i in genre_ids])})")
        return [r["name"] for r in response]

    def get_release_date(self, release_date_ids: list[int]) -> list[int]:
        response = self.query(
            "release_dates", ["date", "platform"], f"id=({','.join([str(d) for d in release_date_ids])})", sort="date"
        )
        for r in response:
            if r["platform"] == self.DOS_PLATFORM_ID:
                return r["date"]
        # if no release date for msdos, return first release date
        return response[0]["date"]
