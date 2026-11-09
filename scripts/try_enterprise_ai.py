"""Run a synthetic travel-policy question using an existing OCI GenAI project.

Install openai and oci-genai-auth in a separate virtual environment first.
Uses ~/.oci/config and never prints authentication material.
The optional code interpreter can create a temporary OCI container.
"""

import argparse
import json
from pathlib import Path

import httpx
from oci_genai_auth import OciUserPrincipalAuth
from openai import APIStatusError, OpenAI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--model", default="google.gemini-2.5-flash-lite")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--code-interpreter", action="store_true")
    args = parser.parse_args()
    with OpenAI(
        base_url=f"https://inference.generativeai.{args.region}.oci.oraclecloud.com/openai/v1",
        api_key="not-used",
        project=args.project,
        max_retries=0,
        timeout=45,
        http_client=httpx.Client(auth=OciUserPrincipalAuth(
            config_file=str(Path.home() / ".oci/config"), profile_name="DEFAULT"
        )),
    ) as client:
        try:
            options = {}
            if args.code_interpreter:
                options = {
                    "tools": [{"type": "code_interpreter", "container": {"type": "auto", "memory_limit": "1g"}}],
                    "instructions": "Use the python tool to calculate the answer. Then explain briefly in Korean.",
                    "include": ["code_interpreter_call.outputs"],
                    "tool_choice": "required",
                }
            response = client.responses.create(
                model=args.model,
                input=("테스트용 가상 출장 규정: 국내 숙박비는 1박당 최대 100,000원. "
                       "식비와 교통비 제외. 부산 2박 3일 출장의 숙박비 한도는? "
                       "계산식을 포함하여 한국어 한 문장으로 답하세요."),
                max_output_tokens=256,
                store=False,
                **options,
            )
        except APIStatusError as error:
            print(json.dumps({"status": error.status_code, "error": error.body}, ensure_ascii=False))
            return 1
        result = {
            "model": response.model,
            "status": response.status,
            "output_text": response.output_text,
            "usage": response.usage.model_dump() if response.usage else None,
            "output": [item.model_dump() for item in response.output],
        }
        if args.output:
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        calls = [item for item in response.output if item.type == "code_interpreter_call"]
        tool_ok = not args.code_interpreter or any(
            item.status == "completed" and item.outputs for item in calls
        )
        return 0 if response.status == "completed" and response.output_text and tool_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
