"""
Copyright start
MIT License
Copyright (c) 2024 Fortinet Inc
Copyright end
"""
from typing_extensions import override
from openai import AssistantEventHandler
from openai.types.beta.threads.runs import RunStepDelta
from openai.types.beta.threads import Message, MessageDelta
from openai.types.beta.threads.runs import ToolCall, RunStep
from openai.types.beta import AssistantStreamEvent
from .operations import *
from .utils import execute_connector_action

logger = get_logger(LOGGER_NAME)


class EventHandler(AssistantEventHandler):
    def __init__(self, config, params):
        super().__init__()
        self.run_id = None
        self.llm_response = ""
        self.config = config
        self.params = params
        self.tool_outputs = []
        self.usage = {}

    # Executes on every event
    @override
    def on_event(self, event: AssistantStreamEvent) -> None:
        logger.info(f'event: {event.event}')

    # thread.run.step.created
    @override
    def on_run_step_created(self, run_step: RunStep) -> None:
        self.run_id = run_step.run_id

    # thread.run.step.delta
    @override
    def on_run_step_delta(self, delta: RunStepDelta, snapshot: RunStep):
        pass

    # thread.run.step.delta
    @override
    def on_run_step_done(self, run_step: RunStep) -> None:
        self.usage = run_step.usage

    # thread.message.created
    @override
    def on_message_created(self, message: Message) -> None:
        pass

    # thread.message.delta
    @override
    def on_message_delta(self, delta: MessageDelta, snapshot: Message) -> None:
        pass

    # thread.message.completed
    @override
    def on_message_done(self, message: Message) -> None:
        self.llm_response = message.content[0].text.value

    @override
    def on_tool_call_created(self, tool_call):
        pass

    @override
    def on_tool_call_delta(self, delta, snapshot):
        pass

    @override
    def on_tool_call_done(self, tool_call: ToolCall) -> None:
        if tool_call.type == 'function':
            run_status = get_run(config=self.config,
                                 params={'thread_id': self.params['threadId'], 'run_id': self.run_id})
            while run_status['status'] in ["queued", "in_progress"]:
                run_status = get_run(config=self.config,
                                     params={'thread_id': self.params['threadId'], 'run_id': self.run_id})
            if run_status['status'] == "requires_action":
                logger.info(f'Calling tool function, Function Name: {tool_call.function.name}, Function Argument: {tool_call.function.arguments}')
                to_add_message, function_output = self.call_required_function(tool_call.function.name,
                                                                              tool_call.function.arguments)
                logger.error(f'Function Calling output: {function_output}')
                if to_add_message:
                    self.tool_outputs.append({"tool_call_id": tool_call.id, "output": function_output})
                else:
                    cancel_run(config=self.config, params={'thread_id': self.params['threadId'], 'run_id': self.run_id})
                    create_thread_message(self.config,
                                          params={'thread_id': self.params['threadId'], 'role': 'assistant',
                                                  'content': function_output})

    @override
    def on_end(self):
        client = openai.OpenAI(api_key=self.config['apiKey'], project=self.config.get('project'), organization=self.config.get('organization'))
        run_status = client.beta.threads.runs.retrieve(
            run_id=self.run_id,
            thread_id=self.params['threadId']
        )
        if run_status.status == 'requires_action':
            with client.beta.threads.runs.submit_tool_outputs_stream(
                    thread_id=self.params['threadId'],
                    run_id=self.run_id,
                    tool_outputs=self.tool_outputs,
                    event_handler=EventHandler(self.config, self.params)
            ) as stream:
                stream.until_done()
        while run_status.status not in ['completed', 'cancelled']:
            run_status = client.beta.threads.runs.retrieve(
                run_id=self.run_id,
                thread_id=self.params['threadId']
            )
        thread_messages = list_thread_messages(config=self.config, params={'thread_id': self.params['threadId']})
        self.llm_response = thread_messages['data'][0]['content'][0]['text']['value']

    @override
    def on_exception(self, exception: Exception) -> None:
        logger.error(f"Exception: {exception}\n", end="", flush=True)

    def get_resposne(self):
        return self.llm_response

    def call_required_function(self, function_name, arguments):
        try:
            payload = {"connector_name": 'openai', "config_id": self.config['config_id'],
                       "function_name": function_name, "arguments": arguments,
                       "ioc_data": self.params['ioc_data'],
                       "auth_token": self.params['authToken'],
                       "recordIRI": self.params['recordIRI'],
                       "record_data": self.params['record_data']}
            response = execute_connector_action(None, 'aiassistant-utils', 'tool_function_caller', payload)
            to_add_message = response['data'].get('to_add_message')
            data = response['data'].get('data')
            if response.get('status') == 'Success':
                return to_add_message, data
            return True, response.get('message', 'Unknown error')
        except Exception as error:
            return True, f'Error: {error}'