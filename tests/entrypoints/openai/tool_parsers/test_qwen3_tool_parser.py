# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from tests.entrypoints.openai.tool_parsers.utils import (
    run_tool_extraction, run_tool_extraction_streaming)
from vllm.entrypoints.openai.protocol import FunctionCall
from vllm.entrypoints.openai.tool_parsers import ToolParser, ToolParserManager

# Format des appels d'outils pour Qwen3
TOOL_CALL_FORMAT = '<tool_call>{{"name": "{name}", "arguments": {arguments}}}</tool_call>'
FUNCTION_CALL_FORMAT = '<function_call>{{"name": "{name}", "arguments": {arguments}}}</function_call>'

# Cas de test simples
SIMPLE_TOOL_CALL = TOOL_CALL_FORMAT.format(
    name="get_weather",
    arguments='{"city": "San Francisco", "metric": "celsius"}'
)
SIMPLE_FUNCTION_CALL = FUNCTION_CALL_FORMAT.format(
    name="get_weather",
    arguments='{"city": "San Francisco", "metric": "celsius"}'
)
SIMPLE_FUNCTION_CALL_OBJ = FunctionCall(
    name="get_weather",
    arguments='{"city": "San Francisco", "metric": "celsius"}',
)

# Cas de test avec différents types de données
COMPLEX_TOOL_CALL = TOOL_CALL_FORMAT.format(
    name="register_user",
    arguments='{"name": "John Doe", "age": 37, "address": {"city": "San Francisco", "state": "CA"}, "role": null, "passed_test": true, "aliases": ["John", "Johnny"]}'
)
COMPLEX_FUNCTION_CALL = FUNCTION_CALL_FORMAT.format(
    name="register_user",
    arguments='{"name": "John Doe", "age": 37, "address": {"city": "San Francisco", "state": "CA"}, "role": null, "passed_test": true, "aliases": ["John", "Johnny"]}'
)
COMPLEX_FUNCTION_CALL_OBJ = FunctionCall(
    name="register_user",
    arguments='{"name": "John Doe", "age": 37, "address": {"city": "San Francisco", "state": "CA"}, "role": null, "passed_test": true, "aliases": ["John", "Johnny"]}',
)

# Cas de test sans paramètres
PARAMETERLESS_TOOL_CALL = TOOL_CALL_FORMAT.format(
    name="get_weather",
    arguments='{}'
)
PARAMETERLESS_FUNCTION_CALL = FUNCTION_CALL_FORMAT.format(
    name="get_weather",
    arguments='{}'
)
PARAMETERLESS_FUNCTION_CALL_OBJ = FunctionCall(
    name="get_weather",
    arguments='{}',
)


@pytest.mark.parametrize("streaming", [True, False])
def test_no_tool_call(streaming: bool):
    mock_tokenizer = MagicMock()
    # Configurer le mock pour simuler les tokens spéciaux
    mock_tokenizer.tokenize.return_value = []
    mock_vocab = {"<tool_call>": 1, "</tool_call>": 2, "<function_call>": 3, "</function_call>": 4}
    mock_tokenizer.get_vocab.return_value = mock_vocab
    
    tool_parser: ToolParser = ToolParserManager.get_tool_parser("qwen3")(
        mock_tokenizer)
    
    # Simuler les IDs de tokens
    tool_parser.tool_call_start_token_id = 1
    tool_parser.tool_call_end_token_id = 2
    tool_parser.function_call_start_token_id = 3
    tool_parser.function_call_end_token_id = 4
    tool_parser.vocab = mock_vocab
    
    model_output = "Comment puis-je vous aider aujourd'hui ?"

    content, tool_calls = run_tool_extraction(tool_parser,
                                             model_output,
                                             streaming=streaming)

    assert content == model_output
    assert len(tool_calls) == 0


