"""Constants for the Lumic Lighting integration."""

DOMAIN = "lumic"

API_ENDPOINT = "https://lumic-v1.apis.cedgetec.com/gql/graphql"

OAUTH2_TOKEN_URL = (
    "https://auth.cedgetec.com/auth/realms/cedgetec-id/protocol/openid-connect/token"
)
OAUTH2_CALLBACK_PATH = "/api/lumic"
OAUTH2_SCOPE = ["lumic", "offline_access"]
OAUTH2_FILE = ".lumic_oauth2.json"

CONF_HOME_ID = "home_id"

ATTR_DEVICE_TYPE_LIGHT = "LIGHT"
ATTR_DEVICE_TYPE_SWITCH = "SWITCH"
ATTR_DEVICE_TYPE_COVER = "ROLLER_SHUTTER"

QUERY_HOME_DEVICES = """
query get_home_devices($id: Float!) {
    homeById(id: $id) {
        devices {
            id
            uuid
            name
            hardwareAddress
            deviceType
            room {
                name
            }
        }
    }
}
"""

QUERY_DEVICE_BY_ID = """
query get_device_by_id($id: Float!) {
    deviceById(id: $id) {
        uuid
        name
        hardwareAddress
        deviceType
        room {
            name
        }
        deviceParameters {
            type
            valueType
            value
            valueNumeric
        }
    }
}
"""

MUTATION_DEVICE_PARAMETER_SET = """
mutation device_parameter_set($uuid: String!, $type: ParameterType!, $value: String!) {
    deviceParameterSet(uuid: $uuid, type: $type, value: $value)
}
"""
