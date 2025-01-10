import requests

# API documentation: https://api-docs.igdb.com/#authentication

class Igdb:
    client_id = "finu9rpxtjmau9p7gv6tmt5rejv3qz"
    client_secret = "fuoapu5qfwkglj3wtwjhscvs40ch37"

    def __init__(self):
        self._auth = self._get_auth()

    def _get_auth(self):
        request_url = f"https://id.twitch.tv/oauth2/token?client_id={Igdb.client_id}&client_secret={Igdb.client_secret}&grant_type=client_credentials"
        response = requests.post(request_url)
        if response.status_code != 200:
            raise RuntimeError("Unable to authenticate to IGDB.com")
        if "access_token" not in response.data:
            raise RuntimeError("Malformed answer from IGDB.com"
        return response.data["access_token"]