TEST_CASES = [
    pytest.param(True,
                 SIMPLE_TOOL_CALL, [SIMPLE_FUNCTION_CALL_OBJ],
                 id="simple_tool_call_streaming"),
    pytest.param(False,
                 SIMPLE_TOOL_CALL, [SIMPLE_FUNCTION_CALL_OBJ],
                 id="simple_tool_call_nonstreaming"),
    pytest.param(True,
                 SIMPLE_FUNCTION_CALL, [SIMPLE_FUNCTION_CALL_OBJ],
                 id="simple_function_call_streaming"),
    pytest.param(False,
                 SIMPLE_FUNCTION_CALL, [SIMPLE_FUNCTION_CALL_OBJ],
                 id="simple_function_call_nonstreaming"),
    pytest.param(True,
                 COMPLEX_TOOL_CALL, [COMPLEX_FUNCTION_CALL_OBJ],
                 id="complex_tool_call_streaming"),
    pytest.param(False,
                 COMPLEX_TOOL_CALL, [COMPLEX_FUNCTION_CALL_OBJ],
                 id="complex_tool_call_nonstreaming"),
    pytest.param(True,
                 COMPLEX_FUNCTION_CALL, [COMPLEX_FUNCTION_CALL_OBJ],
                 id="complex_function_call_streaming"),
    pytest.param(False,
                 COMPLEX_FUNCTION_CALL, [COMPLEX_FUNCTION_CALL_OBJ],
                 id="complex_function_call_nonstreaming"),
    pytest.param(True,
                 PARAMETERLESS_TOOL_CALL, [PARAMETERLESS_FUNCTION_CALL_OBJ],
                 id="parameterless_tool_call_streaming"),
    pytest.param(False,
                 PARAMETERLESS_TOOL_CALL, [PARAMETERLESS_FUNCTION_CALL_OBJ],
                 id="parameterless_tool_call_nonstreaming"),
    pytest.param(True,
                 PARAMETERLESS_FUNCTION_CALL, [PARAMETERLESS_FUNCTION_CALL_OBJ],
                 id="parameterless_function_call_streaming"),
    pytest.param(False,
                 PARAMETERLESS_FUNCTION_CALL, [PARAMETERLESS_FUNCTION_CALL_OBJ],
                 id="parameterless_function_call_nonstreaming"),
    pytest.param(True,
                 f"Voici la météo : {SIMPLE_TOOL_CALL}", [SIMPLE_FUNCTION_CALL_OBJ],
                 id="tool_call_with_prefix_streaming"),
    pytest.param(False,
                 f"Voici la météo : {SIMPLE_TOOL_CALL}", [SIMPLE_FUNCTION_CALL_OBJ],
                 id="tool_call_with_prefix_nonstreaming"),
    pytest.param(True,
                 f"{SIMPLE_TOOL_CALL} Voici les informations demandées.", [SIMPLE_FUNCTION_CALL_OBJ],
                 id="tool_call_with_suffix_streaming"),
    pytest.param(False,
                 f"{SIMPLE_TOOL_CALL} Voici les informations demandées.", [SIMPLE_FUNCTION_CALL_OBJ],
                 id="tool_call_with_suffix_nonstreaming"),
    pytest.param(True,
                 f"Voici la météo : {SIMPLE_TOOL_CALL} et l'utilisateur : {COMPLEX_TOOL_CALL}",
                 [SIMPLE_FUNCTION_CALL_OBJ, COMPLEX_FUNCTION_CALL_OBJ],
                 id="multiple_tool_calls_streaming"),
    pytest.param(False,
                 f"Voici la météo : {SIMPLE_TOOL_CALL} et l'utilisateur : {COMPLEX_TOOL_CALL}",
                 [SIMPLE_FUNCTION_CALL_OBJ, COMPLEX_FUNCTION_CALL_OBJ],
                 id="multiple_tool_calls_nonstreaming"),
]


@pytest.mark.parametrize("streaming, model_output, expected_tool_calls",
                         TEST_CASES)
def test_tool_call(streaming: bool, model_output: str,
                  expected_tool_calls: list[FunctionCall]):
    mock_tokenizer = MagicMock()
    # Configurer le mock pour simuler les tokens spéciaux
    mock_tokenizer.tokenize.return_value = []
    mock_vocab = {"<tool_call>": 1, "</tool_call>": 2, "<function_call>": 3, "</function_call>": 4}
    mock_tokenizer.get_vocab.return_value = mock_vocab
    
    tool_parser: ToolParser = ToolParserManager.get_tool_parser("qwen3")(
        mock_tokenizer)
    
    # Simuler les IDs de tokens
    tool_parser.tool_call_start_token_id = 1
    tool_parser.tool_call_end_token_id = 2
    tool_parser.function_call_start_token_id = 3
    tool_parser.function_call_end_token_id = 4
    tool_parser.vocab = mock_vocab

    content, tool_calls = run_tool_extraction(tool_parser,
                                             model_output,
                                             streaming=streaming)

    if "<tool_call>" not in model_output and "<function_call>" not in model_output:
        assert content == model_output
        assert len(tool_calls) == 0
        return

    # Vérifier que le contenu est extrait correctement
    if "<tool_call>" in model_output:
        prefix = model_output.split("<tool_call>")[0]
        if prefix:
            assert content == prefix.strip()
        else:
            assert content is None or content == ""
    elif "<function_call>" in model_output:
        prefix = model_output.split("<function_call>")[0]
        if prefix:
            assert content == prefix.strip()
        else:
            assert content is None or content == ""

    # Vérifier les appels d'outils
    assert len(tool_calls) == len(expected_tool_calls)
    for actual, expected in zip(tool_calls, expected_tool_calls):
        assert actual.type == "function"
        assert actual.function.name == expected.name
        # Comparer les arguments JSON (en ignorant les différences de formatage)
        import json
        actual_args = json.loads(actual.function.arguments)
        expected_args = json.loads(expected.arguments)
        assert actual_args == expected_args


def test_streaming_tool_call_with_large_steps():
    mock_tokenizer = MagicMock()
    # Configurer le mock pour simuler les tokens spéciaux
    mock_tokenizer.tokenize.return_value = []
    mock_vocab = {"<tool_call>": 1, "</tool_call>": 2, "<function_call>": 3, "</function_call>": 4}
    mock_tokenizer.get_vocab.return_value = mock_vocab
    
    tool_parser: ToolParser = ToolParserManager.get_tool_parser("qwen3")(
        mock_tokenizer)
    
    # Simuler les IDs de tokens
    tool_parser.tool_call_start_token_id = 1
    tool_parser.tool_call_end_token_id = 2
    tool_parser.function_call_start_token_id = 3
    tool_parser.function_call_end_token_id = 4
    tool_parser.vocab = mock_vocab
    
    model_output_deltas = [
        "Voici la météo : <tool_call>{\"name\": \"get_weather\", \"arguments\": {\"city\": \"San",
        " Francisco\", \"metric\": \"celsius\"}}</tool_call>"
    ]

    reconstructor = run_tool_extraction_streaming(
        tool_parser, model_output_deltas, assert_one_tool_per_delta=False)

    assert "Voici la météo : " in reconstructor.other_content
    assert len(reconstructor.tool_calls) == 1
    assert reconstructor.tool_calls[0].function.name == "get_weather"
    assert "San Francisco" in reconstructor.tool_calls[0].function.arguments
    assert "celsius" in reconstructor.tool_calls[0].function.arguments