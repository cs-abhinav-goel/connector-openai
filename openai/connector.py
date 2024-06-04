"""
Copyright start
MIT License
Copyright (c) 2024 Fortinet Inc
Copyright end
"""
from connectors.core.connector import Connector, ConnectorError
from .builtins import *
from .constants import LOGGER_NAME
from .operations import check
logger = get_logger(LOGGER_NAME)


class Openai(Connector):

    def execute(self, config, operation, params, *args, **kwargs):
        try:
            if operation in ['chat_conversation', 'chat_completions']:
                params.update({'operation': operation})
            elif operation == 'create_speech':
                return supported_operations.get(operation)(config, params, *args, **kwargs)
            return supported_operations.get(operation)(config, params)
        except Exception as err:
            logger.exception(err)
            raise ConnectorError("Message: {0}".format(err))

    def check_health(self, config=None, *args, **kwargs):
        return check(config)
