from .exceptions import WrongRequest, KeyNotFound, NoResponse, UnknownTypeData


def interpret_response(dictionary, key: str = "", return_none=False):
    msg = dictionary.get("msg", None)

    if msg == "success":
        data = dictionary.get("data")
        if type(data) is list:
            return data
        elif type(data) is dict:
            pass
        else:
            raise UnknownTypeData(message=type(data))
        value = data.get(key, None)
        if value is None:
            if return_none:
                return None
            else:
                raise KeyNotFound
        else:
            return value
    elif msg is None:
        raise NoResponse
    else:
        raise Exception(msg)


def get_param(dictionary, key: str, return_none=True):
    value = dictionary.get(key, None)
    if value is None:
        if return_none:
            return None
        else:
            return KeyNotFound
    else:
        return value
