import asyncio
import logging, os
from requests.adapters import HTTPAdapter
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from oauthlib.oauth2 import BackendApplicationClient
from requests.auth import HTTPBasicAuth
from urllib3.util import Retry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
import json
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import time

from .const import (
    CONF_HOME_ID,
    API_ENDPOINT,
    OAUTH2_CALLBACK_PATH,
    OAUTH2_SCOPE,
    OAUTH2_FILE,
    OAUTH2_TOKEN_URL,
    QUERY_HOME_DEVICES,
    QUERY_DEVICE_BY_ID,
    MUTATION_DEVICE_PARAMETER_SET,
)


class LumicAPI:
    def __init__(self, auth, hass, config):
        self._auth = auth
        self._hass = hass
        self._config = config
        self._logger = logging.getLogger(__name__ + ":" + self.__class__.__name__)

    async def _request(self, query, vars):
        if self._auth is None:
            _LOGGER.error(
                "Cannot originate requets to Lumic API, not authenticated (no token)."
            )
            return None

        self._logger.debug("Query: %s", query)
        self._logger.debug("Vars: %s", vars)

        try:
            access_token = (await self._auth.getToken())["access_token"]
            self._logger.debug("Access Token: %s", access_token)

            transport = AIOHTTPTransport(
                url=API_ENDPOINT,
                headers={"Authorization": "Bearer %s" % access_token},
            )
            session = Client(transport=transport)

            gql_query = gql(query)
            result = await self._hass.async_add_executor_job(session.execute, gql_query, vars)

            return result
        except Exception as e:
            self._logger.error("Error while executing GraphQL query:")
            self._logger.error(e)
            return {}

    async def sleep(self, _time):
        def _sleep():
            time.sleep(_time)
        await self._hass.async_add_executor_job(_sleep)

    async def getHomeDevices(self, _type):
        result = await self._request(QUERY_HOME_DEVICES, {
            "id": self._config.get(CONF_HOME_ID)
        })

        devices = []
        for i in result["homeById"]["devices"]:
            if i["deviceType"] == _type:
                devices.append(i)

        return devices
    
    async def getDeviceById(self, id):
        try:
            result = await self._request(QUERY_DEVICE_BY_ID, {
                "id": id
            })

            return result["deviceById"]
        except Exception as e:
            self._logger.error("Error while executing GraphQL query:")
            self._logger.error(e)
            return None

    async def setDeviceParameter(self, uuid, _type, value):
        try:
            await self._request(MUTATION_DEVICE_PARAMETER_SET, {
                "uuid": uuid,
                "type": _type,
                "value": value,
            })
            return True
        except Exception as e:
            self._logger.error("Error while executing GraphQL mutation:")
            self._logger.error(e)
            return False


class OAuth2Client:
    """Define an OAuth2 client."""

    def __init__(self, hass, config):
        self._oauth = None
        self._token = None
        self._mutex = asyncio.Lock()
        self._hass = hass
        self._config = config
        self._logger = logging.getLogger(__name__ + ":" + self.__class__.__name__)

    async def getToken(self):
        try:
            self._logger.debug("Acquiring lock for OAuth2 client...")
            await self._mutex.acquire()
            self._logger.debug("Acquired lock.")
            config_path = self._hass.config.path(OAUTH2_FILE)
            if os.path.isfile(config_path):
                with open(config_path, "r") as json_file:
                    try:
                        self._token = json.loads(json_file.read())
                    except Exception as e:
                        self._logger.error("Error while reading token file:")
                        self._logger.error(e)
                    finally:
                        json_file.close()

            def fetch_token(oauth):
                print(self._config.get(CONF_CLIENT_ID))
                print(self._config.get(CONF_CLIENT_SECRET))
                auth = HTTPBasicAuth(self._config.get(CONF_CLIENT_ID), self._config.get(CONF_CLIENT_SECRET))
                return oauth.fetch_token(
                    token_url=OAUTH2_TOKEN_URL,
                    auth=auth,
                )

            def refresh_token(oauth):
                auth = HTTPBasicAuth(self._config.get(CONF_CLIENT_ID), self._config.get(CONF_CLIENT_SECRET))
                return oauth.fetch_token(
                    token_url=OAUTH2_TOKEN_URL,
                    auth=auth,
                )

            if self._token is None:
                oauth = OAuth2Session(
                    client=BackendApplicationClient(
                        client_id=self._config.get(CONF_CLIENT_ID)
                    )
                )
                self._token = await self._hass.async_add_executor_job(
                    fetch_token, oauth
                )
            else:
                try:
                    oauth = OAuth2Session(
                        client=BackendApplicationClient(
                            client_id=self._config.get(CONF_CLIENT_ID)
                        ),
                        token=self._token,
                    )
                    self._token = await self._hass.async_add_executor_job(
                        refresh_token, oauth
                    )
                except Exception as e:
                    self._logger.error(
                        "Error while obtaining token via RefreshToken flow, reauthenticating:"
                    )
                    self._logger.error(e)
                    oauth = OAuth2Session(
                        client=BackendApplicationClient(
                            client_id=self._config.get(CONF_CLIENT_ID)
                        )
                    )
                    self._token = await self._hass.async_add_executor_job(
                        fetch_token, oauth
                    )

            with open(self._hass.config.path(OAUTH2_FILE), "w") as json_file:
                json_file.write(json.dumps(self._token))
                json_file.close()

            self._logger.debug("Tokenset: %s", self._token)

            return self._token
        finally:
            self._mutex.release()
            self._logger.debug("Released lock.")
