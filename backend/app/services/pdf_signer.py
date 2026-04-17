"""PAdES digital signature embedding for medical finding PDFs.

Signs via the AKD smart card through the Local Agent. If the card or agent is
not available, returns the original (unsigned) PDF bytes — the doctor can sign
by hand on the footer signature line. There is NO local/self-signed fallback:
we never produce a PDF that appears signed but isn't legally binding.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

from asn1crypto import x509 as asn1_x509
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields as sig_fields
from pyhanko.sign import signers
from pyhanko_certvalidator.registry import SimpleCertificateStore

from app.services.agent_connection_manager import agent_manager

logger = logging.getLogger(__name__)

# Map agent JOSE algorithm -> pyHanko digest algorithm
_AGENT_ALG_TO_DIGEST: dict[str, str] = {
    "RS256": "sha256",
    "ES256": "sha256",
    "ES384": "sha384",
    "ES512": "sha512",
}


# Stable reason tokens for SignPdfResult.reason. Frontend uses these programmatically;
# user-facing Croatian text is composed at the edge (toast/audit layer).
REASON_AGENT_NOT_CONNECTED = "agent-not-connected"
REASON_CARD_NOT_INSERTED = "card-not-inserted"
REASON_CERT_INFO_FAILED = "cert-info-failed"
REASON_SIGNING_FAILED = "signing-failed"


@dataclass
class SignPdfResult:
    """Outcome of a PDF signing attempt.

    On success, `pdf_bytes` is the signed PDF, `signed` is True, `reason` is None.
    On failure, `pdf_bytes` is the original unsigned input, `signed` is False, and
    `reason` is one of the REASON_* tokens above.
    """
    pdf_bytes: bytes
    signed: bool
    reason: str | None = None


class AgentPdfSigner(signers.Signer):
    """pyHanko Signer that delegates raw signing to the local agent's AKD smart card.

    Retrieves the X.509 certificate from the agent, then uses the agent's
    sign_raw (NCryptSignHash) for the actual cryptographic operation.
    pyHanko handles CMS/PAdES wrapping automatically.
    """

    def __init__(
        self,
        tenant_id: UUID,
        cert_der: bytes,
        agent_algorithm: str,
    ):
        cert = asn1_x509.Certificate.load(cert_der)
        cert_store = SimpleCertificateStore()
        cert_store.register(cert)
        self._tenant_id = tenant_id
        self._agent_algorithm = agent_algorithm
        super().__init__(
            signing_cert=cert,
            cert_registry=cert_store,
        )

    async def async_sign_raw(
        self, data: bytes, digest_algorithm: str, dry_run: bool = False
    ) -> bytes:
        """Sign raw data via the agent's smart card.

        pyHanko passes DER-encoded signed attributes as `data`.
        The agent hashes and signs via NCryptSignHash.
        """
        if dry_run:
            return b"\x00" * 256

        data_b64 = base64.b64encode(data).decode("ascii")
        result = await agent_manager.sign_raw(
            self._tenant_id,
            data_base64=data_b64,
            algorithm=self._agent_algorithm,
            timeout=30.0,
        )
        if "error" in result:
            raise RuntimeError(f"Agent signing failed: {result['error']}")
        return base64.b64decode(result.get("signature", ""))


async def _sign_with_agent(
    pdf_bytes: bytes,
    *,
    tenant_id: UUID,
    doctor_name: str = "",
    reason: str = "",
    location: str = "",
) -> bytes:
    """Sign PDF using the AKD smart card via the local agent. Raises on failure."""
    cert_info = await agent_manager.get_cert_info(tenant_id, timeout=15.0)
    if "error" in cert_info:
        raise RuntimeError(f"Agent cert info failed: {cert_info['error']}")

    cert_der_b64 = cert_info.get("cert_der_base64")
    if not cert_der_b64:
        raise RuntimeError("Agent did not return certificate DER")

    agent_algorithm = cert_info.get("algorithm", "RS256")
    signer = AgentPdfSigner(
        tenant_id=tenant_id,
        cert_der=base64.b64decode(cert_der_b64),
        agent_algorithm=agent_algorithm,
    )

    reader = PdfFileReader(BytesIO(pdf_bytes))
    w = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
    page_count = int(reader.root["/Pages"]["/Count"])
    last_page = max(0, page_count - 1)

    sig_field = sig_fields.SigFieldSpec(
        sig_field_name="DoctorSignature",
        on_page=last_page,
    )

    digest = _AGENT_ALG_TO_DIGEST.get(agent_algorithm, "sha256")
    meta = signers.PdfSignatureMetadata(
        field_name="DoctorSignature",
        md_algorithm=digest,
        reason=reason,
        location=location,
        name=doctor_name,
    )

    output = BytesIO()
    await signers.async_sign_pdf(w, meta, signer=signer, new_field_spec=sig_field, output=output)

    signed_bytes = output.getvalue()
    logger.info(
        "PDF signed (AKD smart card) for %s — %d -> %d bytes, alg=%s",
        doctor_name, len(pdf_bytes), len(signed_bytes), agent_algorithm,
    )
    return signed_bytes


async def sign_pdf(
    pdf_bytes: bytes,
    *,
    tenant_id: UUID,
    doctor_name: str = "",
    reason: str = "Digitalno potpisani medicinski nalaz",
    location: str = "",
) -> SignPdfResult:
    """Sign a PDF with a PAdES digital signature via the AKD smart card.

    Never raises on signing failure. If the agent is not connected, the card is
    not in the reader, or signing otherwise fails, returns the ORIGINAL unsigned
    PDF bytes with `signed=False` and a stable `reason` token describing why.
    The caller surfaces the outcome to the user; the doctor hand-signs on the
    footer signature line when unsigned.

    Unexpected exceptions from pyHanko or the agent are caught and reported as
    `signing-failed` — the download always returns a usable PDF.
    """
    conn = agent_manager.get_any_connected(tenant_id)
    if conn is None:
        logger.info(
            "PDF signing skipped: no Local Agent connected for tenant %s", tenant_id,
        )
        return SignPdfResult(pdf_bytes=pdf_bytes, signed=False, reason=REASON_AGENT_NOT_CONNECTED)

    if not conn.card_inserted:
        logger.info(
            "PDF signing skipped: agent connected for tenant %s but no card inserted",
            tenant_id,
        )
        return SignPdfResult(pdf_bytes=pdf_bytes, signed=False, reason=REASON_CARD_NOT_INSERTED)

    try:
        signed_bytes = await _sign_with_agent(
            pdf_bytes,
            tenant_id=tenant_id,
            doctor_name=doctor_name,
            reason=reason,
            location=location,
        )
    except RuntimeError as e:
        msg = str(e)
        if "cert info" in msg.lower() or "certificate DER" in msg:
            logger.warning(
                "PDF signing failed at cert readout for tenant %s: %s", tenant_id, e,
            )
            return SignPdfResult(pdf_bytes=pdf_bytes, signed=False, reason=REASON_CERT_INFO_FAILED)
        logger.warning(
            "PDF signing failed during agent sign for tenant %s: %s", tenant_id, e,
        )
        return SignPdfResult(pdf_bytes=pdf_bytes, signed=False, reason=REASON_SIGNING_FAILED)
    except Exception:
        logger.exception("Unexpected PDF signing failure for tenant %s", tenant_id)
        return SignPdfResult(pdf_bytes=pdf_bytes, signed=False, reason=REASON_SIGNING_FAILED)

    return SignPdfResult(pdf_bytes=signed_bytes, signed=True, reason=None)
