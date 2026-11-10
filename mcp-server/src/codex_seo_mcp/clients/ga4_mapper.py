from __future__ import annotations

import re

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class Ga4AdminMapper:
    """Convert GA4 Admin API payloads into the small structures used by the plugin."""

    def map_properties(self, payload: dict[str, object]) -> list[dict[str, str]]:
        properties: list[dict[str, str]] = []
        accounts = _optional_list(payload, "accountSummaries")
        for account_index, account in enumerate(accounts):
            if not isinstance(account, dict):
                raise _invalid_response(
                    f"GA4 accountSummaries[{account_index}] 不是对象"
                )
            account_id = _resource_id(account.get("account"), "accounts/")
            if not account_id:
                raise _invalid_response(
                    f"GA4 accountSummaries[{account_index}].account 资源标识格式无效"
                )
            account_name = str(account.get("displayName") or "")
            summaries = _optional_list(account, "propertySummaries")
            for property_index, item in enumerate(summaries):
                if not isinstance(item, dict):
                    raise _invalid_response(
                        "GA4 "
                        f"accountSummaries[{account_index}].propertySummaries[{property_index}] "
                        "不是对象"
                    )
                property_id = _resource_id(item.get("property"), "properties/")
                if not property_id:
                    raise _invalid_response(
                        "GA4 "
                        f"accountSummaries[{account_index}].propertySummaries[{property_index}] "
                        "property 资源标识格式无效"
                    )
                properties.append(
                    {
                        "property_id": property_id,
                        "property_name": str(item.get("displayName") or ""),
                        "account_id": account_id,
                        "account_name": account_name,
                    }
                )
        return properties

    def map_data_streams(
        self, payload: dict[str, object], *, property_id: str,
    ) -> list[dict[str, str]]:
        streams: list[dict[str, str]] = []
        items = _optional_list(payload, "dataStreams")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise _invalid_response(f"GA4 dataStreams[{index}] 不是对象")
            web_data = item.get("webStreamData")
            stream_type = str(item.get("type") or "")
            if stream_type == "WEB_DATA_STREAM" and not isinstance(web_data, dict):
                raise _invalid_response(
                    f"GA4 dataStreams[{index}] 是 WEB_DATA_STREAM 但缺少 webStreamData"
                )
            if not isinstance(web_data, dict):
                web_data = {}

            stream_name = item.get("name")
            stream_match = (
                re.fullmatch(r"properties/([0-9]+)/dataStreams/([0-9]+)", stream_name)
                if isinstance(stream_name, str) else None
            )
            if stream_match is None:
                raise _invalid_response(f"GA4 dataStreams[{index}].name 资源标识格式无效")
            if stream_match.group(1) != property_id:
                raise _invalid_response(f"GA4 dataStreams[{index}].name 不属于请求的媒体资源")
            stream_id = stream_match.group(2)

            streams.append(
                {
                    "data_stream_id": stream_id,
                    "display_name": str(item.get("displayName") or ""),
                    "type": stream_type,
                    "measurement_id": str(web_data.get("measurementId") or ""),
                    "default_uri": str(web_data.get("defaultUri") or ""),
                }
            )
        return streams


def _resource_id(value: object, prefix: str) -> str:
    # 资源路径是身份依据，不接受裸 ID、错误前缀或由对象强制转换出的文本。
    if not isinstance(value, str):
        return ""
    match = re.fullmatch(re.escape(prefix) + r"([0-9]+)", value)
    return match.group(1) if match else ""


def _optional_list(payload: dict[str, object], field: str) -> list[object]:
    raw = payload.get(field)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _invalid_response(f"GA4 {field} 不是数组")
    return raw


def _invalid_response(message: str) -> SeoDataError:
    return SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, message)
