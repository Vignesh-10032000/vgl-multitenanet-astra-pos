"""Provider-neutral IRP contract and environment-configured NIC adapter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from vglpos.extensions import cache

logger = logging.getLogger(__name__)


class IRPClientError(Exception):
    """Base typed provider failure with an optional stable provider code."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class IRPTransientError(IRPClientError):
    """Provider or network failure that can safely be retried."""


class IRPPermanentError(IRPClientError):
    """Provider rejection that requires corrected business data."""


@dataclass(frozen=True, slots=True)
class IRPInvoiceResult:
    irn: str
    ack_number: str
    ack_date: datetime
    signed_invoice: str
    signed_qr_code: str
    raw_json: str
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class IRPCancelResult:
    cancelled_at: datetime
    raw_json: str


@dataclass(frozen=True, slots=True)
class IRPEWayBillResult:
    number: str
    generated_at: datetime
    valid_until: datetime | None
    raw_json: str


class IRPClient(Protocol):
    """Provider-agnostic operations used by durable compliance services."""

    def generate_invoice(self, payload_json: str) -> IRPInvoiceResult:
        """Generate or recover an existing IRN for one validated invoice."""

    def cancel_invoice(self, *, gstin: str, irn: str, reason: str) -> IRPCancelResult:
        """Cancel a generated IRN within the statutory window."""

    def generate_eway_bill(self, payload_json: str) -> IRPEWayBillResult:
        """Generate an e-way bill for an applicable outward consignment."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes


class JsonTransport(Protocol):
    def post(self, url: str, *, headers: dict[str, str], body: bytes) -> HttpResponse:
        """POST raw JSON and return the status and body without interpreting it."""


class UrllibJsonTransport:
    """Small standard-library HTTPS transport suitable for Celery workers."""

    def post(self, url: str, *, headers: dict[str, str], body: bytes) -> HttpResponse:
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=30) as response:
                return HttpResponse(response.status, response.read())
        except HTTPError as exc:
            response_body = exc.read()
            if exc.code >= 500:
                raise IRPTransientError(f"IRP returned HTTP {exc.code}.") from exc
            return HttpResponse(exc.code, response_body)
        except (TimeoutError, URLError, OSError) as exc:
            raise IRPTransientError("IRP is unreachable.") from exc


class TokenStore(Protocol):
    def get(self, key: str) -> str | None:
        """Return a cached authentication token."""

    def set(self, key: str, value: str, timeout: int) -> None:
        """Cache a token for fewer seconds than the provider expiry."""

    def delete(self, key: str) -> None:
        """Invalidate a rejected token before one authentication retry."""


class FlaskTokenStore:
    """Use the configured Redis/SimpleCache backend for IRP auth tokens."""

    def get(self, key: str) -> str | None:
        value = cache.get(key)
        return value if isinstance(value, str) else None

    def set(self, key: str, value: str, timeout: int) -> None:
        cache.set(key, value, timeout=timeout)

    def delete(self, key: str) -> None:
        cache.delete(key)


@dataclass(frozen=True, slots=True)
class NICConfig:
    auth_url: str
    generate_url: str
    lookup_url: str
    cancel_url: str
    eway_url: str
    username: str
    password: str
    client_id: str
    client_secret: str

    def validate(self) -> None:
        """Fail before I/O when the selected provider lacks required deployment config."""
        values = {
            "IRP_NIC_AUTH_URL": self.auth_url,
            "IRP_NIC_GENERATE_URL": self.generate_url,
            "IRP_NIC_LOOKUP_URL": self.lookup_url,
            "IRP_NIC_CANCEL_URL": self.cancel_url,
            "IRP_NIC_EWAY_URL": self.eway_url,
            "IRP_NIC_USERNAME": self.username,
            "IRP_NIC_PASSWORD": self.password,
            "IRP_NIC_CLIENT_ID": self.client_id,
            "IRP_NIC_CLIENT_SECRET": self.client_secret,
        }
        missing = sorted(name for name, value in values.items() if not value.strip())
        if missing:
            raise IRPPermanentError(f"NIC IRP is not configured: {', '.join(missing)}.")


class NICIRPClient:
    """NIC-compatible adapter with cached authentication and token refresh."""

    _TOKEN_ERROR_CODES = frozenset({"1005", "3028", "AUTH_TOKEN_EXPIRED"})
    _DUPLICATE_CODES = frozenset({"2150", "2172", "2295", "DUPLICATE_IRN"})

    def __init__(
        self,
        config: NICConfig,
        *,
        transport: JsonTransport | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.transport = transport or UrllibJsonTransport()
        self.token_store = token_store or FlaskTokenStore()

    def generate_invoice(self, payload_json: str) -> IRPInvoiceResult:
        gstin = self._gstin(payload_json, "SellerDtls", "Gstin")
        response = self._authorized_post(self.config.generate_url, gstin, payload_json)
        code, message = self._error(response)
        duplicate = code in self._DUPLICATE_CODES
        data = self._data(response)
        if code and not duplicate:
            raise self._remote_error(code, message)
        if duplicate and not self._find(data, "Irn"):
            document = self._document_reference(payload_json)
            lookup = self._authorized_post(
                self.config.lookup_url,
                gstin,
                json.dumps(document, separators=(",", ":")),
            )
            lookup_code, lookup_message = self._error(lookup)
            if lookup_code:
                raise self._remote_error(lookup_code, lookup_message)
            data = self._data(lookup)
            response = lookup
            if not self._find(data, "Irn"):
                raise IRPTransientError(
                    "IRP reported a duplicate but lookup did not return the existing IRN.",
                    code=code,
                )
        try:
            return IRPInvoiceResult(
                irn=str(self._required(data, "Irn")),
                ack_number=str(self._required(data, "AckNo")),
                ack_date=self._datetime(self._required(data, "AckDt")),
                signed_invoice=str(self._required(data, "SignedInvoice")),
                signed_qr_code=str(self._required(data, "SignedQRCode")),
                raw_json=self._raw(response),
                duplicate=duplicate,
            )
        except (TypeError, ValueError) as exc:
            raise IRPTransientError("IRP returned an incomplete invoice response.") from exc

    def cancel_invoice(self, *, gstin: str, irn: str, reason: str) -> IRPCancelResult:
        payload = json.dumps({"Irn": irn, "CnlRsn": "4", "CnlRem": reason}, separators=(",", ":"))
        response = self._authorized_post(self.config.cancel_url, gstin, payload)
        code, message = self._error(response)
        if code:
            raise self._remote_error(code, message)
        data = self._data(response)
        value = self._find(data, "CancelDate") or self._find(data, "CnlDt")
        return IRPCancelResult(
            cancelled_at=self._datetime(value or datetime.now(UTC).isoformat()),
            raw_json=self._raw(response),
        )

    def generate_eway_bill(self, payload_json: str) -> IRPEWayBillResult:
        gstin = self._gstin(payload_json, "fromGstin")
        response = self._authorized_post(self.config.eway_url, gstin, payload_json)
        code, message = self._error(response)
        if code:
            raise self._remote_error(code, message)
        data = self._data(response)
        generated = self._find(data, "ewayBillDate") or self._find(data, "EwbDt")
        valid = self._find(data, "validUpto") or self._find(data, "EwbValidTill")
        number = self._find(data, "ewayBillNo") or self._find(data, "EwbNo")
        if number is None or generated is None:
            raise IRPTransientError("IRP returned an incomplete e-way bill response.")
        return IRPEWayBillResult(
            number=str(number),
            generated_at=self._datetime(generated),
            valid_until=self._datetime(valid) if valid is not None else None,
            raw_json=self._raw(response),
        )

    def _authorized_post(self, url: str, gstin: str, payload_json: str) -> dict[str, Any]:
        for refresh in (False, True):
            token = self._token(gstin, force_refresh=refresh)
            response = self._post(
                url,
                payload_json.encode("utf-8"),
                {
                    "Content-Type": "application/json",
                    "auth-token": token,
                    "gstin": gstin,
                    "client-id": self.config.client_id,
                    "client-secret": self.config.client_secret,
                },
            )
            code, _message = self._error(response)
            if code not in self._TOKEN_ERROR_CODES:
                return response
            self.token_store.delete(self._token_key(gstin))
        raise IRPTransientError("IRP authentication token was rejected after refresh.")

    def _token(self, gstin: str, *, force_refresh: bool) -> str:
        key = self._token_key(gstin)
        if not force_refresh:
            cached = self.token_store.get(key)
            if cached:
                return cached
        body = json.dumps(
            {
                "username": self.config.username,
                "password": self.config.password,
                "gstin": gstin,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        response = self._post(self.config.auth_url, body, {"Content-Type": "application/json"})
        code, message = self._error(response)
        if code:
            raise self._remote_error(code, message)
        data = self._data(response)
        token = self._find(data, "AuthToken") or self._find(data, "auth_token")
        if not isinstance(token, str) or not token:
            raise IRPTransientError("IRP authentication response omitted the token.")
        expiry_value = self._find(data, "TokenExpiry") or self._find(data, "expires_in") or 21600
        try:
            timeout = max(60, int(str(expiry_value)) - 60)
        except ValueError:
            timeout = 21_540
        self.token_store.set(key, token, timeout)
        return token

    def _post(self, url: str, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        response = self.transport.post(url, headers=headers, body=body)
        if response.status >= 500:
            raise IRPTransientError(f"IRP returned HTTP {response.status}.")
        try:
            value = json.loads(response.body.decode("utf-8"), parse_float=Decimal)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IRPTransientError("IRP returned malformed JSON.") from exc
        if not isinstance(value, dict):
            raise IRPTransientError("IRP returned a non-object JSON response.")
        return cast(dict[str, Any], value)

    @classmethod
    def _data(cls, response: dict[str, Any]) -> dict[str, Any]:
        value = response.get("Data", response.get("data", response))
        if isinstance(value, str):
            try:
                decoded = json.loads(value, parse_float=Decimal)
            except json.JSONDecodeError:
                return response
            return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else response
        return cast(dict[str, Any], value) if isinstance(value, dict) else response

    @classmethod
    def _error(cls, response: dict[str, Any]) -> tuple[str | None, str]:
        details = response.get("ErrorDetails") or response.get("error")
        if isinstance(details, list) and details:
            details = details[0]
        if isinstance(details, dict):
            code = details.get("ErrorCode") or details.get("errorCodes") or details.get("code")
            message = details.get("ErrorMessage") or details.get("message") or str(details)
            return (str(code) if code is not None else None, str(message))
        status = response.get("Status", response.get("status"))
        if str(status).lower() in {"0", "false", "failed"}:
            code = response.get("ErrorCode", response.get("error_code", "IRP_REJECTED"))
            message = response.get("ErrorMessage", response.get("message", "IRP rejected request."))
            return str(code), str(message)
        return None, ""

    @staticmethod
    def _remote_error(code: str, message: str) -> IRPClientError:
        transient_codes = {"1001", "1002", "500", "503", "TIMEOUT", "SERVICE_UNAVAILABLE"}
        if code in transient_codes:
            return IRPTransientError(message or "IRP temporary failure.", code=code)
        return IRPPermanentError(message or "IRP rejected request.", code=code)

    @classmethod
    def _required(cls, value: dict[str, Any], key: str) -> object:
        found = cls._find(value, key)
        if found is None:
            raise ValueError(f"Missing {key}")
        return found

    @classmethod
    def _find(cls, value: object, key: str) -> object | None:
        if isinstance(value, dict):
            if key in value:
                return cast(object, value[key])
            for nested in value.values():
                found = cls._find(nested, key)
                if found is not None:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = cls._find(nested, key)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _datetime(value: object) -> datetime:
        text = str(value).strip()
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            formats = (
                "%d/%m/%Y %I:%M:%S %p",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %I.%M:%S %p",
            )
            for pattern in formats:
                try:
                    parsed = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Invalid provider datetime")
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _raw(response: dict[str, Any]) -> str:
        return json.dumps(response, default=str, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _gstin(payload_json: str, *path: str) -> str:
        try:
            current: object = json.loads(payload_json, parse_float=Decimal)
            for key in path:
                if not isinstance(current, dict):
                    raise KeyError(key)
                current = current[key]
        except (json.JSONDecodeError, KeyError) as exc:
            raise IRPPermanentError(
                "Validated payload does not contain the supplier GSTIN."
            ) from exc
        if not isinstance(current, str):
            raise IRPPermanentError("Validated payload supplier GSTIN is invalid.")
        return current

    @staticmethod
    def _document_reference(payload_json: str) -> dict[str, str]:
        try:
            payload = json.loads(payload_json, parse_float=Decimal)
            document = payload["DocDtls"]
            document_type = document["Typ"]
            document_number = document["No"]
            document_date = document["Dt"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise IRPPermanentError(
                "Validated payload does not contain invoice document details."
            ) from exc
        if not all(
            isinstance(value, str) and value
            for value in (document_type, document_number, document_date)
        ):
            raise IRPPermanentError("Validated payload invoice document details are invalid.")
        return {
            "DocType": document_type,
            "DocNum": document_number,
            "DocDate": document_date,
        }

    def _token_key(self, gstin: str) -> str:
        return f"irp:nic:token:{self.config.client_id}:{gstin}"


def configured_irp_client() -> IRPClient:
    """Build the selected provider without embedding credentials in queued task arguments."""
    provider = "NIC"
    if provider != "NIC":
        raise IRPPermanentError(f"Unsupported IRP provider {provider!r}.")
    return NICIRPClient(
        NICConfig(
            auth_url=str(current_app.config["IRP_NIC_AUTH_URL"]),
            generate_url=str(current_app.config["IRP_NIC_GENERATE_URL"]),
            lookup_url=str(current_app.config["IRP_NIC_LOOKUP_URL"]),
            cancel_url=str(current_app.config["IRP_NIC_CANCEL_URL"]),
            eway_url=str(current_app.config["IRP_NIC_EWAY_URL"]),
            username=str(current_app.config["IRP_NIC_USERNAME"]),
            password=str(current_app.config["IRP_NIC_PASSWORD"]),
            client_id=str(current_app.config["IRP_NIC_CLIENT_ID"]),
            client_secret=str(current_app.config["IRP_NIC_CLIENT_SECRET"]),
        )
    )
