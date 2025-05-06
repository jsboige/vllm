# SPDX-License-Identifier: Apache-2.0

import json
import re
from collections.abc import Sequence
from typing import Union

import partial_json_parser
from partial_json_parser.core.options import Allow

from vllm.entrypoints.openai.protocol import (ChatCompletionRequest,
                                               DeltaFunctionCall, DeltaMessage,
                                               DeltaToolCall,
                                               ExtractedToolCallInformation,
                                               FunctionCall, ToolCall)
from vllm.entrypoints.openai.tool_parsers.abstract_tool_parser import (
    ToolParser, ToolParserManager)
from vllm.logger import init_logger
from vllm.transformers_utils.tokenizer import AnyTokenizer
from vllm.utils import random_uuid

logger = init_logger(__name__)


@ToolParserManager.register_module("qwen3")
class Qwen3ToolParser(ToolParser):

    def __init__(self, tokenizer: AnyTokenizer):
        super().__init__(tokenizer)

        self.current_tool_name_sent: bool = False
        self.prev_tool_call_arr: list[dict] = []
        self.current_tool_id: int = -1
        self.streamed_args_for_tool: list[str] = []

        # Define tokens for tool_call and function_call
        self.tool_call_start_token: str = "<tool_call>"
        self.tool_call_end_token: str = "</tool_call>"
        self.function_call_start_token: str = "<function_call>"
        self.function_call_end_token: str = "</function_call>"

        # Regex to capture both <tool_call> and <function_call>
        self.tool_call_regex = re.compile(
            r"<tool_call>(.*?)</tool_call>|<tool_call>(.*)|<function_call>(.*?)</function_call>|<function_call>(.*)", 
            re.DOTALL)
        self.scratch_pad_regex = re.compile(
            r"<scratch_pad>(.*?)</scratch_pad>", re.DOTALL)

        if not self.model_tokenizer:
            raise ValueError(
                "The model tokenizer must be passed to the ToolParser "
                "constructor during construction.")
        
        # Get token IDs for tool_call and function_call tags
        self.tool_call_start_token_id = self.vocab.get(self.tool_call_start_token)
        self.tool_call_end_token_id = self.vocab.get(self.tool_call_end_token)
        self.function_call_start_token_id = self.vocab.get(self.function_call_start_token)
        self.function_call_end_token_id = self.vocab.get(self.function_call_end_token)
        
        # Check if at least one of the formats is supported
        if ((self.tool_call_start_token_id is None or self.tool_call_end_token_id is None) and
            (self.function_call_start_token_id is None or self.function_call_end_token_id is None)):
            logger.warning(
                "Qwen3 Tool parser could not locate tool call or function call start/end "
                "tokens in the tokenizer! Tool calling may not work properly.")

    def extract_tool_calls(
        self,
        model_output: str,
        request: ChatCompletionRequest,
    ) -> ExtractedToolCallInformation:

        # Check if one of the tool call formats is present
        if (self.tool_call_start_token not in model_output and 
            self.function_call_start_token not in model_output):
            return ExtractedToolCallInformation(tools_called=False,
                                                tool_calls=[],
                                                content=model_output)
        else:
            try:
                # Search for tool calls with both possible formats
                function_call_tuples = self.tool_call_regex.findall(model_output)

                # Process regex results
                raw_function_calls = []
                for match in function_call_tuples:
                    # The regex can capture up to 4 groups (2 formats x 2 cases)
                    content = next((m for m in match if m), None)
                    if content:
                        try:
                            raw_function_calls.append(json.loads(content))
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON in tool call: {e}. Content: {content}")

                tool_calls = []
                for function_call in raw_function_calls:
                    try:
                        tool_calls.append(
                            ToolCall(
                                type="function",
                                function=FunctionCall(
                                    name=function_call["name"],
                                    # function call args are JSON but as a string
                                    arguments=json.dumps(function_call["arguments"],
                                                        ensure_ascii=False)))
                        )
                    except KeyError as e:
                        logger.warning(f"Missing key in function call: {e}. Function call: {function_call}")

                # Determine content before the first tool call
                first_tool_pos = min(
                    model_output.find(self.tool_call_start_token) if self.tool_call_start_token in model_output else float('inf'),
                    model_output.find(self.function_call_start_token) if self.function_call_start_token in model_output else float('inf')
                )
                
                content = model_output[:first_tool_pos] if first_tool_pos != float('inf') else ""
                
                return ExtractedToolCallInformation(
                    tools_called=True,
                    tool_calls=tool_calls,
                    content=content if content else None)

            except Exception as e:
                logger.exception(
                    f"Error in extracting tool call from response: {e}")
                return ExtractedToolCallInformation(tools_called=False,
                                                    tool_calls=[],
                                                    content=model_output)

    def extract_tool_calls_streaming(
        self,
        previous_text: str,
        current_text: str,
        delta_text: str,
        previous_token_ids: Sequence[int],
        current_token_ids: Sequence[int],
        delta_token_ids: Sequence[int],
        request: ChatCompletionRequest,
    ) -> Union[DeltaMessage, None]:

        logger.debug("delta_text: %s", delta_text)
        logger.debug("delta_token_ids: %s", delta_token_ids)
        
        # Check if we have tool call tokens
        has_tool_call_tokens = False
        if self.tool_call_start_token_id is not None:
            has_tool_call_tokens = has_tool_call_tokens or (self.tool_call_start_token_id in current_token_ids)
        if self.function_call_start_token_id is not None:
            has_tool_call_tokens = has_tool_call_tokens or (self.function_call_start_token_id in current_token_ids)
            
        if not has_tool_call_tokens:
            logger.debug("No tool call tokens found!")
            return DeltaMessage(content=delta_text)

        try:
            # Count occurrences of start and end tokens
            prev_tool_start_count = 0
            prev_tool_end_count = 0
            cur_tool_start_count = 0
            cur_tool_end_count = 0
            
            if self.tool_call_start_token_id is not None:
                prev_tool_start_count += previous_token_ids.count(self.tool_call_start_token_id)
                cur_tool_start_count += current_token_ids.count(self.tool_call_start_token_id)
            if self.function_call_start_token_id is not None:
                prev_tool_start_count += previous_token_ids.count(self.function_call_start_token_id)
                cur_tool_start_count += current_token_ids.count(self.function_call_start_token_id)
            
            if self.tool_call_end_token_id is not None:
                prev_tool_end_count += previous_token_ids.count(self.tool_call_end_token_id)
                cur_tool_end_count += current_token_ids.count(self.tool_call_end_token_id)
            if self.function_call_end_token_id is not None:
                prev_tool_end_count += previous_token_ids.count(self.function_call_end_token_id)
                cur_tool_end_count += current_token_ids.count(self.function_call_end_token_id)
            
            tool_call_portion = None
            text_portion = None

            # Case: if we are generating text, OR finishing a tool call
            if (cur_tool_start_count == cur_tool_end_count
                    and prev_tool_end_count == cur_tool_end_count
                    and self.tool_call_end_token not in delta_text
                    and self.function_call_end_token not in delta_text):
                logger.debug("Generating text content! skipping tool parsing.")
                return DeltaMessage(content=delta_text)

            # Case: if we are finishing a tool call
            if self.tool_call_end_token in delta_text or self.function_call_end_token in delta_text:
                logger.debug("tool_call_end_token or function_call_end_token in delta_text")
                full_text = current_text + delta_text
                
                # Find the tool call portion
                if self.tool_call_start_token in full_text and self.tool_call_end_token in delta_text:
                    tool_call_portion = full_text.split(
                        self.tool_call_start_token)[-1].split(
                            self.tool_call_end_token)[0].rstrip()
                    delta_text = delta_text.split(
                        self.tool_call_end_token)[0].rstrip()
                    text_portion = delta_text.split(
                        self.tool_call_end_token)[-1].lstrip()
                elif self.function_call_start_token in full_text and self.function_call_end_token in delta_text:
                    tool_call_portion = full_text.split(
                        self.function_call_start_token)[-1].split(
                            self.function_call_end_token)[0].rstrip()
                    delta_text = delta_text.split(
                        self.function_call_end_token)[0].rstrip()
                    text_portion = delta_text.split(
                        self.function_call_end_token)[-1].lstrip()

            # Flags for partial JSON parsing
            flags = Allow.ALL if self.current_tool_name_sent \
                else Allow.ALL & ~Allow.STR

            # Case: we are starting a new tool call
            if (cur_tool_start_count > cur_tool_end_count
                    and cur_tool_start_count > prev_tool_start_count):
                if len(delta_token_ids) > 1:
                    if self.tool_call_start_token in current_text:
                        tool_call_portion = current_text.split(
                            self.tool_call_start_token)[-1]
                    elif self.function_call_start_token in current_text:
                        tool_call_portion = current_text.split(
                            self.function_call_start_token)[-1]
                else:
                    tool_call_portion = None
                    delta = None

                text_portion = None

                # Update cursors and state
                self.current_tool_id += 1
                self.current_tool_name_sent = False
                self.streamed_args_for_tool.append("")
                logger.debug("Starting on a new tool %s", self.current_tool_id)

            # Case: we are updating an existing tool call
            elif (cur_tool_start_count > cur_tool_end_count
                  and cur_tool_start_count == prev_tool_start_count):

                # Get the text portion that is the tool call
                if self.tool_call_start_token in current_text:
                    tool_call_portion = current_text.split(
                        self.tool_call_start_token)[-1]
                elif self.function_call_start_token in current_text:
                    tool_call_portion = current_text.split(
                        self.function_call_start_token)[-1]
                text_portion = None

            # Case: the current tool call is being closed
            elif (cur_tool_start_count == cur_tool_end_count
                  and cur_tool_end_count >= prev_tool_end_count):
                if (self.prev_tool_call_arr is None
                        or len(self.prev_tool_call_arr) == 0):
                    logger.debug(
                        "attempting to close tool call, but no tool call")
                    return None
                diff = self.prev_tool_call_arr[self.current_tool_id].get(
                    "arguments")
                if diff:
                    diff = diff.encode('utf-8').decode(
                        'unicode_escape') if diff is str else diff
                    if ('"}' not in delta_text):
                        return None
                    end_loc = delta_text.rindex('"}')
                    diff = delta_text[:end_loc] + '"}'
                    logger.debug(
                        "Finishing tool and found diff that had not "
                        "been streamed yet: %s", diff)
                    self.streamed_args_for_tool[self.current_tool_id] \
                        += diff
                    return DeltaMessage(tool_calls=[
                        DeltaToolCall(index=self.current_tool_id,
                                       function=DeltaFunctionCall(
                                           arguments=diff).model_dump(
                                               exclude_none=True))
                    ])

            # Case: otherwise we are simply generating text
            else:
                text = delta_text.replace(self.tool_call_start_token, "")
                text = text.replace(self.tool_call_end_token, "")
                text = text.replace(self.function_call_start_token, "")
                text = text.replace(self.function_call_end_token, "")
                delta = DeltaMessage(tool_calls=[], content=text)
                return delta

            try:
                current_tool_call = partial_json_parser.loads(
                    tool_call_portion or "{}",
                    flags) if tool_call_portion else None
                logger.debug("Parsed tool call %s", current_tool_call)
            except partial_json_parser.core.exceptions.MalformedJSON:
                logger.debug('not enough tokens to parse into JSON yet')
                return None
            except json.decoder.JSONDecodeError:
                logger.debug("unable to parse JSON")
                return None

            # Case - we haven't sent the tool name yet. If it's available, send it.
            # Otherwise, wait until it's available.
            if not self.current_tool_name_sent:
                if (current_tool_call is None):
                    return None
                function_name: Union[str, None] = current_tool_call.get("name")
                if function_name:
                    self.current_tool_name_sent = True
                    return DeltaMessage(tool_calls=[
                        DeltaToolCall(index=self.current_tool_id,
                                       type="function",
                                       id=f"chatcmpl-tool-{random_uuid()}",
                                       function=DeltaFunctionCall(
                                           name=function_name).model_dump(
                                               exclude_none=True))
                    ])
                else:
                    return None
            # Case -- otherwise, send the delta of the tool call

            # If the tool call portion is None, send the delta as text
            if tool_call_portion is None:
                # If there is text but no tool calls, send that -
                # otherwise None to skip the chunk
                delta = DeltaMessage(content=delta_text) \
                    if text_portion is not None else None
                return delta

            # Now, the details of tool calls
            # Now we have the portion to parse as a tool call.

            logger.debug("Trying to parse current tool call with ID %s",
                         self.current_tool_id)

            # If we are starting a new tool call, push an empty object as
            # placeholder for arguments
            if len(self.prev_tool_call_arr) <= self.current_tool_id:
                self.prev_tool_call_arr.append({})

            # Main logic for tool parsing here - compare the previously partially parsed JSON
            # with the currently partially parsed JSON
            prev_arguments = (
                self.prev_tool_call_arr[self.current_tool_id].get("arguments"))
            cur_arguments = current_tool_call.get("arguments")

            logger.debug("diffing old arguments: %s", prev_arguments)
            logger.debug("against new ones: %s", cur_arguments)

            # Case -- no arguments have been created yet. Skip sending a delta.
            if not cur_arguments and not prev_arguments:
                logger.debug("Skipping text %s - no arguments", delta_text)
                delta = None

            # Case -- previous arguments are defined, but none are now.
            # Probably impossible, but not a fatal error - continue
            elif not cur_arguments and prev_arguments:
                logger.error("should be impossible to have arguments reset "
                             "mid-call. skipping streaming anything.")
                delta = None

            # Case -- we now have the first information about available arguments
            # from JSON autocompletion
            elif cur_arguments and not prev_arguments:

                cur_arguments_json = json.dumps(cur_arguments,
                                               ensure_ascii=False)
                logger.debug("finding %s in %s", delta_text,
                             cur_arguments_json)

                # Get the location where previous arguments differ from current ones
                if (delta_text not in cur_arguments_json[:-2]):
                    return None
                args_delta_start_loc = cur_arguments_json[:-2]. \
                                           rindex(delta_text) + \
                                           len(delta_text)

                # Use that to find the actual delta
                arguments_delta = cur_arguments_json[:args_delta_start_loc]
                logger.debug("First tokens in arguments received: %s",
                             arguments_delta)

                delta = DeltaMessage(tool_calls=[
                    DeltaToolCall(index=self.current_tool_id,
                                  function=DeltaFunctionCall(
                                      arguments=arguments_delta).model_dump(
                                          exclude_none=True))
                ])
                self.streamed_args_for_tool[self.current_tool_id] \
                    += arguments_delta

            # Last case -- we have an update to existing arguments.
            elif cur_arguments and prev_arguments:
                if isinstance(delta_text, str) and len(delta_text.rstrip(
                )) >= 1 and delta_text.rstrip()[-1] == '}':
                    delta_text = delta_text.rstrip()[:-1]

                logger.debug("got diff %s", delta_text)

                delta = DeltaMessage(tool_calls=[
                    DeltaToolCall(index=self.current_tool_id,
                                  function=DeltaFunctionCall(
                                      arguments=delta_text).model_dump(
                                          exclude_none=True))
                ])
                self.streamed_args_for_tool[self.current_tool_id] \
                    += delta_text

            # Handle saving the state for the current tool in
            # the "prev" list to use in comparison for the next iteration
            if self.current_tool_id == len(self.prev_tool_call_arr) - 1:
                self.prev_tool_call_arr[self.current_tool_id] = \
                    current_tool_call
            else:
                self.prev_tool_call_arr.append(current_tool_call)

            return delta

        except Exception as e:
            logger.exception("Error trying to handle streaming tool call: %s", e)
            return None  # don't stream delta. skip this token ID.